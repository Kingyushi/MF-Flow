"""Indian AMC date format tests."""
from __future__ import annotations

from datetime import date

from lib.month_hint import format_month, parse_as_on, try_infer


def test_try_infer_long_form():
    assert try_infer("May 2026") == (2026, 5)
    assert try_infer("January 2026") == (2026, 1)


def test_try_infer_short_form():
    assert try_infer("Apr-26") == (2026, 4)
    assert try_infer("may26") == (2026, 5)


def test_try_infer_iso_like():
    assert try_infer("2026-05") == (2026, 5)
    assert try_infer("202605") == (2026, 5)


def test_try_infer_picks_latest():
    assert try_infer("April 2026", "May 2026") == (2026, 5)


def test_parse_as_on_dashed():
    assert parse_as_on("31-May-2026") == date(2026, 5, 31)


def test_parse_as_on_slash():
    assert parse_as_on("31/05/2026") == date(2026, 5, 31)


def test_parse_as_on_ordinal():
    assert parse_as_on("as on 31st May, 2026") == date(2026, 5, 31)


def test_parse_as_on_iso():
    assert parse_as_on("2026-05-31") == date(2026, 5, 31)


def test_parse_as_on_month_first():
    assert parse_as_on("May 31, 2026") == date(2026, 5, 31)


def test_format_month():
    assert format_month(2026, 5) == "May 2026"
    assert format_month(2026, 1) == "January 2026"
