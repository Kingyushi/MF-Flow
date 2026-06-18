"""Parse-only tests for mf25 Mahindra Manulife scraper."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf25_mahindra_manulife import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf25" / "links.json"


def _make_scraper() -> Scraper:
    cfg = MFConfig(
        id="mf25", name="Mahindra Manulife Mutual Fund",
        url="https://www.mahindramanulife.com/downloads",
        schemes=[], instructions="", pattern="single_xlsx_multi_sheet",
        module="scrapers.mf25_mahindra_manulife",
    )
    return Scraper(cfg)


def _load_links() -> list[tuple[str, str]]:
    with open(FIXTURE, encoding="utf-8") as f:
        return [tuple(pair) for pair in json.load(f)]


def test_picks_latest_month():
    scraper = _make_scraper()
    links = _load_links()
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 4), f"Expected (2026, 4), got {latest}"
    assert len(at_latest) == 1
    assert "b6705f83" in at_latest[0].href


def test_excludes_factsheet_and_commission():
    scraper = _make_scraper()
    links = _load_links()
    _, at_latest = scraper._parse_links(links)
    all_hrefs = [fl.href for fl in at_latest]
    for href in all_hrefs:
        assert "factsheet" not in href.lower()
        assert "commission" not in href.lower()


def test_excludes_non_xlsx():
    """PDF links (factsheet, forms) must not appear in filtered results."""
    scraper = _make_scraper()
    links = _load_links()
    from scrapers.mf25_mahindra_manulife import _INCLUDE, _EXCLUDE
    from scrapers.patterns.static_links_filter import filter_monthly_xlsx_links
    filtered = filter_monthly_xlsx_links(
        links, include_terms=_INCLUDE, exclude_terms=_EXCLUDE, include_either=False,
    )
    for fl in filtered:
        assert fl.href.endswith(".xlsx"), f"Non-xlsx in results: {fl.href}"
