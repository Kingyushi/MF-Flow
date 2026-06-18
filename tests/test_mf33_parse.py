"""Parse-only tests for mf33 Parag Parikh scraper."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf33_parag_parikh import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf33" / "links.json"


def _make_scraper() -> Scraper:
    cfg = MFConfig(
        id="mf33", name="Parag Parikh Mutual Fund",
        url="https://amc.ppfas.com/downloads/portfolio-disclosure/",
        schemes=[], instructions="", pattern="single_xlsx_multi_sheet",
        module="scrapers.mf33_parag_parikh",
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
    assert "April_30_2026" in at_latest[0].href


def test_only_consolidated():
    """Only 'Consolidated' links should pass the filter."""
    scraper = _make_scraper()
    links = _load_links()
    from scrapers.mf33_parag_parikh import _is_consolidated
    from scrapers.patterns.static_links_filter import filter_monthly_xlsx_links
    filtered = filter_monthly_xlsx_links(
        links, include_terms=(), exclude_terms=(),
        custom_filter=_is_consolidated,
    )
    for fl in filtered:
        assert fl.text.strip().lower() == "consolidated"


def test_handles_xls_extension():
    """Parag Parikh consolidated files are .xls (not .xlsx). Verify they pass."""
    scraper = _make_scraper()
    links = _load_links()
    latest, at_latest = scraper._parse_links(links)
    assert at_latest[0].href.split("?")[0].endswith(".xls")
