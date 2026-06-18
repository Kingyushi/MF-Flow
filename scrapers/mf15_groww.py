"""Groww Mutual Fund — direct xlsx link, single file per month.

Page shows a "Portfolio" section with anchors like:
    "Monthly Portfolio- Apr 30, 2026.xlsx"
URL goes to assets-netstorage.growwmf.in/.../Monthly%20Portfolio-%20Apr%2030,%202026.xlsx

Pick the latest "Monthly Portfolio" link (NOT fortnightly).
"""
from __future__ import annotations

import re
from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf15")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://growwmf.in/statutory-disclosure/portfolio"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(4000)

    def find_target(self, page) -> Target:
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => /^Monthly Portfolio/i.test((a.innerText||'').trim()))
                .filter(a => /\.xlsx?$/i.test(a.href||''))
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        if not rows:
            raise NoDataYetError("Groww: no Monthly Portfolio anchor")
        best, best_d = None, None
        for r in rows:
            d = parse_as_on(r["text"], r["href"])
            if d and (best_d is None or d > best_d):
                best_d = d
                best = r
        if not best:
            raise NoDataYetError("Groww: could not parse any row date")
        return Target(
            year=best_d.year, month=best_d.month, label=best["text"],
            as_on=best_d, kind="url", payload=best["href"],
        )
