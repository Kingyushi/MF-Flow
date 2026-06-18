"""mf41 Taurus — parser test against real link patterns from the site.

The Taurus monthly-portfolio page after Drupal AJAX shows per-scheme xlsx links
with visible text like "Taurus Flexi Cap Fund" and URLs containing the month:
    .../Taurus_Flexi_Cap_Fund_Monthly_Portfolio_Report_Performance_April_2026.xlsx

The link text alone has no month info — the month is inferred from the URL by
month_hint.try_infer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf41_taurus import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf41" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf41",
        name="Taurus Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Taurus Flexi Cap Fund",
            "Taurus Large Cap Fund",
            "Taurus Mid Cap Fund",
            "Taurus ELSS Tax Saver Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf41_taurus",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    """Real fixture: links after Drupal year+month AJAX selection."""
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    assert (year, month) == (2026, 4)
    # 8 April 2026 portfolio links (all Taurus schemes).
    assert len(at_latest) == 8


def test_excludes_riskometer_and_factsheet() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    for fl in at_latest:
        combined = f"{fl.text}\n{fl.href}".lower()
        assert "riskometer" not in combined
        assert "factsheet" not in combined


def test_matched_schemes_against_filtered_links() -> None:
    """Scheme matching works for all 4 user schemes."""
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (_year, _month), at_latest = s._parse_links(links)
    pairs = [(fl.text, fl.href) for fl in at_latest]
    report = match_schemes(s.mf.schemes, pairs)
    assert report.matched_count == 4, (
        f"expected 4 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
