"""Abakkus Mutual Fund — page may bot-block. Best-effort.

User instruction: "Go on monthly portfolio disclosure tab and download the
latest month. Output will be in xlsx with different sheets".

History of site tricks this scraper has survived (keep both defenses):

* June 2026 — AMC renamed the May file so the href lost its
  "monthly_portfolio" token; filtering on the token alone silently fell back
  to April. Fix: also accept rows whose visible text uses the section's
  "<Month> <DD>, <YYYY>" comma-date shape.
* August 2026 — AMC added a NEW "Debt and money market transactions" section
  whose rows ALSO render "August 03, 2026" comma-dates. The text heuristic
  matched it, Aug 3 beat Jul 31 as "latest", and a daily TREPS file was
  downloaded and recorded as the phantom month "August 2026" — which would
  make the incremental skip miss the real August portfolio forever.
  Fix, two independent layers:
    1. Scope anchor collection to the Monthly Portfolio container
       (div#mpdOutput) so other sections are never even seen. Whole-page
       scan remains only as a fallback for a future redesign.
    2. Date plausibility in row selection (_pick_monthly_row): monthly
       portfolios are as-on CALENDAR MONTH-END and can only exist for
       COMPLETED months. "August 03, 2026" fails both; "15th July" style
       fortnightly rows fail month-end. Implausible rows are logged and
       skipped so selection falls back to the newest plausible row.
  The runner additionally rejects any discovery claiming a not-yet-completed
  month (lib/month_guard.py) as a last line of defense for ALL scrapers.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lib.log import get_logger
from lib.month_guard import is_completed_month, is_month_end
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError, ScraperError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf02")

# The Monthly Portfolio Disclosure container on the statutory-disclosures
# page. Verified live 2026-08-14: monthly rows sit in div#mpdOutput;
# fortnightly = #fpOutput, scheme dashboard = #sdOutput, AUM = #maadOutput,
# daily debt/money-market transactions (the August 2026 trap) = #dmmtOutput.
_MONTHLY_SECTION_SELECTOR = "#mpdOutput"

# Comma-date shape used by Monthly Portfolio row text ("MAY 31, 2026").
# Fortnightly rows read "15th May 2026" (day-first, no comma), Dashboard/AUM
# read "May 2026" (no day). NOTE: since Aug 2026 this shape is NOT unique to
# the monthly section (daily debt rows use it too) — it is only a coarse
# pre-filter for the whole-page fallback; real safety comes from
# _pick_monthly_row's date checks.
_FULLDATE_TEXT = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)

_COLLECT_ANCHORS_JS = r"""
    (scope) => {
        const root = scope ? document.querySelector(scope) : document;
        if (!root) return null;
        return [...root.querySelectorAll('a')]
            .filter(a => /\.xlsx?$/i.test(a.href||''))
            .map(a => ({text: (a.innerText||'').trim(), href: a.href}));
    }
"""


def _pick_monthly_row(rows: list[dict], today: Optional[date] = None):
    """Pick the newest PLAUSIBLE monthly-portfolio row.

    Returns (row, as_on_date) or (None, None). A row is plausible when:
      * a date can be parsed from href/text, AND
      * its month is already completed (a monthly portfolio for the current
        or a future month cannot exist yet), AND
      * if a full date was parsed, it is a calendar month-end (Abakkus
        monthly files are always as-on month-end; daily debt files like
        "August 03, 2026" and fortnightly "15th July" rows fail this).
    Implausible rows are logged and skipped, so selection degrades to the
    newest genuine month instead of swallowing a trap row.
    """
    t = today or date.today()
    best, best_d = None, None
    for r in rows:
        full = parse_as_on(r.get("href") or "", r.get("text") or "")
        d = full
        if not d:
            ym = try_infer(r.get("href") or "", r.get("text") or "")
            if ym:
                d = date(ym[0], ym[1], 1)
        if not d:
            continue
        if full is not None and not is_month_end(full):
            log.warning(
                "mf02: rejecting row %r (as_on %s is not a month-end — "
                "not a monthly portfolio)", r.get("text"), full.isoformat(),
            )
            continue
        if not is_completed_month(d.year, d.month, t):
            log.warning(
                "mf02: rejecting row %r (month %d-%02d has not ended yet as of %s)",
                r.get("text"), d.year, d.month, t.isoformat(),
            )
            continue
        if best_d is None or d > best_d:
            best_d, best = d, r
    return best, best_d


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
        # Layer 1: only anchors inside the Monthly Portfolio container.
        rows = page.evaluate(_COLLECT_ANCHORS_JS, _MONTHLY_SECTION_SELECTOR)
        if not rows:
            # Fallback (container renamed/redesigned): whole-page scan with
            # the legacy filters. _pick_monthly_row still date-guards it.
            log.warning(
                "mf02: %s missing or empty — falling back to whole-page scan",
                _MONTHLY_SECTION_SELECTOR,
            )
            rows = page.evaluate(_COLLECT_ANCHORS_JS, None) or []
            rows = [
                r for r in rows
                if re.search(r"monthly[_\-]portfolio", r["href"] or "", re.IGNORECASE)
                or _FULLDATE_TEXT.search(r["text"] or "")
            ]
        if not rows:
            raise NoDataYetError("Abakkus: no MONTHLY_PORTFOLIO xlsx links")
        best, best_d = _pick_monthly_row(rows)
        if not best:
            raise NoDataYetError(
                "Abakkus: no row with a plausible completed month-end date "
                f"among {len(rows)} candidate link(s)"
            )
        return Target(
            year=best_d.year, month=best_d.month, label=best["text"],
            as_on=best_d if is_month_end(best_d) else None,
            kind="url", payload=best["href"],
        )
