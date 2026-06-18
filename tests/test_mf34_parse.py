"""mf34 Quant — parser test against real post-click fixture data."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf34_quant import Scraper, parse_scheme_entries

FIXTURE = Path(__file__).parent / "fixtures" / "mf34" / "links.json"

SCHEMES = [
    "quant Multi Cap Fund",
    "quant Large & Mid Cap Fund",
    "quant Small Cap Fund",
    "quant Focused Fund",
    "quant Mid Cap Fund",
    "quant Flexi cap Fund",
    "quant ELSS Tax Saver Fund",
    "quant Value Fund",
    "quant Large cap fund",
    "quant Business Cycle Fund",
    "quant Momentum Fund",
]


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf34",
        name="Quant Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES,
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf34_quant",
    )
    return Scraper(mf)


def test_parse_filters_xlsx_entries() -> None:
    """parse_scheme_entries returns all non-commission xlsx entries."""
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    filtered = parse_scheme_entries(entries, year=2026, month=4)
    # Should have 29 scheme entries (all non-commission)
    assert len(filtered) >= 20, f"expected >=20 entries, got {len(filtered)}"
    # None should be commission links
    for text, href in filtered:
        assert "commission" not in text.lower()
        assert "commission" not in href.lower()


def test_matched_schemes() -> None:
    """All 11 target schemes should match against real link data."""
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    filtered = parse_scheme_entries(entries, year=2026, month=4)
    report = match_schemes(SCHEMES, filtered)
    assert report.matched_count >= 11, (
        f"expected >=11 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )


def test_href_pattern() -> None:
    """Real hrefs follow /Admin/disclouser/<name>_<Mon>_<Year>.xlsx pattern."""
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    filtered = parse_scheme_entries(entries, year=2026, month=4)
    for _text, href in filtered:
        assert "/Admin/disclouser/" in href, f"unexpected href pattern: {href}"
        assert href.endswith(".xlsx"), f"expected .xlsx: {href}"
