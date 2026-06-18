"""Parse-only tests for mf35 Quantum scraper."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf35_quantum import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf35" / "links.json"


def _make_scraper() -> Scraper:
    cfg = MFConfig(
        id="mf35", name="Quantum Mutual Fund",
        url="https://www.quantumamc.com/portfolio/combined/-1/1/0/0",
        schemes=["Quantum Value Fund", "Quantum Small Cap Fund", "Quantum ELSS Tax Saver Fund"],
        instructions="", pattern="single_xlsx_multi_sheet",
        module="scrapers.mf35_quantum",
    )
    return Scraper(cfg)


def _load_links() -> list[tuple[str, str]]:
    with open(FIXTURE, encoding="utf-8") as f:
        return [tuple(pair) for pair in json.load(f)]


def test_picks_latest_month():
    scraper = _make_scraper()
    links = _load_links()
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 5), f"Expected (2026, 5), got {latest}"
    assert len(at_latest) == 1
    assert "fed58a77" in at_latest[0].href


def test_all_links_are_all_funds():
    scraper = _make_scraper()
    links = _load_links()
    from scrapers.patterns.static_links_filter import filter_monthly_xlsx_links
    filtered = filter_monthly_xlsx_links(
        links, include_terms=("all funds",), exclude_terms=(),
    )
    for fl in filtered:
        assert "all funds" in fl.text.lower()


def test_multiple_months_present():
    """Fixture has 20 months of data — all should parse."""
    scraper = _make_scraper()
    links = _load_links()
    from scrapers.patterns.static_links_filter import filter_monthly_xlsx_links
    filtered = filter_monthly_xlsx_links(
        links, include_terms=("all funds",), exclude_terms=(),
    )
    assert len(filtered) == 20
