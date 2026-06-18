"""mf22 JM Financial — parser test against captured static-links fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf22_jm_financial import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf22" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf22",
        name="JM Financial Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Monthly Portfolio - JM Small Cap Fund",
            "Monthly Portfolio - JM Midcap Fund",
            "Monthly Portfolio - JM Large Cap Fund",
            "Monthly Portfolio - JM Large and Midcap Fund",
            "Monthly Portfolio - JM Focused Fund",
            "Monthly Portfolio - JM Flexicap Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf22_jm_financial",
    )
    return Scraper(mf)


def test_parse_picks_may_2026() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    assert (year, month) == (2026, 5)
    # 6 fixture entries are May 2026 monthly portfolio; April + fortnightly + IAP excluded.
    assert len(at_latest) == 8


def test_matched_schemes_against_filtered_links() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (_year, _month), at_latest = s._parse_links(links)
    pairs = [(fl.text, fl.href) for fl in at_latest]
    report = match_schemes(s.mf.schemes, pairs)
    assert report.matched_count >= 5, f"expected >=5 matches, got {report.matched_count} (unmatched={report.unmatched_schemes!r})"
