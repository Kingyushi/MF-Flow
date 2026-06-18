"""Parse test for mf40 Tata Mutual Fund — single xlsx via advisorkhoj."""
import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf40_tata import Scraper

FIXTURES = Path(__file__).parent / "fixtures" / "mf40"


def _make_mf():
    return MFConfig(
        id="mf40",
        name="Tata Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "TATA BUSINESS CYCLE FUND",
            "TATA FLEXI CAP FUND",
            "TATA SMALL CAP FUND",
        ],
        instructions="",
        pattern="single_xlsx_multi_sheet",
        module="scrapers.mf40_tata",
    )


def test_parse_links_finds_latest_month():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 4)
    assert len(at_latest) == 1
    assert "April" in at_latest[0].text or "April" in at_latest[0].href


def test_parse_links_excludes_non_portfolio():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    _, at_latest = scraper._parse_links(links)
    for fl in at_latest:
        assert ".xlsx" in fl.href or ".xls" in fl.href
