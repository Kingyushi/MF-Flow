"""mf05 Axis Mutual Fund — parser tests for both API entries and link filtering."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapers.mf05_axis import Scraper, _parse_api_entries

FIXTURE_LINKS = Path(__file__).parent / "fixtures" / "mf05" / "links.json"
FIXTURE_API = Path(__file__).parent / "fixtures" / "mf05" / "api_entries.json"


# --- API entry parser tests ---

def test_api_parse_picks_latest_monthly_consolidated():
    entries = json.loads(FIXTURE_API.read_text(encoding="utf-8"))
    result = _parse_api_entries(entries)
    assert len(result) >= 2
    # Latest should be April 2026 (the monthly one, not May weekly or June daily)
    assert result[0]["_year"] == 2026
    assert result[0]["_month"] == 4


def test_api_parse_excludes_weekly_daily():
    entries = json.loads(FIXTURE_API.read_text(encoding="utf-8"))
    result = _parse_api_entries(entries)
    for r in result:
        name = r.get("field_pdf_name_statutory", "").lower()
        assert "weekly" not in name
        assert "daily" not in name


def test_api_parse_excludes_non_consolidated():
    entries = json.loads(FIXTURE_API.read_text(encoding="utf-8"))
    result = _parse_api_entries(entries)
    for r in result:
        assert r["field_aboutus_scheme_code"] == "Consolidated"


# --- Legacy link parser tests (kept for backward compat) ---

def test_parse_links_filters_monthly_portfolio_xlsx():
    links = [tuple(p) for p in json.loads(FIXTURE_LINKS.read_text(encoding="utf-8"))]
    result = Scraper._parse_links(links)
    # Should keep monthly portfolio xlsx, exclude fortnightly, factsheet pdf, half yearly
    assert len(result) >= 3
    for text, href in result:
        assert href.lower().endswith(".xlsx")
        combined = f"{text} {href}".lower()
        assert "fortnightly" not in combined
        assert "factsheet" not in combined
        assert "half year" not in combined


def test_parse_links_excludes_fortnightly():
    links = [tuple(p) for p in json.loads(FIXTURE_LINKS.read_text(encoding="utf-8"))]
    result = Scraper._parse_links(links)
    for text, href in result:
        assert "fortnightly" not in text.lower()
        assert "fortnightly" not in href.lower()


def test_parse_links_excludes_pdf():
    links = [tuple(p) for p in json.loads(FIXTURE_LINKS.read_text(encoding="utf-8"))]
    result = Scraper._parse_links(links)
    for text, href in result:
        assert not href.lower().endswith(".pdf")
