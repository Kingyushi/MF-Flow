"""mf26 Mirae Asset — parser test against captured static-links fixture."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf26_mirae_asset import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf26" / "links.json"

SCHEMES = [
    "Mirae Asset Flexicap Fund",
    "Mirae Asset Equity Savings Fund",
    "Mirae Asset Midcap Fund",
    "Mirae Asset Large & Midcap Fund",
    "Mirae Asset Healthcare Fund",
    "Mirae Asset Smallcap Fund",
    "Mirae Asset Focused Fund",
    "Mirae Asset Multicap Fund",
    "Mirae Asset Largecap Fund",
]


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf26",
        name="Mirae Asset Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES,
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf26_mirae_asset",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    assert (year, month) == (2026, 4)
    # Should have multiple April 2026 portfolio links, but ETF/fortnightly/half-year excluded
    assert len(at_latest) >= 8


def test_excludes_fortnightly_and_half_year() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (_year, _month), at_latest = s._parse_links(links)
    for fl in at_latest:
        assert "fortnightly" not in fl.text.lower()
        assert "half year" not in fl.text.lower()


def test_matched_schemes() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (_year, _month), at_latest = s._parse_links(links)
    pairs = [(fl.text, fl.href) for fl in at_latest]
    report = match_schemes(SCHEMES, pairs)
    # All 9 wanted schemes should match (fixture has them all)
    assert report.matched_count >= 9, (
        f"expected >=9 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
