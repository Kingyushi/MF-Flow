"""mf28 Navi Mutual Fund — parser test against links fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf28_navi import Scraper, _parse_scheme_entries

FIXTURE = Path(__file__).parent / "fixtures" / "mf28" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf28",
        name="Navi Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Navi Large & Midcap Fund",
            "Navi Flexi Cap Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf28_navi",
    )
    return Scraper(mf)


def test_parse_picks_april_2026():
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    ym, at_latest = _parse_scheme_entries(links)
    assert ym == (2026, 4)
    # Should have April entries
    assert len(at_latest) >= 2


def test_parse_excludes_fortnightly():
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    _, at_latest = _parse_scheme_entries(links)
    for text, href in at_latest:
        assert "fortnightly" not in text.lower()
        assert "fortnightly" not in href.lower()


def test_scheme_matching():
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    _, at_latest = _parse_scheme_entries(links)
    s = _scraper()
    report = match_schemes(s.mf.schemes, at_latest)
    assert report.matched_count >= 2, (
        f"expected >=2 matches, got {report.matched_count}"
    )
