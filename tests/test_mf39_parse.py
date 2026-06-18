"""Parse test for mf39 Sundaram Mutual Fund — single xlsx via form interaction."""
import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf39_sundaram import Scraper

FIXTURES = Path(__file__).parent / "fixtures" / "mf39"


def _make_mf():
    return MFConfig(
        id="mf39",
        name="Sundaram Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Sundaram Mid Cap Fund",
            "Sundaram Small Cap Fund",
            "Sundaram Multi Cap Fund",
        ],
        instructions="",
        pattern="single_xlsx_multi_sheet",
        module="scrapers.mf39_sundaram",
    )


def test_parse_links_finds_latest_month():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 4)
    assert len(at_latest) == 1
    assert "Equity" in at_latest[0].text or "Fund of Funds" in at_latest[0].text


def test_parse_links_excludes_debt_and_fortnightly():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    _, at_latest = scraper._parse_links(links)
    for fl in at_latest:
        assert "Debt" not in fl.text
        assert "Fortnightly" not in fl.text
