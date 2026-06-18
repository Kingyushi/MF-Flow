"""Navi Mutual Fund — SPA-click, per-scheme xlsx via WP REST API.

The page at /mutual-fund/downloads/portfolio is a WordPress/Elementor site.
The portfolio files are fetched via a WP REST API:

    POST /wp-json/nv/v1/documents
    Headers: WP-NONCE: <nonce from navi_property global>
    Body: {financial_year, value (month name), category: "884", type: "Monthly", order: "DESC"}

Returns JSON: {success: true, data: [{title, url}, ...]}
where each item is a per-scheme xlsx download.

Mechanism (verified 2026-06-08):
1. Load the page to get the nonce from `navi_property.nonce`.
2. Determine the latest FY and month by trying the most recent FY first,
   then walking months backward until we get non-empty results.
3. Filter returned items to the wanted scheme names.

The _parse_scheme_entries method is extracted for test use with fixture data.
"""
from __future__ import annotations

import html
import re
from datetime import date
from typing import Optional

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_NAMES, parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf28")

# Indian financial year runs April-March. FY "2025-2026" covers April 2025 - March 2026.
# FY "2026-2027" covers April 2026 - March 2027.
_FY_MONTHS = [
    ("April", 4), ("May", 5), ("June", 6), ("July", 7),
    ("August", 8), ("September", 9), ("October", 10), ("November", 11),
    ("December", 12), ("January", 1), ("February", 2), ("March", 3),
]


def _fy_for_month(year: int, month: int) -> str:
    """Return the FY string for a given calendar year+month."""
    if month >= 4:
        return f"{year}-{year + 1}"
    else:
        return f"{year - 1}-{year}"


def _parse_scheme_entries(links: list[tuple[str, str]]) -> tuple[
    Optional[tuple[int, int]], list[tuple[str, str]]
]:
    """Pure parse: from (text, href) pairs, find latest month entries.

    Returns ((year, month), filtered_links) or (None, []).
    Links are expected to contain scheme names + dates in text/href.
    """
    candidates = []
    for text, href in links:
        h = (href or "").lower()
        # Must be xlsx
        if not (".xlsx" in h or ".xls" in h):
            continue
        # Skip non-monthly
        combined = f"{text} {href}".lower()
        if any(ex in combined for ex in (
            "fortnightly", "half year", "quarterly", "overlap",
        )):
            continue
        ym = try_infer(text, href)
        if ym:
            candidates.append((ym[0], ym[1], text, href))

    if not candidates:
        return None, []

    latest = max(candidates, key=lambda c: (c[0], c[1]))
    latest_ym = (latest[0], latest[1])
    at_latest = [(c[2], c[3]) for c in candidates if (c[0], c[1]) == latest_ym]
    return latest_ym, at_latest


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://navi.com/mutual-fund/downloads/portfolio"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def navigate_to_portfolio(self, page) -> None:
        """No visible navigation needed — we use the API directly."""
        pass

    def _call_api(self, page, fy: str, month_name: str) -> list[dict]:
        """Call the WP REST API for documents."""
        result = page.evaluate("""([fy, month]) => {
            return new Promise((resolve) => {
                jQuery.ajax({
                    url: navi_property.rest_url + 'nv/v1/documents',
                    type: 'POST',
                    dataType: 'json',
                    data: {
                        financial_year: fy,
                        value: month,
                        category: '884',
                        type: 'Monthly',
                        order: 'DESC'
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader('WP-NONCE', navi_property.nonce);
                    },
                    success: function(response) { resolve(response); },
                    error: function(xhr, status, error) {
                        resolve({success: false, error: error});
                    }
                });
            });
        }""", [fy, month_name])
        if result and result.get("success") and result.get("data"):
            return result["data"]
        return []

    def _api_items_to_links(self, items: list[dict]) -> list[tuple[str, str]]:
        """Convert API items to (text, href) pairs."""
        links = []
        for item in items:
            title = html.unescape(item.get("title", ""))
            url = item.get("url", "")
            if isinstance(url, list):
                url = url[0] if url else ""
            if isinstance(url, dict):
                # Sometimes url is {url: ..., title: ...}
                url = url.get("url", "")
            if url:
                links.append((title, url))
        return links

    def latest_month_label(self, page):
        """Find the latest month with data by walking FYs and months."""
        from datetime import datetime
        now = datetime.now()

        # Try current FY first, then previous FY
        current_fy = _fy_for_month(now.year, now.month)
        prev_year = int(current_fy.split("-")[0]) - 1
        prev_fy = f"{prev_year}-{prev_year + 1}"

        for fy in [current_fy, prev_fy]:
            fy_start_year = int(fy.split("-")[0])
            # Walk months from latest to earliest within this FY
            for month_name, month_num in reversed(_FY_MONTHS):
                # Calendar year for this month
                cal_year = fy_start_year if month_num >= 4 else fy_start_year + 1
                # Skip future months
                if (cal_year, month_num) > (now.year, now.month):
                    continue

                items = self._call_api(page, fy, month_name)
                if items:
                    links = self._api_items_to_links(items)
                    self._latest_links = links
                    # Parse as_on date from link texts
                    as_on = None
                    for text, href in links:
                        as_on = parse_as_on(text, href)
                        if as_on:
                            break
                    log.info("Navi: found %d items for %s %s (%d-%02d)",
                             len(items), fy, month_name, cal_year, month_num)
                    return cal_year, month_num, as_on

        raise NoDataYetError("Navi: no monthly portfolio data found via API")

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        links = getattr(self, "_latest_links", None)
        if links is None:
            # Re-discover
            self.latest_month_label(page)
            links = getattr(self, "_latest_links", [])

        return [SchemeEntry(text=text, url=href) for text, href in links]
