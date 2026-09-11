"""Tests for lib/month_guard.py — the phantom-month defense.

Incident being defended against (2026-08, mf02 Abakkus): a daily TREPS/debt
disclosure dated "August 03, 2026" was picked as the latest monthly portfolio
and recorded as the phantom month "August 2026", which would make the
September run skip the real August data.
"""
from datetime import date

from lib.month_guard import (
    check_discovered_month,
    is_completed_month,
    is_month_end,
    last_day_of_month,
)

TODAY = date(2026, 8, 14)  # the day of the real incident


def test_month_end_detection():
    assert is_month_end(date(2026, 7, 31))
    assert is_month_end(date(2026, 6, 30))
    assert is_month_end(date(2028, 2, 29))       # leap year
    assert not is_month_end(date(2026, 8, 3))    # the trap file's date
    assert not is_month_end(date(2026, 7, 15))   # fortnightly
    assert is_month_end(date(2026, 2, 28))       # 2026 is not a leap year
    assert not is_month_end(date(2028, 2, 28))   # 2028 is — Feb ends on the 29th
    assert last_day_of_month(2026, 2) == 28


def test_completed_month():
    # July is completed as of Aug 14.
    assert is_completed_month(2026, 7, TODAY)
    # August (current) and September (future) are not.
    assert not is_completed_month(2026, 8, TODAY)
    assert not is_completed_month(2026, 9, TODAY)
    assert not is_completed_month(2027, 1, TODAY)
    # Year boundary: December completed once January starts.
    assert is_completed_month(2025, 12, date(2026, 1, 1))
    assert not is_completed_month(2026, 1, date(2026, 1, 31))


def test_check_rejects_current_month_discovery():
    """The exact incident: discovery claimed 2026-08 on 2026-08-14."""
    ok, why = check_discovered_month(2026, 8, date(2026, 8, 3), TODAY)
    assert not ok
    assert "has not ended yet" in why


def test_check_accepts_previous_month():
    ok, why = check_discovered_month(2026, 7, date(2026, 7, 31), TODAY)
    assert ok, why


def test_check_accepts_september_run_for_august():
    """In September the REAL August portfolio must pass."""
    ok, why = check_discovered_month(2026, 8, date(2026, 8, 31), date(2026, 9, 5))
    assert ok, why


def test_check_rejects_future_and_garbage():
    assert not check_discovered_month(2026, 12, None, TODAY)[0]
    assert not check_discovered_month(2031, 5, None, TODAY)[0]     # "2031" misparse class
    assert not check_discovered_month(2014, 5, None, TODAY)[0]
    assert not check_discovered_month(2026, 0, None, TODAY)[0]


def test_check_rejects_as_on_outside_claimed_month():
    ok, why = check_discovered_month(2026, 6, date(2026, 7, 31), TODAY)
    assert not ok
    assert "does not fall inside" in why


# --- Second real incident: Capital Mind (mf11) upload-hash misparse ---------
# `CMMAAF_Monthly_Portfolio_Disclosure_June_2026_11dcac4356.xlsx` parsed as
# year=2026 mm=11 (the "11" of the hash "11dcac4356" glued to "2026_"),
# so the JUNE file was recorded as the phantom month "November 2026" on
# 2026-07-31, freezing Capital Mind's incremental skip until December.

def test_capital_mind_hash_url_parses_as_june():
    from lib.month_hint import try_infer
    url = ("https://capitalmindmf.com/uploads/"
           "CMMAAF_Monthly_Portfolio_Disclosure_June_2026_11dcac4356.xlsx")
    assert try_infer(url) == (2026, 6)


def test_numeric_yyyymm_still_parses_when_legitimate():
    from lib.month_hint import try_infer
    assert try_infer("portfolio_2026-07.xlsx") == (2026, 7)
    assert try_infer("portfolio_202607.pdf") == (2026, 7)
    assert try_infer("disclosure 07-2026 final") == (2026, 7)


def test_guard_would_have_caught_capital_mind_phantom():
    """Even without the parser fix, discovery claiming 2026-11 on 2026-07-31
    must be rejected by the runner guard."""
    ok, why = check_discovered_month(2026, 11, date(2026, 11, 1), date(2026, 7, 31))
    assert not ok
    assert "has not ended yet" in why
