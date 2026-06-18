"""UTI Mutual Fund — latest month zip via direct API.

The page at /downloads/consolidate-all-portfolio-disclosure is an Angular SPA
with custom dropdown components (not standard `<select>` elements). However,
the underlying data comes from a simple REST API:

    GET /api/get-consolidate-portfolio-disclosure?year=YYYY&month=MonthName

which returns JSON like:
    {"rows": [{"name": "Consolidated Portfolio May 2026",
               "url": "https://d3ce1o48hc5oli.cloudfront.net/.../fw_uti_mf_...zip",
               "type": "Zip", "month": "May", "year": "2026", ...}]}

Mechanism (verified 2026-06-08):
1. Try months from latest to earliest for the current year.
2. The first non-empty response's `rows[0].url` is the zip download URL.
3. No Playwright interaction needed — use static fetcher for the API call.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from lib.log import get_logger
from lib.month_hint import MONTH_NAMES, parse_as_on

from .base import NoDataYetError
from .patterns.zip_pattern import LatestMonthZipScraper

log = get_logger("mf44")

_API_URL = "https://www.utimf.com/api/get-consolidate-portfolio-disclosure"


def _parse_api_response(data: dict) -> Optional[tuple[str, str, Optional[date]]]:
    """Parse a single API response.

    Returns (zip_url, label_text, as_on_date) or None if no data.
    """
    rows = data.get("rows")
    if not rows:
        return None
    row = rows[0]
    url = row.get("url") or row.get("doc") or ""
    if not url:
        return None
    name = row.get("name", "")
    # Parse as_on from the URL (contains date like 31.05.2026)
    as_on = parse_as_on(name, url)
    return url, name, as_on


def _parse_zip_url(links: list[tuple[str, str]]):
    """Pure parse step for backward compat with fixture tests.

    Returns (url, label_text) or raises NoDataYetError.
    """
    for text, href in links:
        if not href:
            continue
        h = href.lower()
        if h.endswith(".zip") or ".zip?" in h:
            return href, text
    raise NoDataYetError("UTI: no zip download link found")


class Scraper(LatestMonthZipScraper):
    DISCLOSURES_URL = "https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_zip_url(self, links: list[tuple[str, str]]):
        """Backward compat for tests."""
        return _parse_zip_url(links)

    def find_latest_link(self, page):
        """Use API to find the latest consolidated portfolio zip.

        Tries the current year first, walking months from latest to earliest.
        Falls back to previous year if nothing found.
        """
        from datetime import datetime
        now = datetime.now()
        current_year = now.year

        for year in [current_year, current_year - 1]:
            # Months to try: from current month down to January
            months_to_try = list(range(12, 0, -1))
            if year == current_year:
                # Don't try months beyond current
                months_to_try = list(range(now.month, 0, -1))

            for month_num in months_to_try:
                month_name = MONTH_NAMES[month_num - 1]
                api_result = page.evaluate(
                    """([url, year, month]) => {
                        return fetch(url + '?year=' + year + '&month=' + month)
                            .then(r => r.json())
                            .catch(e => ({}));
                    }""",
                    [_API_URL, str(year), month_name]
                )

                if not api_result:
                    continue

                result = _parse_api_response(api_result)
                if result:
                    url, label, as_on = result
                    log.info("UTI: found %s %d -> %s", month_name, year, label)
                    return url, label, as_on

        raise NoDataYetError("UTI: no portfolio data found in API for any month")
