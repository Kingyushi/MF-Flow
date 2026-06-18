"""mf45 The Wealth Company Mutual Fund — parser test against probe fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf45_wealth_company import Scraper, _parse_visible_entries

FIXTURE = Path(__file__).parent / "fixtures" / "mf45" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf45",
        name="The Wealth Company Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Monthly - The Wealth Company Flexi Cap Fund",
            "Monthly - The Wealth Company Small Cap Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf45_wealth_company",
    )
    return Scraper(mf)


def test_parse_picks_april_2026():
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    ym, at_latest = _parse_visible_entries(entries)
    assert ym == (2026, 4)
    # April 2026 has 9 entries
    assert len(at_latest) == 9


def test_parse_excludes_march():
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    ym, at_latest = _parse_visible_entries(entries)
    for text, _ in at_latest:
        assert "march" not in text.lower()


def test_scheme_matching():
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    _, at_latest = _parse_visible_entries(entries)
    s = _scraper()
    # Match against (text, url) pairs
    report = match_schemes(s.mf.schemes, at_latest)
    assert report.matched_count >= 2, (
        f"expected >=2 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
