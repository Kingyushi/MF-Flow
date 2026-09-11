"""PGIM India Mutual Fund — API-driven per-scheme xlsx, with a GET-only page fallback.

Page structure (Angular SPA, server-side rendered):
The probe captured two critical API endpoints:

1. /api/v1/brochure/disclosure/section — returns the full section/tab structure
   including the "Monthly Portfolio" section (SectionId "SECTION_747960037")
   with tabs: Equity (TabId 12), Debt (13), Fund of Funds (14), Prior to June
   2021 (66).

2. /api/v1/brochure/published/disclosure — returns the actual disclosure entries
   for a given section+tab. Each entry has: title, pdfPath (which is actually
   xlsx despite the name), dateMonthYear, year, month, date.

The SPA calls these APIs from its Angular frontend. We can call them directly
via Fetcher.static (no Playwright needed), then parse the response to find the
latest entries under the Equity tab.

The pdfPath URLs look like:
  https://www.pgimindia.com/api/v1/brochure/about-us/image/<filename>

Post-June-2021 entries are per-scheme xlsx files (one per fund).

Access findings (2026-09-12), which drive the fallback below:
- PGIM sits behind an AWS load balancer + WAF that answers HTTP 403 to EVERY
  request from datacenter IPs (the DigitalOcean droplet): homepage, page, API
  and file downloads alike. The same requests succeed from a residential IP.
- Through the Bright Data residential proxy every GET succeeds, but a POST is
  refused with HTTP 402 "bad_endpoint: POST requests are not allowed"
  (no-KYC mode). The disclosure list API is POST-only (GET -> 405), so from
  the droplet the API cannot be used for discovery. The page and the files
  are retried through MF_FLOW_PROXY automatically when the direct GET fails,
  so pgimindia.com does not have to be listed in MF_FLOW_PROXY_HOSTS.
- The Monthly-Portfolio page is server-side rendered: the first tab's first
  TEN cards carry `<label class="w-100 file-title">PGIM INDIA LARGE CAP FUND
  Aug 2026</label>`. The download filename is exactly that title:
  pdfPath == API_BASE + "/about-us/image/" + title + ".xlsx" (checked for all
  14 Equity-tab August-2026 entries). A file that does not exist answers
  HTTP 204 with an empty body, not 404.

Strategy: try the POST API first (unchanged behaviour where it works). If it
fails, GET the page, read the titles, take the latest month from them, and
for configured schemes that sit beyond the ten rendered cards (Multi Cap in
Aug 2026) probe the title-derived URL. A probe must return a real workbook
(PK signature) or the scheme is reported as a download failure.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from lib.fetcher import Fetcher, fresh_dest, proxy_available
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, parse_as_on
from lib.scheme_filter import match_schemes

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)

log = get_logger("mf32")

API_BASE = "https://www.pgimindia.com/api/v1/brochure"
DISCLOSURES_URL = "https://www.pgimindia.com/mutual-funds/disclosures/Portfolios/Monthly-Portfolio"

# Section and Tab IDs from the disclosure/section API response
SECTION_MONTHLY = "SECTION_747960037"
TAB_EQUITY = 12

# <label class="w-100 file-title">PGIM INDIA LARGE CAP FUND Aug 2026</label>
_PAGE_TITLE_RE = re.compile(
    r'class="[^"]*\bfile-title\b[^"]*"[^>]*>\s*([^<]+?)\s*</label>', re.IGNORECASE
)
# Trailing "<Mon> <YYYY>" of a card title ("Aug 2026", "August 2026").
_MONTH_TOKEN_RE = re.compile(r"\b([A-Za-z]{3,9})\s+((?:19|20)\d{2})\s*$")


def file_url_for_title(title: str) -> str:
    """Download URL for a card title: pdfPath is exactly `<title>.xlsx`."""
    return f"{API_BASE}/about-us/image/{title}.xlsx"


def _parse_disclosure_entries(data: list[dict]) -> list[dict]:
    """Pure parse: extract and sort disclosure entries from API response.

    Filters to Equity tab monthly portfolio entries, parses year/month,
    returns sorted newest-first.
    """
    results = []
    for tab_group in data:
        tab_id = tab_group.get("tabId")
        if tab_id != TAB_EQUITY:
            continue
        for entry in tab_group.get("content", []):
            title = entry.get("title", "")
            year_str = entry.get("year", "")
            month_str = entry.get("month", "")
            pdf_path = entry.get("pdfPath", "")

            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue

            month_num = ALL_MONTHS.get((month_str or "").lower())
            if not month_num:
                continue

            results.append({
                "title": title,
                "url": pdf_path,
                "year": year,
                "month": month_num,
                "date_str": entry.get("dateMonthYear", ""),
            })

    results.sort(key=lambda e: (e["year"], e["month"]), reverse=True)
    return results


def _parse_page_titles(html: str) -> list[dict]:
    """Pure parse of the server-rendered Monthly-Portfolio page.

    Every rendered card title that ends in "<Mon> <YYYY>" becomes an entry
    whose URL is the title-derived download path. Sorted newest-first.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for m in _PAGE_TITLE_RE.finditer(html):
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        mt = _MONTH_TOKEN_RE.search(title)
        if not mt:
            continue
        month_num = ALL_MONTHS.get(mt.group(1).lower())
        if not month_num or title in seen:
            continue
        seen.add(title)
        out.append({
            "title": title,
            "url": file_url_for_title(title),
            "year": int(mt.group(2)),
            "month": month_num,
            "date_str": "",
            "month_token": mt.group(0).strip(),
            "probe": False,
        })
    out.sort(key=lambda e: (e["year"], e["month"]), reverse=True)
    return out


def _probe_entries_for_missing_schemes(
    schemes: list[str], page_entries: list[dict], month_token: str, year: int, month: int
) -> list[dict]:
    """Candidate entries for configured schemes that no rendered title matches.

    The page renders only the first ten cards of the tab, so a tracked scheme
    further down (Multi Cap in Aug 2026) never appears there. Its file still
    lives at the title-derived URL, so build that title from the configured
    scheme name plus the month token copied from the page. `download()` keeps
    a probe only if the URL returns a real workbook.
    """
    report = match_schemes(schemes, [(e["title"], e["url"]) for e in page_entries])
    out: list[dict] = []
    for scheme in report.unmatched_schemes:
        name = re.sub(r"\s+", " ", scheme).strip().upper()
        title = f"{name} {month_token}"
        out.append({
            "title": title,
            "url": file_url_for_title(title),
            "year": year,
            "month": month,
            "date_str": "",
            "month_token": month_token,
            "probe": True,
        })
    return out


class Scraper(BaseScraper):
    PATTERN = "per_scheme_xlsx"

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        host = host_of(DISCLOSURES_URL)
        try:
            return self._discover_via_api(fetcher, host)
        except NoDataYetError:
            raise
        except Exception as e:
            # HTTP 403 from PGIM's WAF (datacenter IP), HTTP 402 from the
            # proxy (POST refused), or a network error: use the page instead.
            log.warning("PGIM: API discovery failed (%s); falling back to the page titles via GET", e)
            return self._discover_via_page(fetcher, host, api_error=e)

    def _discover_via_api(self, fetcher: Fetcher, host: str) -> DiscoveryResult:
        # The disclosure API requires POST with a JSON body containing the sectionId.
        # GET returns HTTP 405; POST without sectionId returns a generic error.
        url = f"{API_BASE}/published/disclosure"
        session = fetcher.static._session(host)
        fetcher.static._polite(host)
        resp = session.post(
            url,
            json={"sectionId": SECTION_MONTHLY},
            timeout=30,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.pgimindia.com",
                "Referer": DISCLOSURES_URL,
            },
        )
        if not resp.ok:
            raise ScraperError(f"PGIM disclosure API HTTP {resp.status_code}")

        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise ScraperError(f"PGIM: JSON parse error: {e}")

        data = body.get("data", [])
        if not data:
            raise NoDataYetError("PGIM: no data in disclosure API response")

        entries = _parse_disclosure_entries(data)
        if not entries:
            raise NoDataYetError("PGIM: no Equity monthly portfolio entries")

        # Find latest month
        latest_year = entries[0]["year"]
        latest_month = entries[0]["month"]
        at_latest = [e for e in entries if e["year"] == latest_year and e["month"] == latest_month]

        as_on: Optional[date] = None
        for e in at_latest:
            as_on = parse_as_on(e.get("date_str", ""), e.get("title", ""))
            if as_on:
                break

        self._entries = at_latest
        self._host = host
        return DiscoveryResult(year=latest_year, month=latest_month, as_on_date=as_on)

    def _discover_via_page(self, fetcher: Fetcher, host: str, *, api_error: object = None) -> DiscoveryResult:
        res = fetcher.static.fetch_html(DISCLOSURES_URL, host)
        if not res.ok and proxy_available():
            # Datacenter IPs get HTTP 403 from PGIM's WAF. The residential
            # proxy passes GETs even when pgimindia.com is not listed in
            # MF_FLOW_PROXY_HOSTS, so retry through it before giving up.
            log.warning("PGIM: page fetch failed directly (%s); retrying through MF_FLOW_PROXY", res.error)
            res = fetcher.static.fetch_html(DISCLOSURES_URL, host, force_proxy=True)
            if res.ok:
                self._force_proxy = True
        if not res.ok:
            raise ScraperError(
                f"PGIM: disclosure API failed ({api_error}) and the disclosure page failed too ({res.error})"
            )
        entries = _parse_page_titles(res.html)
        if not entries:
            raise ScraperError(
                f"PGIM: disclosure API failed ({api_error}) and no file titles were found on the "
                "disclosure page (layout changed?)"
            )

        latest_year = entries[0]["year"]
        latest_month = entries[0]["month"]
        at_latest = [e for e in entries if e["year"] == latest_year and e["month"] == latest_month]
        probes = _probe_entries_for_missing_schemes(
            self.mf.schemes, at_latest, at_latest[0]["month_token"], latest_year, latest_month
        )
        log.info(
            "PGIM: page fallback — %d title(s) for %04d-%02d rendered on the page; probing %d scheme(s) "
            "beyond the rendered cards: %s",
            len(at_latest), latest_year, latest_month, len(probes),
            ", ".join(p["title"] for p in probes) or "-",
        )

        self._entries = at_latest + probes
        self._host = host
        # The page shows only "<Mon> <YYYY>"; the as-on day is read from the
        # workbook itself downstream (month plausibility guard).
        return DiscoveryResult(year=latest_year, month=latest_month, as_on_date=None)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        entries = getattr(self, "_entries", None)
        if entries is None:
            self.discover_latest_month(fetcher)
            entries = getattr(self, "_entries", None)
        if entries is None:
            raise ScraperError("PGIM: no entries after discovery")

        host = getattr(self, "_host", host_of(DISCLOSURES_URL))

        # Build link pairs for scheme matching
        link_pairs = [(e["title"], e["url"]) for e in entries]
        report = match_schemes(self.mf.schemes, link_pairs)
        self._match_report = report
        log.info(report.summary(self.mf.id, self.mf.name))

        files: list[DownloadedFile] = []
        failures: list[str] = []
        for m in report.matched:
            # Find the entry by title
            entry = next((e for e in entries if e["title"] == m.link_text), None)
            if not entry:
                continue
            url = entry["url"]
            if not url:
                log.warning("PGIM: no URL for %s", m.scheme_name)
                failures.append(m.scheme_name)
                continue
            probe = bool(entry.get("probe"))

            safe_seg = "".join(c for c in m.scheme_name if c.isalnum())[:20]
            # Detect extension from URL
            ext = "xlsx"
            if url.lower().endswith(".xlsb"):
                ext = "xlsb"
            dest = fresh_dest(f"{self.mf.id}-{safe_seg}", ext)

            # A probed URL is a guess: insist on a real workbook (a missing
            # file answers HTTP 204 with an empty body).
            sigs = (b"PK",) if probe else ()
            force = bool(getattr(self, "_force_proxy", False))
            ok = fetcher.static.download_file(
                url, dest, host_of(url) or host,
                referer=DISCLOSURES_URL, expected_signatures=sigs, force_proxy=force,
            )
            if not ok and not force and proxy_available():
                # Same WAF block as discovery: retry the file through the proxy.
                ok = fetcher.static.download_file(
                    url, dest, host_of(url) or host,
                    referer=DISCLOSURES_URL, expected_signatures=sigs, force_proxy=True,
                )
                if ok:
                    self._force_proxy = True
            if not ok and not probe:
                # Try browser download as fallback
                ok = fetcher.browser.download_file(
                    url, dest, host_of(url) or host,
                    referer=DISCLOSURES_URL,
                    expected_signatures=(),
                )
            if not ok:
                if probe:
                    log.warning(
                        "PGIM: %s — no workbook at the title-derived URL %s "
                        "(not published yet, or PGIM titled it differently)", m.scheme_name, url,
                    )
                else:
                    log.warning("PGIM: download failed for %s", m.scheme_name)
                failures.append(m.scheme_name)
                continue

            files.append(DownloadedFile(
                src_path=dest,
                scheme_name=m.scheme_name,
                source_url=url,
                label=m.scheme_name,
            ))

        self._download_failures = failures
        if not files:
            raise ScraperError(f"{self.mf.name}: no schemes downloaded")
        return files
