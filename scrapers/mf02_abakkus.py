"""Abakkus Mutual Fund — page may bot-block. Best-effort.

User instruction: "Go on monthly portfolio disclosure tab and download the
latest month. Output will be in xlsx with different sheets".
"""
from __future__ import annotations

import re

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError, ScraperError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf02")

# The Monthly Portfolio Disclosure rows render their visible text as
# "<Month> <DD>, <YYYY>" (e.g. "MAY 31, 2026"). This comma date format is unique
# to that section — Fortnightly rows read "15th May 2026" (no comma, day-first),
# Scheme Dashboard / AUM read "May 2026" (no day). Matching on it lets us find
# the latest month even when the AMC renames the file so the href no longer
# contains "monthly_portfolio" (which is exactly what happened for May 2026:
# .../Abakkus_Mutual_Fund_31_05_2026_*.xls).
_FULLDATE_TEXT = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.abakkusmf.com/statutory-disclosures.html"

    def dismiss_consent(self, page) -> None:
        # Page opens with a Bootstrap modal "#onload"; kill it before any clicks.
        page.wait_for_timeout(6000)
        title = (page.title() or "")
        if "Request Rejected" in title or "Access Denied" in title:
            raise ScraperError(f"Abakkus: site rejected request (title={title!r})")
        try:
            page.evaluate("() => { const m = document.getElementById('onload'); if (m) m.remove(); document.querySelectorAll('.modal-backdrop').forEach(b => b.remove()); document.body.classList.remove('modal-open'); }")
        except Exception:
            pass

    def navigate_to_portfolio(self, page) -> None:
        # Default tab on the page IS Monthly Portfolio Disclosures — no click needed.
        page.wait_for_timeout(1000)

    def find_target(self, page) -> Target:
        # Collect every spreadsheet anchor, then keep the Monthly Portfolio
        # rows. We identify them two ways (either is enough):
        #   - href still carries the legacy "monthly_portfolio" token, OR
        #   - visible text uses the section's "<Month> <DD>, <YYYY>" date format.
        # The text test survives the AMC renaming the file (May 2026 dropped the
        # "monthly_portfolio" token from its URL). Fortnightly/Dashboard/AUM rows
        # use different text shapes and so are excluded.
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => /\.xlsx?$/i.test(a.href||''))
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        rows = [
            r for r in rows
            if re.search(r"monthly[_\-]portfolio", r["href"] or "", re.IGNORECASE)
            or _FULLDATE_TEXT.search(r["text"] or "")
        ]
        if not rows:
            raise NoDataYetError("Abakkus: no MONTHLY_PORTFOLIO xlsx links")
        best, best_d = None, None
        from datetime import date as _date
        for r in rows:
            # Prefer the URL — Abakkus filenames encode "MONTHLY_PORTFOLIO_<DD>_<MM>_<YYYY>"
            # or "MONTHLY_PORTFOLIO_<Month>_<DD>_<YYYY>".
            d = parse_as_on(r["href"], r["text"])
            if not d:
                ym = try_infer(r["href"], r["text"])
                if ym:
                    d = _date(ym[0], ym[1], 1)
            if d and (best_d is None or d > best_d):
                best_d = d
                best = r
        if not best:
            raise NoDataYetError("Abakkus: could not parse any row date")
        return Target(
            year=best_d.year, month=best_d.month, label=best["text"],
            as_on=best_d, kind="url", payload=best["href"],
        )
