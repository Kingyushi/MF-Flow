"""mf42 Trust MF — parser test against links fixture.

Fixture contains real-format links from the Trust MF API/DOM.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from scrapers.mf42_trust import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf42" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf42",
        name="Trust Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "TRUSTMF Flexi Cap Fund",
            "TRUSTMF Small Cap Fund",
            "TRUSTMF Multi Cap Fund",
            "TRUSTMF Mid Cap Fund",
        ],
        instructions="",
        pattern="single_xlsx_multi_sheet",
        module="scrapers.mf42_trust",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    """Fixture: links from the Trust MF disclosure page."""
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    year, month, label, url = s._parse_links(links)
    assert (year, month) == (2026, 4)
    assert url.endswith(".xlsx")


def test_excludes_fortnightly_pdfs() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    year, month, label, url = s._parse_links(links)
    assert "fortnightly" not in url.lower()
    assert "fortnightly" not in label.lower()


def test_label_contains_april() -> None:
    """Label should reference April (the latest month in fixture)."""
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    year, month, label, url = s._parse_links(links)
    assert "30.04.2026" in label or "april" in label.lower()
