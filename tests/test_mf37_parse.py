"""Parse-only tests for mf37 SBI scraper."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf37_sbi import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf37" / "links.json"


def _make_scraper() -> Scraper:
    cfg = MFConfig(
        id="mf37", name="SBI Mutual Fund",
        url="https://www.sbimf.com/portfolios",
        schemes=[], instructions="", pattern="single_xlsx_multi_sheet",
        module="scrapers.mf37_sbi",
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
    # Only the descriptive-text link passes (the "Download" duplicate lacks include terms)
    assert len(at_latest) >= 1
    assert "31st-may-2026" in at_latest[0].href


def test_excludes_fortnightly():
    scraper = _make_scraper()
    links = _load_links()
    from scrapers.mf37_sbi import _INCLUDE, _EXCLUDE
    from scrapers.patterns.static_links_filter import filter_monthly_xlsx_links
    filtered = filter_monthly_xlsx_links(
        links, include_terms=_INCLUDE, exclude_terms=_EXCLUDE, include_either=False,
    )
    for fl in filtered:
        assert "fortnightly" not in fl.text.lower()
        assert "fortnightly" not in fl.href.lower()


def test_excludes_non_portfolio():
    """Factsheet, commission, SID, KIM, addendum PDFs should not appear."""
    scraper = _make_scraper()
    links = _load_links()
    from scrapers.mf37_sbi import _INCLUDE, _EXCLUDE
    from scrapers.patterns.static_links_filter import filter_monthly_xlsx_links
    filtered = filter_monthly_xlsx_links(
        links, include_terms=_INCLUDE, exclude_terms=_EXCLUDE, include_either=False,
    )
    for fl in filtered:
        href_lower = fl.href.lower()
        assert "factsheet" not in href_lower
        assert "commission" not in href_lower
        assert "sid" not in href_lower
        assert "addendum" not in href_lower
