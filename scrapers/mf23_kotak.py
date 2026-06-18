"""Kotak Mutual Fund — direct API for Portfolios > Consolidated.

Radware bot detection blocks plain Playwright. The stealth-init browser context
passes, and reveals an Angular SPA whose Portfolios section fires:

    GET /api/kotakapi/forms/user/getsubheaderList/417?option=51&pagination=1&pageSize=100&pageNumber=1

headerId 417 = "Portfolios", optionId 51 = "Consolidated & Fortnightly Portfolio".
The response JSON has subHeaderList[] with entries like:
    - "Consolidated Portfolio as on April 30, 2026" (contentType: "upload",
       content: "FormsDownloads/Portfolios/.../file.xlsx")
    - "Fortnightly Portfolio as on May 15, 2026"

We filter to "Consolidated" entries (skip fortnightly), parse year/month from
the subHeaderTitle, and download the latest xlsx from
    https://www.kotakmf.com/{content}
"""
from __future__ import annotations

import json
import re
from datetime import date

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, parse_as_on, try_infer

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    retry,
)

log = get_logger("mf23")

_API_URL = (
    "https://www.kotakmf.com/api/kotakapi/forms/user/getsubheaderList/417"
    "?option=51&pagination=1&pageSize=100&pageNumber=1"
)
_FILES_BASE = "https://vatseelabs-s3.kotakmf.com/"

# Regex to match portfolio entry labels like:
# "Consolidated Portfolio as on April 30, 2026"
_PORTFOLIO_RE = re.compile(
    r"(?:consolidated|monthly)\s+portfolio.*?"
    r"(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)"
    r"[\s,\-]+(?:(?P<day>\d{1,2})[\s,\-]+)?(?P<year>20\d{2})",
    re.IGNORECASE,
)


def _parse_portfolio_entries(entries: list[dict]) -> list[dict]:
    """Pure parse: filter to consolidated monthly entries, parse year/month.

    Each entry dict has keys: text, href (optional).
    Returns list of dicts with added year/month keys, sorted newest first.
    """
    results = []
    for entry in entries:
        text = entry.get("text", "")
        href = entry.get("href", "")
        combined = f"{text} {href}".lower()

        # Must be "consolidated" — skip fortnightly
        if "fortnightly" in combined:
            continue

        m = _PORTFOLIO_RE.search(combined)
        if not m:
            # Fallback: try generic month inference
            ym = try_infer(text, href)
            if ym and "consolidated" in combined:
                results.append({
                    **entry,
                    "year": ym[0],
                    "month": ym[1],
                })
            continue

        month_num = ALL_MONTHS.get(m.group("month").lower())
        if not month_num:
            continue
        year = int(m.group("year"))
        results.append({**entry, "year": year, "month": month_num})

    results.sort(key=lambda e: (e["year"], e["month"]), reverse=True)
    return results


def _parse_api_items(items: list[dict]) -> list[dict]:
    """Parse the Kotak API subHeaderList items into the standard entry format,
    then filter to consolidated monthly entries."""
    entries = []
    for item in items:
        title = item.get("subHeaderTitle", "")
        content = item.get("content", "")
        filename = item.get("fileName", "")
        if not title:
            continue
        # Build href from content path
        href = ""
        if content:
            href = _FILES_BASE + content
        entries.append({"text": title, "href": href, "filename": filename})
    return _parse_portfolio_entries(entries)


class Scraper(BaseScraper):
    PATTERN = "single_xlsx_multi_sheet"

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        # Use the browser engine with stealth to call the API
        host = "www.kotakmf.com"
        page = fetcher.browser.open_page(_API_URL, host)
        try:
            raw = page.evaluate("() => document.body?.innerText || ''")
        finally:
            try:
                page.close()
            except Exception:
                pass

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            raise ScraperError(f"Kotak: API response not JSON: {e}")

        items = data.get("subHeaderList") or []
        if not items:
            raise NoDataYetError("Kotak: empty subHeaderList from API")

        parsed = _parse_api_items(items)
        if not parsed:
            raise NoDataYetError("Kotak: no consolidated portfolio entries in API")

        latest = parsed[0]
        year = latest["year"]
        month = latest["month"]
        href = latest.get("href", "")
        text = latest.get("text", "")
        as_on = parse_as_on(text, href)

        self._download_url = href
        self._label = text or f"Consolidated Portfolio {year}-{month:02d}"
        return DiscoveryResult(year=year, month=month, as_on_date=as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = getattr(self, "_download_url", None)
        if url is None:
            self.discover_latest_month(fetcher)
            url = self._download_url

        if not url:
            raise ScraperError("Kotak: no download URL found")

        dest = fresh_dest(self.mf.id, "xlsx")
        # Files are hosted on S3 (vatseelabs-s3.kotakmf.com) — no browser
        # cookies needed; plain requests works and is faster.
        ok = fetcher.static.download_file(
            url, dest, "vatseelabs-s3.kotakmf.com",
            referer="https://www.kotakmf.com/Information/forms-and-downloads",
            expected_signatures=(),
        )
        if not ok:
            raise ScraperError(f"Kotak: download failed for {url[:140]}")
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=url,
            label=self.mf.name,
        )]
