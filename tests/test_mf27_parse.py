"""Parse-only tests for mf27 Motilal Oswal scraper."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from scrapers.mf27_motilal_oswal import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf27" / "links.json"


def _make_scraper() -> Scraper:
    cfg = MFConfig(
        id="mf27", name="Motilal Oswal Mutual Fund",
        url="https://www.motilaloswalmf.com/downloads/scheme-portfolio-details",
        schemes=[], instructions="", pattern="single_xlsx_multi_sheet",
        module="scrapers.mf27_motilal_oswal",
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
    assert "PortfolioHolding_May" in at_latest[0].href


def test_excludes_fortnightly_and_factsheet():
    scraper = _make_scraper()
    links = _load_links()
    _, at_latest = scraper._parse_links(links)
    for fl in at_latest:
        h = fl.href.lower()
        assert "fortnightly" not in h
        assert "forthnightly" not in h
        assert "factsheet" not in h


def test_month_from_filename_not_folder():
    """Regression: Motilal republishes the month-end file under the NEXT month's
    folder (May-31 portfolio lives at .../2026/june/Scheme Portfolio Details
    31-05-2026.xlsx). The month must come from the filename's as-on date (May),
    not the '/june/' folder. Also exercises the space-separated filename that the
    old hyphen-only filter dropped."""
    scraper = _make_scraper()
    links = [
        # Republished May-end portfolio, sitting in the June folder, space-named.
        ("Scheme Portfolio Details May 2026",
         "https://www.motilaloswalmf.com/content/dam/motilal-mf/downloads/mf/month-end-portfolio/2026/june/Scheme%20Portfolio%20Details%2031-05-2026.xlsx"),
        # April folder actually holds March-end data (Motilal's mislabeling).
        ("Scheme Portfolio Details April 2026",
         "https://www.motilaloswalmf.com/content/dam/motilal-mf/downloads/mf/month-end-portfolio/2026/apr/b3b74-copy-of-portfolioholding_march-31-2026-3-.xlsx"),
        # A fortnightly in the same june folder must NOT win.
        ("Fortnightly Portfolio Report 31st May 2026",
         "https://www.motilaloswalmf.com/content/dam/motilal-mf/downloads/mf/month-end-portfolio/2026/june/Fortnightly%20Portfolio%20Report%20-31st%20May%202026.xlsx"),
    ]
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 5), f"Expected May (2026, 5), got {latest}"
    assert len(at_latest) == 1
    assert "31-05-2026" in at_latest[0].href
