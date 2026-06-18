"""Trust Mutual Fund — single xlsx via API (React SPA).

The page at /disclosures?activeTab=portfolio-disclosures is a React SPA.
It loads disclosure data from `/api/api/Trust/GetData` which returns a
JSON array of all disclosure items. Monthly portfolio files have
`matching_slugs` containing "portfolio-monthly-disclosure".

Mechanism (verified 2026-06-08):
1. Page loads and fires multiple GetData API calls.
2. The 4th GetData call returns ~182 disclosure items with fields:
   title, uploaddate, slug, fileurl, disclosuretypes, matching_slugs.
3. Filter to items where matching_slugs contains "portfolio-monthly-disclosure"
   OR title contains "Monthly Portfolio Report".
4. Pick the latest by parsing the "as on DD.MM.YYYY" date from the title.
5. Download the fileurl (xlsx or xls).

No Playwright interaction needed — the API data comes in the initial page load.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf42")

# Pattern to extract date from titles like "TRUSTMF Monthly Portfolio Report as on 30.04.2026"
_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _parse_api_items(items: list[dict]) -> list[tuple[str, str, date]]:
    """Parse API items to (title, fileurl, as_on_date) triples.

    Filters to monthly portfolio items only.
    """
    results = []
    for item in items:
        title = item.get("title", "")
        fileurl = item.get("fileurl", "")
        slugs = item.get("matching_slugs", "")

        # Must be monthly portfolio
        is_monthly = "portfolio-monthly-disclosure" in slugs
        is_monthly_title = "monthly" in title.lower() and "portfolio" in title.lower()
        if not (is_monthly or is_monthly_title):
            continue

        # Must have a file URL
        if not fileurl:
            continue

        # Must be xlsx/xls
        if not (fileurl.lower().endswith(".xlsx") or fileurl.lower().endswith(".xls")):
            continue

        # Parse date from title
        m = _DATE_RE.search(title)
        if m:
            try:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                as_on = date(y, mo, d)
                results.append((title, fileurl, as_on))
                continue
            except ValueError:
                pass

        # Fallback: try_infer from title
        ym = try_infer(title)
        if ym:
            as_on_fallback = parse_as_on(title, fileurl)
            if as_on_fallback:
                results.append((title, fileurl, as_on_fallback))
            else:
                results.append((title, fileurl, date(ym[0], ym[1], 1)))

    return results


def _parse_links(links: list[tuple[str, str]]):
    """Pure parse step for backward compat with fixture tests.

    Returns (year, month, label, url) for the latest monthly xlsx.
    """
    xlsx_links = []
    for text, href in links:
        if not href:
            continue
        h = href.lower()
        if not (h.endswith(".xlsx") or h.endswith(".xls") or ".xlsx?" in h or ".xls?" in h):
            continue
        # Exclude fortnightly
        combined = f"{text}\n{href}".lower()
        if "fortnightly" in combined:
            continue
        ym = try_infer(text, href)
        if ym:
            xlsx_links.append((ym[0], ym[1], text, href))

    if not xlsx_links:
        raise NoDataYetError("Trust MF: no monthly xlsx links found")
    xlsx_links.sort()
    year, month, label, url = xlsx_links[-1]
    return year, month, label, url


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def navigate_to_portfolio(self, page) -> None:
        # No click needed — the API fires on page load.
        # Wait for the API responses to complete.
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Backward compat for tests using fixture links."""
        return _parse_links(links)

    def find_target(self, page) -> Target:
        # The React SPA uses POST /api/api/Trust/GetData with a JSON body.
        api_items = page.evaluate("""() => {
            return fetch('/api/api/Trust/GetData', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({
                    systemQueryFileName: 'disclosuresweb.xml',
                    tagName: 'GetDisclosureByType',
                    searchField: '',
                    searchValue: '',
                    sortField: 'uploaddate',
                    sortDirection: 'DESC',
                    replaceField: '_slug_',
                    replaceValue: 'portfolio-fortnightly-disclosure,portfolio-monthly-disclosure,portfolio-quarterly-disclosure,portfolio-half-yearly-disclosure'
                })
            })
            .then(r => r.json())
            .then(data => {
                const arr = data.resultSetArray || [];
                return arr.filter(item =>
                    (item.matching_slugs || '').includes('portfolio-monthly-disclosure') ||
                    (item.title && item.title.toLowerCase().includes('monthly') &&
                     item.title.toLowerCase().includes('portfolio'))
                ).map(item => ({
                    title: item.title,
                    fileurl: item.fileurl,
                    matching_slugs: item.matching_slugs,
                    uploaddate: item.uploaddate
                }));
            })
            .catch(e => []);
        }""")

        if api_items:
            parsed = _parse_api_items(api_items)
            if parsed:
                parsed.sort(key=lambda x: x[2])
                title, fileurl, as_on = parsed[-1]
                return Target(
                    year=as_on.year, month=as_on.month, label=title,
                    as_on=as_on, kind="url", payload=fileurl,
                )

        # Fallback: try collecting links from DOM (legacy path)
        hrefs = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        year, month, label, url = _parse_links([(t, h) for t, h in hrefs])
        as_on = parse_as_on(label, url)
        if not as_on:
            as_on = date(year, month, 1)
        return Target(year=year, month=month, label=label, as_on=as_on, kind="url", payload=url)
