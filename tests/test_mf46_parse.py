"""mf46 WhiteOak — parser test against real API-shaped fixture data."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf46_whiteoak import Scraper, parse_scheme_entries

FIXTURE = Path(__file__).parent / "fixtures" / "mf46" / "links.json"

SCHEMES = [
    "WhiteOak Capital Flexi Cap Fund",
    "WhiteOak Capital Mid Cap Fund",
    "WhiteOak Capital ELSS Tax Saver Fund",
    "WhiteOak Capital Multi Cap Fund",
    "WhiteOak Capital Large & Mid Cap Fund",
    "WhiteOak Capital Special Opportunities Fund",
    "WhiteOak Capital Digital Bharat Fund",
    "WhiteOak Capital Quality Equity Fund",
]


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf46",
        name="WhiteOak Capital Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES,
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf46_whiteoak",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (year, month), filtered = parse_scheme_entries(entries)
    assert (year, month) == (2026, 4), f"expected (2026, 4) got ({year}, {month})"
    # All 21 entries in the fixture are April 2026
    assert len(filtered) >= 8


def test_excludes_old_entries() -> None:
    # Add a March 2026 entry to verify filtering
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    entries.append((
        "WhiteOak Capital Flexi Cap Fund Monthly Portfolio Disclosure - 31st March2026",
        "https://content.whiteoakamc.com/WOC_Flexicap_Fund_March_2026_5e23fcb25e.xlsx",
    ))
    (year, month), filtered = parse_scheme_entries(entries)
    assert (year, month) == (2026, 4)
    for text, href in filtered:
        assert "March" not in text, f"March entry should be excluded: {text}"


def test_matched_schemes() -> None:
    entries = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (_year, _month), filtered = parse_scheme_entries(entries)
    report = match_schemes(SCHEMES, filtered)
    assert report.matched_count >= 8, (
        f"expected >=8 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
