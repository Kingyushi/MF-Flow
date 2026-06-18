"""Filename sanitization + collision-detection tests."""
from __future__ import annotations

import pytest

from lib.sanitize import assert_unique, safe_filename


def test_basic_safe_filename():
    assert safe_filename("HDFC Large Cap Fund") == "HDFC Large Cap Fund"


def test_strip_reserved_chars():
    assert safe_filename("Foo/Bar:Baz") == "Foo Bar Baz"
    assert safe_filename('Quote"Test') == "Quote Test"


def test_strip_trailing_dot_space():
    assert safe_filename("Foo. ") == "Foo"


def test_windows_reserved_name():
    assert safe_filename("CON") == "_CON"
    assert safe_filename("PRN.txt") == "_PRN.txt"


def test_empty_raises():
    with pytest.raises(ValueError):
        safe_filename("")
    with pytest.raises(ValueError):
        safe_filename("   ")


def test_hdfc_scheme_list_distinct_filenames():
    """HDFC's actual scheme list must not collide."""
    schemes = [
        "HDFC Value Fund",
        "HDFC Technology Fund",
        "HDFC Small cap Fund",
        "HDFC Pharma and Healthcare Fund",
        "HDFC Multicap Fund",
        "HDFC Midcap Fund",
        "HDFC Large Cap Fund",
        "HDFC Large and Mid cap fund",
        "HDFC Innovation Fund",
        "HDFC Focused Fund",
        "HDFC Flexi cap fund",
        "HDFC Equity Savings Fund",
    ]
    # Must not raise.
    assert_unique(schemes)


def test_collision_detection():
    with pytest.raises(ValueError, match="collision"):
        assert_unique(["HDFC Large Cap", "HDFC: Large Cap"])
