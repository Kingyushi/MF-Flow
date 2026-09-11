"""Tata Mutual Fund — single multi-sheet xlsx from the AMC's own portfolio page.

History: until 2026-09-12 this scraper read advisorkhoj.com, a third-party
aggregator that lags the AMC by weeks (Tata posted the August-2026 workbook on
8 Sep 2026; advisorkhoj still listed July on 12 Sep). The AMC page is now the
only source.

Page: https://www.tatamutualfund.com/schemes-related/portfolio (Next.js, server
rendered, reachable from a DigitalOcean droplet without a proxy as of
2026-09-12). The list is NOT in the DOM as anchors — it is embedded in the
React Server Components payload (`<script>self.__next_f.push([1,"..."])</script>`
chunks) as a component prop:

    "initialData": [
      {"field_title": "For the year 2026",
       "field_document_title": "Portfolio as on 31st August, 2026",
       "field_media_document": "https://betacms.tatamutualfund.com/system/files/2026-09/Monthly%20Portfolio%20as%20on%2031st%20August%202026.xlsx",
       ...}, ...]

Rows go back to 2010 (pdf era) and include odd one-offs (a fortnightly
scheme-level file in Dec 2017). We key on the document TITLE date, keep only
month-end dates whose file is xls/xlsx and whose title names no scheme, and
take the latest.

Notes:
- href folders carry the PUBLICATION month (2026-09 for August data), so the
  month is never inferred from the URL. Files are served from S3.
- Plain GETs only (no browser). If the AMC ever blocks the server's IP, the
  page and the file are retried through MF_FLOW_PROXY automatically.
"""
from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from lib.fetcher import Fetcher, fresh_dest, proxy_available
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS

from .base import DiscoveryResult, DownloadedFile, ScraperError, host_of, retry
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf40")

PORTFOLIO_URL = "https://www.tatamutualfund.com/schemes-related/portfolio"

# One React Server Components payload chunk: self.__next_f.push([1,"<js string>"])
_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
# "31st August, 2026" / "30th June 2026" / "29th February, 2024"
_TITLE_DATE_RE = re.compile(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s+((?:19|20)\d{2})")
_SPREADSHEET_RE = re.compile(r"\.xlsx?(?:\?|#|$)", re.IGNORECASE)
# Scheme-level or non-monthly one-offs ("Portfolio for Tata Regular Savings
# Equity Fund as on 15th December 2017", weekly / fortnightly files).
_NOT_CONSOLIDATED_RE = re.compile(r"\bfund\b|\bweekly\b|\bfortnight", re.IGNORECASE)

SIG_XLSX = b"PK\x03\x04"
SIG_XLS = b"\xd0\xcf\x11\xe0"


@dataclass
class PortfolioEntry:
    title: str
    url: str
    as_on: date
    section: str = ""


def is_month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def rsc_payload(html: str) -> str:
    """Concatenate the decoded React Server Components payload chunks of a page."""
    parts: list[str] = []
    for raw in _CHUNK_RE.findall(html):
        try:
            parts.append(json.loads('"' + raw + '"'))
        except ValueError:
            continue
    return "".join(parts)


def title_date(title: str) -> Optional[date]:
    """Date named in a document title, or None."""
    m = _TITLE_DATE_RE.search(title)
    if not m:
        return None
    month = ALL_MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def parse_portfolio_entries(html: str) -> list[PortfolioEntry]:
    """Pure parse: every consolidated month-end portfolio spreadsheet on the page, newest first."""
    payload = rsc_payload(html)
    dec = json.JSONDecoder()
    out: list[PortfolioEntry] = []
    seen: set[str] = set()
    for m in re.finditer(r'"initialData"\s*:', payload):
        start = payload.find("[", m.end())
        if start < 0:
            continue
        try:
            items, _ = dec.raw_decode(payload, start)
        except ValueError:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            title = re.sub(r"\s+", " ", str(it.get("field_document_title") or "")).strip()
            url = str(it.get("field_media_document") or "").strip()
            if not title or not url or not _SPREADSHEET_RE.search(url):
                continue
            if _NOT_CONSOLIDATED_RE.search(title):
                continue
            d = title_date(title)
            if not d or not is_month_end(d):
                continue
            if url in seen:
                continue
            seen.add(url)
            out.append(PortfolioEntry(
                title=title, url=url, as_on=d, section=str(it.get("field_title") or ""),
            ))
    out.sort(key=lambda e: e.as_on, reverse=True)
    return out


def _looks_like_workbook(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(8)
    except OSError:
        return False
    return head.startswith(SIG_XLSX) or head.startswith(SIG_XLS)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = PORTFOLIO_URL

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        host = host_of(self.DISCLOSURES_URL)
        res = fetcher.static.fetch_html(self.DISCLOSURES_URL, host)
        if not res.ok and proxy_available():
            log.warning("Tata: page fetch failed directly (%s); retrying through MF_FLOW_PROXY", res.error)
            res = fetcher.static.fetch_html(self.DISCLOSURES_URL, host, force_proxy=True)
            if res.ok:
                self._force_proxy = True
        if not res.ok:
            raise ScraperError(f"Tata: portfolio page fetch failed ({res.error})")
        entries = parse_portfolio_entries(res.html or "")
        if not entries:
            raise ScraperError(
                "Tata: no consolidated month-end portfolio spreadsheet found in the AMC page "
                "payload (page layout changed?)"
            )
        latest = entries[0]
        log.info("Tata: latest on the AMC page = %r -> %s", latest.title, latest.url)
        self._host = host
        self._page = None
        self._target = Target(
            year=latest.as_on.year, month=latest.as_on.month, label=latest.title,
            as_on=latest.as_on, kind="url", payload=latest.url,
        )
        return DiscoveryResult(year=latest.as_on.year, month=latest.as_on.month, as_on_date=latest.as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        t = getattr(self, "_target", None)
        if t is None:
            self.discover_latest_month(fetcher)
            t = getattr(self, "_target", None)
        if t is None:
            raise ScraperError(f"{self.mf.name}: discovery did not populate _target")

        url = str(t.payload)
        ext = "xls" if url.lower().split("?", 1)[0].endswith(".xls") else "xlsx"
        dest = fresh_dest(self.mf.id, ext)
        host = host_of(url) or getattr(self, "_host", host_of(self.DISCLOSURES_URL))

        force = bool(getattr(self, "_force_proxy", False))
        ok = fetcher.static.download_file(
            url, dest, host, referer=self.DISCLOSURES_URL, expected_signatures=(), force_proxy=force,
        )
        if not ok and not force and proxy_available():
            log.warning("Tata: direct download failed; retrying through MF_FLOW_PROXY")
            ok = fetcher.static.download_file(
                url, dest, host, referer=self.DISCLOSURES_URL, expected_signatures=(), force_proxy=True,
            )
            if ok:
                self._force_proxy = True
        if not ok:
            ok = fetcher.browser.download_file(
                url, dest, host, referer=self.DISCLOSURES_URL, expected_signatures=(),
            )
        if not ok:
            raise ScraperError(f"{self.mf.name}: download failed for {t.label!r} ({url})")
        if not _looks_like_workbook(dest):
            raise ScraperError(
                f"{self.mf.name}: {t.label!r} downloaded from {url} is not an Excel workbook"
            )
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=url,
            label=self.mf.name,
        )]
