"""Bank of India Mutual Fund — direct xlsx link list.

Page already shows "MONTHLY PORTFOLIO" section listing rows like
"MONTHLY-PORTFOLIO - 30-APRIL-2026" with direct .xlsx URLs.
"""
from __future__ import annotations

import re
from datetime import date

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, parse_as_on

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf08")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.boimf.in/investor-corner#t2"

    def dismiss_consent(self, page) -> None:
        # BoI's investor-corner page lazy-renders the data table.
        page.wait_for_timeout(6000)
        try:
            page.evaluate("() => document.querySelectorAll('.modal.show, #onload').forEach(m => m.remove())")
        except Exception:
            pass
        # Scroll to trigger lazy load of disclosure table.
        try:
            for _ in range(3):
                page.evaluate("() => window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(1500)
            page.evaluate("() => window.scrollTo(0, 0)")
        except Exception:
            pass

    def navigate_to_portfolio(self, page) -> None:
        # Make sure "Monthly Portfolio" sub-tab/heading is active.
        for sel in (
            'a:has-text("MONTHLY PORTFOLIO")',
            'button:has-text("MONTHLY PORTFOLIO")',
            'text="MONTHLY PORTFOLIO"',
        ):
            try:
                page.locator(sel).first.click(timeout=4_000)
                page.wait_for_timeout(2000)
                break
            except Exception:
                continue

    def find_target(self, page) -> Target:
        # Filter by URL containing monthly-portfolio (case-insensitive).
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => (a.href||'').toLowerCase().includes('.xlsx'))
                .filter(a => /monthly[-_ ]?portfolio/i.test(a.href||''))
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        if not rows:
            raise NoDataYetError("BoI: no MONTHLY-PORTFOLIO xlsx rows")
        best, best_d = None, None
        for r in rows:
            d = parse_as_on(r["text"], r["href"])
            if d and (best_d is None or d > best_d):
                best_d = d
                best = r
        if not best:
            raise NoDataYetError("BoI: could not parse date from any row")
        return Target(
            year=best_d.year, month=best_d.month, label=best["text"],
            as_on=best_d, kind="url", payload=best["href"],
        )
