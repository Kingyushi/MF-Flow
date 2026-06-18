"""WhiteOak Capital Mutual Fund — per-scheme xlsx via Strapi REST API.

Uses per-scheme-latest semantics: each user scheme gets ITS individual
latest month (WhiteOak publishes per-scheme on a rolling basis, so May 2026
for Mid Cap may ship a week before May 2026 for Flexi Cap).


The disclosure page is a Next.js SPA backed by a Strapi CMS at
``cms.whiteoakamc.com``. The API exposes all portfolio entries with direct
download URLs on ``content.whiteoakamc.com`` (S3).

API endpoint:
    GET https://cms.whiteoakamc.com/api/scheme-portfolios
        ?populate=*
        &filters[period][$eq]=Monthly
        &sort[0]=published_date:desc
        &pagination[page]=1&pagination[pageSize]=50

Each entry has:
    - ``scheme_name``  — full scheme name (matches user config exactly)
    - ``period``       — "Monthly" | "Fortnightly" | "Half Yearly"
    - ``doc_name``     — title text like "... Monthly Portfolio Disclosure - 30th April2026"
    - ``published_date`` — ISO date like "2026-05-08"
    - ``doc_file.data.attributes.url`` — direct xlsx URL

Because the API returns structured data with direct URLs, NO Playwright is
needed. Static HTTP is sufficient for both discovery and download.

For testability, ``parse_api_entries`` accepts a list of dicts (API response
items) and returns the latest month + filtered entries.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer
from lib.scheme_filter import MatchReport, match_schemes

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)
log = get_logger("mf46")

API_URL = "https://cms.whiteoakamc.com/api/scheme-portfolios"
CONTENT_HOST = "content.whiteoakamc.com"
DISCLOSURES_URL = "https://mf.whiteoakamc.com/regulatory-disclosures/scheme-portfolios"


def _file_url(item: dict) -> str:
    """Extract the xlsx download URL from a Strapi entry."""
    doc_file = item.get("attributes", {}).get("doc_file", {})
    data = doc_file.get("data")
    if isinstance(data, dict):
        return data.get("attributes", {}).get("url", "")
    return ""


def _doc_name(item: dict) -> str:
    return item.get("attributes", {}).get("doc_name", "")


def _scheme_name(item: dict) -> str:
    return item.get("attributes", {}).get("scheme_name", "")


def _published_date(item: dict) -> str:
    return item.get("attributes", {}).get("published_date", "")


def parse_api_entries(
    items: list[dict],
) -> tuple[tuple[int, int], list[tuple[tuple[int, int], dict]]]:
    """Pure parse: given Strapi API entry dicts, return:
      - max (year, month) across all schemes
      - list of (per-scheme-latest-(year,month), item) — one entry per
        distinct scheme_name, each at THAT scheme's individual latest month

    WhiteOak publishes per-scheme portfolios on a rolling basis (Mid Cap May
    2026 ships today, Flexi Cap May 2026 ships a week later). Picking 'latest
    month overall' would drop schemes not yet published; per-scheme latest
    preserves every scheme at its own latest available month.
    """
    if not items:
        raise NoDataYetError("WhiteOak: no scheme entries from API")

    # Parse each item to (ym, item). Skip items missing file URL or month.
    ym_items: list[tuple[tuple[int, int], dict]] = []
    for item in items:
        if not _file_url(item):
            continue
        # Prefer doc_name for month inference — file URLs include content
        # hashes (e.g. "_09eb8c14a2.xlsx") that mislead try_infer.
        ym: Optional[tuple[int, int]] = try_infer(_doc_name(item))
        if not ym:
            pd = _published_date(item)
            if pd and len(pd) >= 7:
                try:
                    parts = pd.split("-")
                    y, m = int(parts[0]), int(parts[1])
                    if 2015 <= y <= 2099 and 1 <= m <= 12:
                        ym = (y, m)
                except (ValueError, IndexError):
                    pass
        if ym:
            ym_items.append((ym, item))

    if not ym_items:
        raise NoDataYetError("WhiteOak: could not infer month from API entries")

    # Group by NORMALIZED scheme identifier (strip dates / month names /
    # "monthly portfolio" boilerplate so the same scheme across different
    # months hashes to the same key). Keep each scheme's latest month.
    best_per_scheme: dict[str, tuple[tuple[int, int], dict]] = {}
    for ym, item in ym_items:
        raw = _scheme_name(item) or _doc_name(item)
        key = _normalize_scheme_key(raw)
        if not key:
            continue
        prev = best_per_scheme.get(key)
        if prev is None or ym > prev[0]:
            best_per_scheme[key] = (ym, item)
    picks = list(best_per_scheme.values())
    max_ym = max(p[0] for p in picks)
    return max_ym, picks


def _normalize_scheme_key(raw: str) -> str:
    """Strip dates and month names so the same scheme across different months
    hashes to the same key (e.g. "...Mid Cap Fund...April 2026" and
    "...Mid Cap Fund...May 2026" → same key).

    Handles AMC-side oddities like "March2026" (no separator) and "30th May".
    """
    import re
    s = raw.lower()
    s = re.sub(r"monthly\s+portfolio(?:\s+disclosure)?", "", s)
    s = re.sub(r"\d{1,2}(?:st|nd|rd|th)?\s*", " ", s)
    # Strip month names (don't require \b — handles 'march2026' contiguous)
    s = re.sub(
        r"(january|february|march|april|may|june|july|"
        r"august|september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)",
        "", s,
    )
    s = re.sub(r"20\d{2}", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


# Legacy alias kept for backward compatibility with tests
def parse_scheme_entries(
    entries: list[tuple[str, str]],
) -> tuple[tuple[int, int], list[tuple[str, str]]]:
    """Parse (text, href) pairs into per-scheme-latest entries.

    Wraps parse_api_entries by converting (text, href) pairs into fake API
    items. Returns ((max_year, max_month), list of (doc_name, url)) where
    each entry is at its individual scheme's latest month.
    """
    items = []
    for text, href in entries:
        items.append({
            "attributes": {
                "scheme_name": text,
                "period": "Monthly",
                "doc_name": text,
                "doc_file": {"data": {"attributes": {"url": href}}},
                "published_date": "",
            }
        })
    (year, month), picks = parse_api_entries(items)
    filtered = [(_doc_name(it), _file_url(it)) for _ym, it in picks]
    return (year, month), filtered


class Scraper(BaseScraper):
    PATTERN = "per_scheme_xlsx"
    DISCLOSURES_URL = DISCLOSURES_URL

    def _fetch_api(self, fetcher: Fetcher) -> list[dict]:
        """Hit the Strapi REST API and return the latest monthly entries."""
        params = {
            "populate": "*",
            "filters[period][$eq]": "Monthly",
            "sort[0]": "published_date:desc",
            "pagination[page]": "1",
            "pagination[pageSize]": "50",
        }
        url = API_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        result = fetcher.static.fetch_html(url, host_of(API_URL))
        if not result.ok:
            raise ScraperError(
                f"WhiteOak API returned HTTP {result.status_code}: {result.error}"
            )
        import json
        try:
            data = json.loads(result.html)
        except json.JSONDecodeError as e:
            raise ScraperError(f"WhiteOak API returned invalid JSON: {e}")
        items = data.get("data", [])
        if not items:
            raise NoDataYetError("WhiteOak API returned no entries")
        return items

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        items = self._fetch_api(fetcher)
        (year, month), picks = parse_api_entries(items)
        # Store as list of (ym, item) so download can place each in its month folder
        self._picks = picks

        # Try to extract as_on date from the latest-month entry
        as_on = None
        for ym, item in picks:
            if ym == (year, month):
                as_on = parse_as_on(_doc_name(item), _file_url(item))
                if as_on:
                    break
        if not as_on:
            as_on = date(year, month, 1)

        return DiscoveryResult(year=year, month=month, as_on_date=as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        picks = getattr(self, "_picks", None)
        if picks is None:
            self.discover_latest_month(fetcher)
            picks = self._picks

        # Build (text, url) pairs for scheme matching; keep ym alongside.
        link_pairs: list[tuple[str, str]] = []
        item_by_text: dict[str, tuple[tuple[int, int], dict]] = {}
        for ym, item in picks:
            scheme = _scheme_name(item) or _doc_name(item)
            url = _file_url(item)
            if not url:
                continue
            link_pairs.append((scheme, url))
            item_by_text[scheme] = (ym, item)

        report: MatchReport = match_schemes(self.mf.schemes, link_pairs)
        log.info(report.summary(self.mf.id, self.mf.name))
        self._match_report = report

        files: list[DownloadedFile] = []
        download_failures: list[str] = []
        for m in report.matched:
            ym, _item = item_by_text[m.link_text]
            url = m.link_url
            safe_seg = "".join(c for c in m.scheme_name if c.isalnum())[:20]
            dest = fresh_dest(f"{self.mf.id}-{safe_seg}", "xlsx")
            ok = fetcher.static.download_file(
                url, dest, host_of(url) or CONTENT_HOST,
                referer=DISCLOSURES_URL,
                expected_signatures=(),
            )
            if not ok:
                log.warning("download failed for %s (%s)", m.scheme_name, url)
                download_failures.append(m.scheme_name)
                continue
            files.append(DownloadedFile(
                src_path=dest,
                scheme_name=m.scheme_name,
                source_url=url,
                label=m.scheme_name,
                year=ym[0], month=ym[1],
            ))

        self._download_failures = download_failures
        if not files:
            raise ScraperError(f"{self.mf.name}: no schemes downloaded")
        return files
