"""Capital Mind Mutual Fund — single xlsx (only 1 scheme: Capitalmind Flexi Cap).

User: "Click on monthly portfolio and then download the latest portfolio of
the latest month".

Page uses a Bootstrap '#onload' modal that blocks clicks — remove via JS.
URL pattern: CMFLEXI_Monthly_Portfolio_Disclosure_<Month>_<Year>.xlsx
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError, ScraperError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf11")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://capitalmindmf.com/statutory-disclosures.html"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(6000)
        title = (page.title() or "")
        if "Request Rejected" in title or "Access Denied" in title:
            raise ScraperError(f"Capital Mind: rejected (title={title!r})")
        try:
            page.evaluate(
                "() => { const m = document.getElementById('onload'); if (m) m.remove(); "
                "document.querySelectorAll('.modal-backdrop').forEach(b => b.remove()); "
                "document.body.classList.remove('modal-open'); }"
            )
        except Exception:
            pass

    def find_target(self, page) -> Target:
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => /\.xlsx?$/i.test(a.href||''))
                .filter(a => /Monthly_Portfolio_Disclosure/i.test(a.href||''))
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        if not rows:
            raise NoDataYetError("Capital Mind: no Monthly Portfolio xlsx anchors")
        best, best_d = None, None
        for r in rows:
            d = parse_as_on(r["href"], r["text"])
            if not d:
                ym = try_infer(r["href"], r["text"])
                if ym:
                    d = date(ym[0], ym[1], 1)
            if d and (best_d is None or d > best_d):
                best_d = d
                best = r
        if not best:
            raise NoDataYetError("Capital Mind: could not parse any URL date")
        return Target(
            year=best_d.year, month=best_d.month,
            label=best["text"] or "Capitalmind Flexi Cap Fund",
            as_on=best_d, kind="url", payload=best["href"],
        )
