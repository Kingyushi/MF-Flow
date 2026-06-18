"""Quant Mutual Fund — per-scheme xlsx via Playwright click navigation.

Page structure (ASP.NET + jQuery AJAX):
- "MONTHLY PORTFOLIO - FUND - WISE" is a `div.statutory.disclouser` heading.
- Its sibling `div.accord-opns.innerclss` contains year tabs (`li.yearurl`)
  and a content div (`div.stat-cont-sub`).
- Clicking a year tab calls `submit_event1(year, category)` which POSTs to
  `/statutorydisclosures.aspx/displaydisclouser1` and injects month tabs.
- Clicking a month tab calls `submit_event2(monthNum, category, year)` which
  POSTs to `/statutorydisclosures.aspx/displaydisclouser2` and injects
  per-scheme xlsx links into `div#files`.

URL pattern: /Admin/disclouser/quant_<Scheme>_<Mon>_<Year>.xlsx
  (note: "disclouser" is the AMC's actual path, not a typo on our side)

For testability, `_parse_scheme_entries` accepts a list of (text, href) pairs
that the live scraper extracts from the DOM after the click sequence.
"""
from __future__ import annotations

import re
from datetime import date

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf34")

SECTION_CAT = "MONTHLY PORTFOLIO - FUND - WISE"

# Month abbreviation map for parsing hrefs like _Apr_2026.xlsx
_MON_ABBR = {v: k for k, v in {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}.items()}

# Regex to extract month abbreviation + year from href
_HREF_MY_RE = re.compile(r"_([A-Za-z]{3})_(\d{4})\.xlsx?$", re.IGNORECASE)


def parse_scheme_entries(
    entries: list[tuple[str, str]],
    year: int,
    month: int,
) -> list[tuple[str, str]]:
    """Pure parse: given (text, href) pairs from the post-click DOM,
    filter to xlsx links for the given year/month.

    The link text is just the scheme name (e.g. "quant Multi Cap Fund").
    The href contains month + year (e.g. /Admin/disclouser/..._Apr_2026.xlsx).

    Returns list of (text, href) pairs.
    """
    filtered = []
    for text, href in entries:
        if not href:
            continue
        if not re.search(r"\.xlsx?$", href, re.IGNORECASE):
            continue
        # Skip commission disclosures
        combined = f"{text}\n{href}".lower()
        if "commission" in combined:
            continue
        filtered.append((text, href))
    return filtered


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://quantmutual.com/statutory-disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def navigate_to_portfolio(self, page) -> None:
        """Click through: call submit_event1 for latest year,
        then submit_event2 for latest month."""
        cat = SECTION_CAT

        # Step 1: Find the section and get available years
        years = page.evaluate(r"""
            () => {
                const headings = [...document.querySelectorAll('div.statutory.disclouser')];
                const mpfw = headings.find(h =>
                    (h.innerText||'').trim().toUpperCase() === 'MONTHLY PORTFOLIO - FUND - WISE'
                );
                if (!mpfw) return [];
                const panel = mpfw.nextElementSibling;
                if (!panel) return [];
                const lis = [...panel.querySelectorAll('li.yearurl')];
                return lis
                    .map(li => parseInt((li.innerText||'').trim()))
                    .filter(y => y >= 2020 && y <= 2099);
            }
        """)
        if not years:
            raise NoDataYetError("Quant: no year tabs found in MONTHLY PORTFOLIO - FUND - WISE")

        latest_year = max(years)
        log.info("Quant: clicking year %d", latest_year)

        # Step 2: Call submit_event1 to load month tabs
        page.evaluate(
            f"() => submit_event1('{latest_year}', '{cat}')"
        )
        page.wait_for_timeout(3000)

        # Step 3: Find available months
        month_tabs = page.evaluate(f"""
            () => {{
                const el = document.getElementById('{cat}');
                if (!el) return [];
                const lis = [...el.querySelectorAll('li.yearurl, li')];
                return lis
                    .map(li => ({{id: li.id, text: (li.innerText||'').trim()}}))
                    .filter(m => /^\\d+$/.test(m.id) && parseInt(m.id) >= 1 && parseInt(m.id) <= 12);
            }}
        """)
        if not month_tabs:
            raise NoDataYetError(f"Quant: no month tabs found for year {latest_year}")

        latest_month_tab = max(month_tabs, key=lambda m: int(m["id"]))
        latest_month_num = int(latest_month_tab["id"])
        log.info("Quant: clicking month %s (%d)", latest_month_tab["text"], latest_month_num)

        # Step 4: Call submit_event2 to load scheme links
        page.evaluate(
            f"() => submit_event2('{latest_month_num}', '{cat}', '{latest_year}')"
        )
        page.wait_for_timeout(3000)

        # Store year/month for latest_month_label
        self._nav_year = latest_year
        self._nav_month = latest_month_num

    def latest_month_label(self, page):
        year = getattr(self, "_nav_year", None)
        month = getattr(self, "_nav_month", None)
        if not year or not month:
            return None

        # Collect xlsx links from the page
        raw = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .filter(a => /\\.xlsx?$/i.test(a.href))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []

        entries = parse_scheme_entries(raw, year, month)
        if not entries:
            return None

        self._scheme_entries = entries
        as_on = date(year, month, 1)
        return year, month, as_on

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        return [SchemeEntry(text=t, url=h) for t, h in self._scheme_entries]
