"""Jio BlackRock Mutual Fund — month-toggle until data appears, then ONE xlsx
per scheme.

Page has two AntD selects:
- "View by fiscal year": 2026-2027, 2025-2026, ...
- "View by month": January..December

The latest available month may not be the currently selected one — site shows
"No documents found." for empty selections. Iterate backward from the current
month until download links appear, switching fiscal year if needed.

Once a month has data the page lists one xlsx per scheme (16 links for
August 2026: Arbitrage, Large Cap, Flexi Cap, Sector Rotation, the index
funds, the debt funds, plus a consolidated "JioBlackRock Mutual Fund" file),
with anchor text like
    "JioBlackRock Large Cap Fund-Monthly-Portfolio-31-08-2026".
Until 2026-09-25 this scraper took the FIRST link only (the Arbitrage fund),
so the three equity schemes in the user's list were never downloaded. It is
now a per-scheme scraper: every xlsx link of the chosen month is offered to
the scheme matcher and the matched ones are downloaded, one file per scheme.

Indian fiscal year mapping:
- Months 4-12 of year Y belong to FY Y-(Y+1)
- Months 1-3 of year Y belong to FY (Y-1)-Y
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import MONTH_NAMES, parse_as_on

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf21")

MAX_BACKWARD_STEPS = 6


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


def portfolio_links(links: list[dict]) -> list[tuple[str, str]]:
    """Pure filter over the page's anchors: keep the xlsx portfolio links as
    (text, href) pairs, in page order. Anchors carry the scheme name in their
    text; the href is an opaque CDN name, so the text is what the matcher sees."""
    out: list[tuple[str, str]] = []
    for a in links:
        href = (a.get("href") or "").strip()
        text = (a.get("text") or "").strip()
        if ".xlsx" not in href.lower():
            continue
        out.append((text or href, href))
    return out


def as_on_from_links(links: list[tuple[str, str]], year: int, month: int) -> date:
    """The anchor text ends with the as-on date ("...-31-08-2026"); fall back to
    the first of the month when nothing parses."""
    for text, href in links:
        d = parse_as_on(text, href)
        if d and (d.year, d.month) == (year, month):
            return d
    return date(year, month, 1)


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.jioblackrockamc.com/statutory-disclosure/disclosures/monthly-portfolio-disclosure"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    # ---- month toggling (unchanged mechanics) ---------------------------------

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
        page.locator(f'.ant-select-selection-item:has-text("{current_text}")').first.click(timeout=10_000)
        page.wait_for_timeout(500)
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

    def links_for_month(self, page, token: str, year: int, month: int) -> list[tuple[str, str]]:
        """Select the month; return every xlsx (text, href) it lists, or []."""
        fy, mname = token.split("|", 1)
        cur_fy, cur_month = self._current_select_values(page)
        if cur_fy and cur_fy != fy:
            try:
                self._select_antd(page, cur_fy, fy)
            except Exception as e:
                log.info("Jio BlackRock: FY switch %r -> %r failed: %s", cur_fy, fy, e)
                return []
        _, cur_month = self._current_select_values(page)
        if cur_month and cur_month != mname:
            try:
                self._select_antd(page, cur_month, mname)
            except Exception as e:
                log.info("Jio BlackRock: month switch %r -> %r failed: %s", cur_month, mname, e)
                return []
        page.wait_for_timeout(2000)
        body = page.locator("body").inner_text(timeout=2000)
        if "No documents found" in body:
            log.info("Jio BlackRock: %s %s has no data", mname, fy)
            return []
        anchors = page.evaluate("""
            () => [...document.querySelectorAll('a')]
                .map(a => ({text: a.innerText.trim(), href: a.href}))
        """) or []
        return portfolio_links(anchors)

    # ---- per_scheme contract --------------------------------------------------

    def latest_month_label(self, page):
        months = self.available_months_newest_first(page)
        tried = 0
        for year, month, token in months:
            if tried >= MAX_BACKWARD_STEPS:
                log.warning("Jio BlackRock: hit MAX_BACKWARD_STEPS=%d", MAX_BACKWARD_STEPS)
                break
            tried += 1
            links = self.links_for_month(page, token, year, month)
            if links:
                self._links = links
                log.info("Jio BlackRock: %s %s lists %d xlsx files", token.split("|", 1)[1], year, len(links))
                return year, month, as_on_from_links(links, year, month)
        raise NoDataYetError(f"{self.mf.name}: no toggled month had data within {tried} steps")

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        return [SchemeEntry(text=t, url=h) for t, h in getattr(self, "_links", [])]
