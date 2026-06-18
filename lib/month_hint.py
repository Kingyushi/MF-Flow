"""Month + date inference from text strings.

Covers Indian AMC formats: "May 2026", "31-May-2026", "May-26", "31/05/2026",
"as on 31st May, 2026". Returns either a (year, month) tuple or a full
date when a day component is present.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

MONTH_FULL = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
MONTH_SHORT = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
ALL_MONTHS = {**MONTH_FULL, **MONTH_SHORT}

_MONTH_NAME_PAT = "|".join(sorted(ALL_MONTHS.keys(), key=len, reverse=True))
_LB = r"(?<![A-Za-z])"

# 4-digit-year patterns. Run these first — if any of them produce candidates
# the 2-digit-year fallback is suppressed (otherwise day-of-month digits like
# "31" in "March_31_2026" get misparsed as YY=31 -> 2031).
_PATTERNS_4DIGIT: list[re.Pattern[str]] = [
    re.compile(
        rf"{_LB}(?P<month>{_MONTH_NAME_PAT})[ _\-.,]+(?P<year>20\d{{2}})(?![0-9])",
        re.IGNORECASE,
    ),
    re.compile(r"(?<![0-9])(?P<year>20\d{2})[ _\-.]?(?P<mm>0[1-9]|1[0-2])(?![0-9])"),
    re.compile(r"(?<![0-9])(?P<mm>0[1-9]|1[0-2])[ _\-.](?P<year>20\d{2})(?![0-9])"),
    # Day-Month-Year forms like "30 April 2026" or "30-Apr-2026"
    re.compile(
        rf"(?<![0-9])\d{{1,2}}[ _\-.,]+(?P<month>{_MONTH_NAME_PAT})[ _\-.,]+(?P<year>20\d{{2}})(?![0-9])",
        re.IGNORECASE,
    ),
]

# 2-digit year fallback patterns (only used if no 4-digit hit). The YY must
# fall in a plausible window (15-50 -> 2015..2050).
_PATTERNS_2DIGIT: list[re.Pattern[str]] = [
    re.compile(
        rf"{_LB}(?P<month>{_MONTH_NAME_PAT})[ _\-.]?(?P<yy>\d{{2}})(?![0-9])",
        re.IGNORECASE,
    ),
]

# Full-date extraction — used to capture "as on 31-May-2026" etc.
# Separators include underscore for filename formats like "April_30_2026".
_DATE_PATTERNS: list[re.Pattern[str]] = [
    # 31-May-2026, 31 May 2026, 31st May 2026, 31/May/2026, 30_April_2026
    re.compile(
        rf"(?<![0-9])(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[ \-/.,_]+(?P<month>{_MONTH_NAME_PAT})[ \-/.,_]+(?P<year>20\d{{2}})(?![0-9])",
        re.IGNORECASE,
    ),
    # May 31, 2026 / April_30_2026
    re.compile(
        rf"(?<![A-Za-z])(?P<month>{_MONTH_NAME_PAT})[ \-/.,_]+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[ \-/.,_]+(?P<year>20\d{{2}})(?![0-9])",
        re.IGNORECASE,
    ),
    # 31/05/2026, 31-05-2026, 31_05_2026
    re.compile(r"(?<![0-9])(?P<day>\d{1,2})[/\-._](?P<mm>0[1-9]|1[0-2])[/\-._](?P<year>20\d{2})(?![0-9])"),
    # 2026-05-31, 2026/05/31, 2026_05_31
    re.compile(r"(?<![0-9])(?P<year>20\d{2})[/\-._](?P<mm>0[1-9]|1[0-2])[/\-._](?P<day>\d{1,2})(?![0-9])"),
]


_FOUR_DIGIT_YEAR = re.compile(r"(?<![0-9])(20\d{2})(?![0-9])")
_MONTH_NAME_ANY = re.compile(rf"(?<![A-Za-z])({_MONTH_NAME_PAT})(?![A-Za-z])", re.IGNORECASE)


def _normalize_text(raw: str) -> str:
    """Lowercase and URL-decode so encoded "%2031" doesn't masquerade as a year."""
    s = raw.lower()
    # Replace URL escapes for whitespace + common separators with a space.
    s = re.sub(r"%20", " ", s)
    s = re.sub(r"%2[bdef]|%2c", " ", s)  # + , - . /
    return s


def try_infer(*texts: str) -> Optional[tuple[int, int]]:
    """Return (year, month_num) — LATEST across all hints — or None.

    Strategy:
    1. Run the 4-digit-year patterns. If any match, that's the answer.
    2. If a text contains BOTH a standalone 4-digit year AND a standalone
       month name, pair them (latest year + nearest month).
    3. Only fall back to 2-digit YY when no 4-digit year exists anywhere.
       This prevents day-of-month digits ("31" in "March_31_2026") from
       being misparsed as a year.

    Inputs are URL-decoded before parsing so "%2031" (space + day 31) doesn't
    masquerade as the year 2031.
    """
    candidates: list[tuple[int, int]] = []
    has_any_4digit = False
    for raw in texts:
        if not raw:
            continue
        s = _normalize_text(raw)
        if _FOUR_DIGIT_YEAR.search(s):
            has_any_4digit = True
        for pat in _PATTERNS_4DIGIT:
            for m in pat.finditer(s):
                gd = m.groupdict()
                year = int(gd["year"])
                if gd.get("month"):
                    month_num = ALL_MONTHS[gd["month"].lower()]
                elif gd.get("mm"):
                    month_num = int(gd["mm"])
                else:
                    continue
                if 2015 <= year <= 2099:
                    candidates.append((year, month_num))
    if candidates:
        return max(candidates)
    # Pair: 4-digit year + nearest month name in same text.
    if has_any_4digit:
        for raw in texts:
            if not raw:
                continue
            s = _normalize_text(raw)
            years = [(m.start(), int(m.group(1))) for m in _FOUR_DIGIT_YEAR.finditer(s)]
            months = [(m.start(), ALL_MONTHS[m.group(1).lower()]) for m in _MONTH_NAME_ANY.finditer(s)]
            if not years or not months:
                continue
            for y_pos, year in years:
                if not (2015 <= year <= 2099):
                    continue
                m_pos, m_num = min(months, key=lambda x: abs(x[0] - y_pos))
                candidates.append((year, m_num))
        if candidates:
            return max(candidates)
        return None
    # Fall back to 2-digit-year only if no 4-digit year exists anywhere.
    for raw in texts:
        if not raw:
            continue
        s = _normalize_text(raw)
        for pat in _PATTERNS_2DIGIT:
            for m in pat.finditer(s):
                gd = m.groupdict()
                yy = int(gd["yy"])
                if not (15 <= yy <= 50):
                    continue
                year = 2000 + yy
                month_num = ALL_MONTHS[gd["month"].lower()]
                candidates.append((year, month_num))
    if not candidates:
        return None
    return max(candidates)


def parse_as_on(*texts: str) -> Optional[date]:
    """Return the LATEST full date found across hints, or None."""
    candidates: list[date] = []
    for raw in texts:
        if not raw:
            continue
        s = _normalize_text(raw)
        for pat in _DATE_PATTERNS:
            for m in pat.finditer(s):
                gd = m.groupdict()
                year: Optional[int] = None
                month_num: Optional[int] = None
                day: Optional[int] = None
                if gd.get("year"):
                    year = int(gd["year"])
                if gd.get("month"):
                    month_num = ALL_MONTHS[gd["month"].lower()]
                elif gd.get("mm"):
                    month_num = int(gd["mm"])
                if gd.get("day"):
                    day = int(gd["day"])
                if year and month_num and day and 2015 <= year <= 2099 and 1 <= day <= 31:
                    try:
                        candidates.append(date(year, month_num, day))
                    except ValueError:
                        continue
    if not candidates:
        return None
    return max(candidates)


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_month(year: int, month: int) -> str:
    """Render (2026, 5) -> 'May 2026'."""
    return f"{MONTH_NAMES[month - 1]} {year}"
