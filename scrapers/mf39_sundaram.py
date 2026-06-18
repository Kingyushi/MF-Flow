"""Sundaram Mutual Fund — single multi-sheet xlsx via form interaction.

Page has a category dropdown (Monthly/Fortnightly/AdHoc) and a "View"
button. After selecting "Monthly Portfolio" and clicking View, an AJAX
call populates a Bootstrap accordion with year-wise sections. Each year
has month tabs; each month tab has xlsx links. The target is the link
titled "Monthly Portfolio Disclosure Equity and Fund of Funds"
(or similar "Equity" link) for the latest available month.

Mechanism (verified 2026-06-08):
1. select_option('#Cbx_Category', 'Monthly') + click "View"
2. AJAX call to `GetCategory` populates `#MonthAdhoc` accordion.
3. Expand the first (latest) accordion year item.
4. The first visible month tab is already active.
5. Collect all xlsx links in the active tab-pane.
6. Filter to "Equity" or "Fund of Funds" link.

The _parse_links method is extracted for test use with fixture data.
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf39")


def _equity_fof_filter(text: str, href: str) -> bool:
    """Keep only links about equity/FoF monthly portfolio disclosure."""
    t = text.lower()
    return "equity" in t or "fund of funds" in t


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.sundarammutual.com/Monthly-Fortnightly-Adhoc-Portfolios"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def navigate_to_portfolio(self, page) -> None:
        page.select_option("#Cbx_Category", "Monthly")
        page.wait_for_timeout(1000)
        # Click View button (may be input[type="button"] or regular button)
        page.evaluate("""() => {
            const btns = [...document.querySelectorAll('input[type="button"], button, a')];
            const view = btns.find(b => (b.value||b.innerText||'').trim() === 'View');
            if (view) view.click();
        }""")
        page.wait_for_timeout(8000)
        # Expand the first (latest-year) accordion item
        page.evaluate("""() => {
            const acc = document.querySelector('#MonthAdhoc');
            if (!acc) return;
            const btn = acc.querySelector('.accordion-button');
            if (btn && btn.classList.contains('collapsed')) btn.click();
        }""")
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=("monthly portfolio",),
            include_either=True,
            custom_filter=_equity_fof_filter,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Sundaram: no monthly portfolio equity/FoF links found")
        return latest, at_latest

    def find_target(self, page) -> Target:
        # Collect links from the expanded accordion
        hrefs = page.evaluate("""() => {
            // First try: links inside the active tab-pane of the accordion
            const acc = document.querySelector('#MonthAdhoc');
            if (acc) {
                const activePane = acc.querySelector('.tab-pane.active, .tab-pane.show');
                if (activePane) {
                    return Array.from(activePane.querySelectorAll('a[href]'))
                        .map(a => [(a.innerText || a.textContent || '').trim(), a.href]);
                }
                // Fallback: all links inside the accordion
                return Array.from(acc.querySelectorAll('a[href]'))
                    .map(a => [(a.innerText || a.textContent || '').trim(), a.href]);
            }
            // Final fallback: all page links
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href]);
        }""") or []
        latest, at_latest = self._parse_links([(t, h) for t, h in hrefs])
        year, month = latest
        fl = at_latest[0]
        as_on = parse_as_on(fl.text, fl.href)
        if not as_on:
            as_on = date(year, month, 1)
        return Target(
            year=year, month=month, label=fl.text,
            as_on=as_on, kind="url", payload=fl.href,
        )
