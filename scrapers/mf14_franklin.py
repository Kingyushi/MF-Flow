"""Franklin Templeton Mutual Fund — Reports page with category filter.

Page is /reports — needs filter selection ("Monthly Portfolio Disclosure")
before xlsx links appear.
"""
from __future__ import annotations

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf14")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.franklintempletonindia.com/reports"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def navigate_to_portfolio(self, page) -> None:
        # Franklin has multiple <select> elements; the category select is
        # not always visible to Playwright (custom styling overlays it).
        # Mutate the value directly via JS and dispatch a change event.
        page.evaluate(
            r"""() => {
                const selects = [...document.querySelectorAll('select')];
                for (const s of selects) {
                    for (const o of s.options) {
                        if ((o.value||'').includes('Monthly Portfolio')) {
                            s.value = o.value;
                            s.dispatchEvent(new Event('change', { bubbles: true }));
                            return;
                        }
                    }
                }
            }"""
        )
        page.wait_for_timeout(5000)

    def find_target(self, page) -> Target:
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => (a.href||'').toLowerCase().endsWith('.xlsx'))
                .filter(a => {
                    const t = (a.innerText||'').toLowerCase() + ' ' + (a.href||'').toLowerCase();
                    return t.includes('monthly') && t.includes('portfolio');
                })
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        if not rows:
            raise NoDataYetError("Franklin: no Monthly Portfolio xlsx anchors")
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
            raise NoDataYetError("Franklin: could not parse any row date")
        return Target(
            year=best_d.year, month=best_d.month, label=best["text"],
            as_on=best_d, kind="url", payload=best["href"],
        )
