"""mf23 Kotak Mutual Fund — parser test against synthesized fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapers.mf23_kotak import _parse_portfolio_entries

FIXTURE = Path(__file__).parent / "fixtures" / "mf23" / "api_response.json"


def test_parse_filters_consolidated_and_picks_latest():
    entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = _parse_portfolio_entries(entries)
    # Should have 3 consolidated entries (May, April, March), no fortnightly
    assert len(result) == 3
    for r in result:
        assert "fortnightly" not in r["text"].lower()
    # Latest should be May 2026
    assert result[0]["year"] == 2026
    assert result[0]["month"] == 5


def test_parse_excludes_fortnightly():
    entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = _parse_portfolio_entries(entries)
    for r in result:
        assert "fortnightly" not in r["text"].lower()


def test_parse_extracts_year_month():
    entries = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = _parse_portfolio_entries(entries)
    years_months = [(r["year"], r["month"]) for r in result]
    assert (2026, 5) in years_months
    assert (2026, 4) in years_months
    assert (2026, 3) in years_months
