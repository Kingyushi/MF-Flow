"""Jio BlackRock Mutual Fund — month-toggle until data appears.

Page has two AntD selects:
- "View by fiscal year": 2026-2027, 2025-2026, ...
- "View by month": January..December

The latest available month may not be the currently selected one — site shows
"No documents found." for empty selections. Iterate backward from the current
month until a download link appears, switching fiscal year if needed.

Indian fiscal year mapping:
- Months 4-12 of year Y belong to FY Y-(Y+1)
- Months 1-3 of year Y belong to FY (Y-1)-Y
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_NAMES

from .base import NoDataYetError
from .patterns.toggle import ToggleUntilDataScraper

log = get_logger("mf21")


def _fy_label(year: int, month: int) -> str:
    """Return Indian fiscal year string for a (year, month)."""
    if month >= 4:
        return f"{year}-{year + 1}"
    return f"{year - 1}-{year}"


def _enumerate_months_newest_first(today: date) -> list[tuple[int, int]]:
    """Return (year, month) tuples to try, newest first, going back ~6 months."""
    out = []
    y, m = today.year, today.month
    for _ in range(6):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


class Scraper(ToggleUntilDataScraper):
    DISCLOSURES_URL = "https://www.jioblackrockamc.com/statutory-disclosure/disclosures/monthly-portfolio-disclosure"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def available_months_newest_first(self, page) -> list[tuple[int, int, str]]:
        today = date.today()
        tuples = _enumerate_months_newest_first(today)
        # Pack (year, month, token) where token is "fy|monthname"
        out = []
        for y, m in tuples:
            fy = _fy_label(y, m)
            mname = MONTH_NAMES[m - 1]
            out.append((y, m, f"{fy}|{mname}"))
        return out

    def _select_antd(self, page, current_text: str, new_text: str):
        """Click an AntD select showing `current_text` and pick option `new_text`."""
        # Click the selection-item with current_text to open the dropdown.
        page.locator(f'.ant-select-selection-item:has-text("{current_text}")').first.click(timeout=10_000)
        page.wait_for_timeout(500)
        # Wait for any visible dropdown option
        page.wait_for_selector('.ant-select-item-option', timeout=10_000)
        page.locator(f'.ant-select-item-option:has-text("{new_text}")').first.click(timeout=10_000)
        page.wait_for_timeout(2500)

    def _current_select_values(self, page) -> tuple[str, str]:
        vals = page.evaluate(
            "() => [...document.querySelectorAll('.ant-select-selection-item')].map(e => e.innerText.trim())"
        )
        # First is fiscal year, second is month.
        if len(vals) >= 2:
            return vals[0], vals[1]
        return "", ""

    def link_for_month(self, page, token: str, year: int, month: int):
        fy, mname = token.split("|", 1)
        cur_fy, cur_month = self._current_select_values(page)
        # Set fiscal year if different.
        if cur_fy and cur_fy != fy:
            try:
                self._select_antd(page, cur_fy, fy)
            except Exception as e:
                log.info("Jio BlackRock: FY switch %r -> %r failed: %s", cur_fy, fy, e)
                return None
        # Re-read month after FY switch (may have changed automatically).
        _, cur_month = self._current_select_values(page)
        if cur_month and cur_month != mname:
            try:
                self._select_antd(page, cur_month, mname)
            except Exception as e:
                log.info("Jio BlackRock: month switch %r -> %r failed: %s", cur_month, mname, e)
                return None
        # Wait for content to render
        page.wait_for_timeout(2000)
        # Check for "No documents found" — bail
        body = page.locator("body").inner_text(timeout=2000)
        if "No documents found" in body:
            log.info("Jio BlackRock: %s %s has no data", mname, fy)
            return None
        # Find an xlsx link
        links = page.evaluate("""
            () => [...document.querySelectorAll('a')]
                .filter(a => (a.href||'').toLowerCase().includes('.xlsx'))
                .map(a => ({text: a.innerText.trim(), href: a.href}))
        """)
        if not links:
            return None
        # Pick the first xlsx link (typically the consolidated portfolio).
        chosen = links[0]
        as_on = date(year, month, 1)
        label = f"JioBlackRock - {mname} {year}"
        return (chosen["href"], label, as_on)
