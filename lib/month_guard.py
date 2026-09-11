"""Plausibility guards for discovered portfolio months.

Incident (2026-08, mf02 Abakkus): the AMC added a new "Debt and money market
transactions" disclosure section whose rows render as "August 03, 2026" — the
same "<Month> <DD>, <YYYY>" comma-date text shape the Monthly Portfolio
section uses. The scraper matched that row, Aug 3 beat Jul 31 as "latest",
and a daily TREPS/debt file was downloaded and recorded on disk as the
phantom month "August 2026". The incremental skip would then treat August as
already collected and silently never fetch the REAL August portfolio when it
publishes in September.

Invariant enforced here: a monthly portfolio disclosure for month M can only
exist after M has fully ended (SEBI disclosures land in the first ~10 days of
M+1). Any discovery claiming the CURRENT or a FUTURE month is therefore bogus
by construction — no matter which AMC, page redesign, or mislabeled link
produced it. The runner applies this to every scraper as a last line of
defense; individual scrapers should ALSO filter implausible rows during
selection so they fall back to the newest plausible row instead of erroring.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def is_month_end(d: date) -> bool:
    """True iff d is the last calendar day of its month."""
    return d.day == last_day_of_month(d.year, d.month)


def is_completed_month(year: int, month: int, today: Optional[date] = None) -> bool:
    """True iff (year, month) lies strictly before the current calendar month.

    A portfolio "as on" the end of month M can only be published once M is
    over, so the current month and anything later cannot legitimately be the
    site's latest monthly portfolio.
    """
    t = today or date.today()
    return (year, month) < (t.year, t.month)


def check_discovered_month(
    year: int,
    month: int,
    as_on: Optional[date] = None,
    today: Optional[date] = None,
) -> tuple[bool, str]:
    """Validate a DiscoveryResult month. Returns (ok, reason_if_not_ok).

    Rejections:
      - year/month outside sane bounds (parser produced garbage), or
      - month not yet completed (current or future month) — see module
        docstring for why that is impossible for a real monthly portfolio.

    Deliberately NOT enforced here: as_on being the exact last day of its
    month. Most AMCs use calendar month-end, but this is left to individual
    scrapers (e.g. mf02) that know their site's convention, so a last-
    business-day AMC doesn't false-positive at the runner level.
    """
    t = today or date.today()
    if not (2015 <= year <= 2099) or not (1 <= month <= 12):
        return False, f"nonsense year/month ({year}, {month}) — date parser produced garbage"
    if not is_completed_month(year, month, t):
        return False, (
            f"month {year}-{month:02d} has not ended yet (today={t.isoformat()}); "
            "a monthly portfolio for it cannot exist — the page most likely "
            "contains a mislabeled or non-portfolio link (e.g. a daily debt/"
            "TREPS disclosure) that tricked date extraction"
        )
    if as_on is not None and (as_on.year, as_on.month) != (year, month):
        return False, (
            f"as_on date {as_on.isoformat()} does not fall inside claimed "
            f"month {year}-{month:02d} — inconsistent discovery"
        )
    return True, ""
