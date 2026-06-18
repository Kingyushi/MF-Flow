"""mf31 Old Bridge — parser test against captured static-links fixture.

Fixture is real data from the probe output (link hrefs are genuine, visible
text is "Download" for all links on this site).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf31_old_bridge import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf31" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf31",
        name="Old Bridge Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Old Bridge Flexi Cap Fund",
            "Old Bridge Focused Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf31_old_bridge",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    assert (year, month) == (2026, 4)
    # April 2026 should have 3 portfolio links (Flexi Cap, Arbitrage, Focused).
    assert len(at_latest) == 3


def test_excludes_half_yearly_and_non_portfolio() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    for fl in at_latest:
        assert "half_yearly" not in fl.href.lower()
        assert "financials" not in fl.href.lower()


def test_matched_schemes_against_filtered_links() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (_year, _month), at_latest = s._parse_links(links)
    # Build scheme-matching pairs from URL-decoded filenames.
    from urllib.parse import unquote
    pairs = [
        (unquote(fl.href.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " "), fl.href)
        for fl in at_latest
    ]
    report = match_schemes(s.mf.schemes, pairs)
    assert report.matched_count == 2, (
        f"expected 2 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
