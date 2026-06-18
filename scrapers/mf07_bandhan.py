"""Bandhan Mutual Fund — disclosures page with Portfolio sub-section.

Site uses Cloudflare/Akamai protection that may block initial probe. Page
renders dynamic content (Statutory Disclosures > Portfolio > Monthly).
"""
from __future__ import annotations

import re

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf07")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://bandhanmutual.com/downloads/other-disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(6000)

    def navigate_to_portfolio(self, page) -> None:
        # Bandhan nav has "Portfolio" then "Monthly and Half-yearly" submenu.
        for sel in (
            'a:has-text("Portfolio")',
            'button:has-text("Portfolio")',
        ):
            try:
                page.locator(sel).first.click(timeout=6_000)
                page.wait_for_timeout(2500)
                break
            except Exception:
                continue
        for sel in (
            'a:has-text("Monthly and Half-yearly")',
            'button:has-text("Monthly and Half-yearly")',
            'text=/Monthly and Half-yearly/i',
        ):
            try:
                page.locator(sel).first.click(timeout=6_000)
                page.wait_for_timeout(3000)
                break
            except Exception:
                continue

    def find_target(self, page) -> Target:
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => (a.href||'').toLowerCase().endsWith('.xlsx'))
                .filter(a => {
                    const t = (a.innerText||'').toLowerCase();
                    const h = (a.href||'').toLowerCase();
                    return t.includes('monthly') || h.includes('monthly');
                })
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        if not rows:
            raise NoDataYetError("Bandhan: no Monthly xlsx anchors")
        best, best_d = None, None
        from datetime import date as _date
        for r in rows:
            d = parse_as_on(r["text"], r["href"])
            if not d:
                ym = try_infer(r["text"], r["href"])
                if ym:
                    d = _date(ym[0], ym[1], 1)
            if d and (best_d is None or d > best_d):
                best_d = d
                best = r
        if not best:
            raise NoDataYetError("Bandhan: could not parse any row date")
        return Target(
            year=best_d.year, month=best_d.month, label=best["text"],
            as_on=best_d, kind="url", payload=best["href"],
        )
