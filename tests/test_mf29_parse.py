"""Parse test for mf29 Nippon India Mutual Fund — single xlsx via static links."""
import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf29_nippon import Scraper

FIXTURES = Path(__file__).parent / "fixtures" / "mf29"


def _make_mf():
    return MFConfig(
        id="mf29",
        name="Nippon India Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Nippon India Growth Mid Cap Fund",
            "Nippon India Small Cap Fund",
            "Nippon India Flexi Cap Fund",
        ],
        instructions="",
        pattern="single_xlsx_multi_sheet",
        module="scrapers.mf29_nippon",
    )


def test_parse_links_finds_latest_month():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 4)
    assert len(at_latest) == 1
    assert "MONTHLY-PORTFOLIO" in at_latest[0].href


def test_parse_links_excludes_fortnightly():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    _, at_latest = scraper._parse_links(links)
    for fl in at_latest:
        assert "FORTNIGHTLY" not in fl.href
        assert "Risk-Parameter" not in fl.href
