"""mf44 UTI — parser test against links fixture.

Fixture contains real-format links from the UTI API response.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from scrapers.mf44_uti import Scraper
from scrapers.base import NoDataYetError

FIXTURE = Path(__file__).parent / "fixtures" / "mf44" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf44",
        name="UTI Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[],  # UTI is "all scheme" — no scheme filter.
        instructions="",
        pattern="latest_month_zip",
        module="scrapers.mf44_uti",
    )
    return Scraper(mf)


def test_parse_zip_url_picks_first_zip() -> None:
    """Fixture: zip URL parsing from API response links."""
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    s = _scraper()
    url, label = s._parse_zip_url(links)
    assert url.endswith(".zip")
    assert "May" in label or "April" in label


def test_parse_zip_url_ignores_non_zip() -> None:
    links = [
        ("Statement of Additional Information", "https://www.utimf.com/content/SAI.pdf"),
        ("Some other link", "https://www.utimf.com/content/other.html"),
    ]
    s = _scraper()
    with pytest.raises(NoDataYetError):
        s._parse_zip_url(links)


def test_parse_zip_url_with_empty_list() -> None:
    s = _scraper()
    with pytest.raises(NoDataYetError):
        s._parse_zip_url([])
