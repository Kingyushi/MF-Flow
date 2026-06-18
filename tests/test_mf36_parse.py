"""mf36 SAMCO — parser test against captured static-links fixture.

Fixture is real data from the probe output (link text is empty for all SAMCO
links; scheme info lives in the URL filename).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf36_samco import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf36" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf36",
        name="SAMCO Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Samco_Flexicap_Fund",
            "Samco Large Cap Fund",
            "Samco_Active_Momentum_Fund",
            "Samco_Special_Opportunities_Fund",
            "Samco_ Small_Cap_ Fund",
            "Samco Multi Cap Fund",
            "Samco Mid_Cap Fund",
            "Samco Large & Mid Cap Fund",
            "Samco ELSS Tax Saver Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf36_samco",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    assert (year, month) == (2026, 4)
    # April has links for ~11 schemes (all on www.samcomf.com domain only).
    assert len(at_latest) >= 9


def test_excludes_fortnightly_hy_and_media1() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (year, month), at_latest = s._parse_links(links)
    for fl in at_latest:
        assert "media1.samco.in" not in fl.href
        assert "fortnightly" not in fl.href.lower()
        assert "hy_portfolio" not in fl.href.lower()


def test_matched_schemes_against_filtered_links() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    (_year, _month), at_latest = s._parse_links(links)
    from urllib.parse import unquote
    from scrapers.mf36_samco import _split_camelcase
    pairs = [
        (_split_camelcase(unquote(fl.href.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " ")), fl.href)
        for fl in at_latest
    ]
    report = match_schemes(s.mf.schemes, pairs)
    # SAMCO has inconsistent naming (underscores, spaces, typos like "Apirl").
    # The fuzzy matcher should still match most schemes.
    assert report.matched_count >= 7, (
        f"expected >=7 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
