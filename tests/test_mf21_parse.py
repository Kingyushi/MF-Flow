"""mf21 Jio BlackRock — pure-function tests against the anchors captured from
the live page on 2026-09-25 (August 2026 selected): 16 xlsx links, one per
scheme, plus navigation anchors. The scraper must offer every xlsx link to the
scheme matcher (it used to take only the first one, the Arbitrage fund)."""
from __future__ import annotations

from datetime import date

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf21_jio_blackrock import (
    Scraper,
    _enumerate_months_newest_first,
    _fy_label,
    as_on_from_links,
    portfolio_links,
)

CDN = "https://cdnstorage-ddh3hqhvg3gyedd9.a02.azurefd.net/brcms/"
ANCHORS = [
    {"text": "Skip to main content", "href": "https://www.jioblackrockamc.com/statutory-disclosure/disclosures/monthly-portfolio-disclosure#main-content"},
    {"text": "JioBlackRock Arbitrage Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpnbl6-d8a68b.xlsx"},
    {"text": "JioBlackRock Nifty Smallcap 250 Index Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpuhga-6c8977.xlsx"},
    {"text": "JioBlackRock Nifty Next 50 Index Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttptnuy-48c0f5.xlsx"},
    {"text": "JioBlackRock Nifty Midcap 150 Index Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttqee57-339f0b.xlsx"},
    {"text": "JioBlackRock Overnight Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpwb9s-11afdf.xlsx"},
    {"text": "JioBlackRock Liquid Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpsfof-663c83.xlsx"},
    {"text": "JioBlackRock Sector Rotation Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpk4jt-205092.xlsx"},
    {"text": "JioBlackRock Large Cap Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttplzcg-dd7d34.xlsx"},
    {"text": "JioBlackRock Nifty 50 Index Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttqfgax-6344b7.xlsx"},
    {"text": "JioBlackRock Flexi Cap Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpooc1-43078c.xlsx"},
    {"text": "JioBlackRock Nifty 8-13 yr G-Sec Index Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpx8og-5cd68a.xlsx"},
    {"text": "JioBlackRock Money Market Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttpvge1-918871.xlsx"},
    {"text": "JioBlackRock Nifty 50 ETF-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttqq0cz-b27ac2.xlsx"},
    {"text": "JioBlackRock Ultra Short to Short Term Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mttqo5ds-9cc190.xlsx"},
    {"text": "JioBlackRock Short Term Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mtv8ks7e-97b22f.xlsx"},
    {"text": "JioBlackRock Mutual Fund-Monthly-Portfolio-31-08-2026", "href": CDN + "jioblackro-mtv8ptmz-6aaba2.xlsx"},
    {"text": "Home", "href": "https://www.jioblackrockamc.com/"},
]

SCHEMES = [
    "JioBlackRock Large Cap Fund",
    "JioBlackRock Flexi Cap Fund",
    "JioBlackRock Sector Rotation Fund",
]


def _scraper() -> Scraper:
    return Scraper(MFConfig(
        id="mf21", name="Jio BlackRock Mutual Fund", url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES, instructions="", pattern="per_scheme_xlsx",
        module="scrapers.mf21_jio_blackrock",
    ))


def test_portfolio_links_keeps_every_xlsx_in_page_order() -> None:
    links = portfolio_links(ANCHORS)
    assert len(links) == 16
    assert links[0][0].startswith("JioBlackRock Arbitrage Fund")
    assert all(h.endswith(".xlsx") for _t, h in links)


def test_three_equity_schemes_match_their_own_files() -> None:
    """The old scraper returned links[0] (Arbitrage) as THE file for the AMC;
    the per-scheme matcher must pick the three equity funds' own workbooks."""
    links = portfolio_links(ANCHORS)
    report = match_schemes(SCHEMES, links)
    assert report.matched_count == 3, report.summary("mf21", "Jio")
    by_scheme = {m.scheme_name: m.link_url for m in report.matched}
    assert by_scheme["JioBlackRock Large Cap Fund"].endswith("mttplzcg-dd7d34.xlsx")
    assert by_scheme["JioBlackRock Flexi Cap Fund"].endswith("mttpooc1-43078c.xlsx")
    assert by_scheme["JioBlackRock Sector Rotation Fund"].endswith("mttpk4jt-205092.xlsx")
    # and none of them is the Arbitrage or consolidated file
    assert not any(u.endswith(("mttpnbl6-d8a68b.xlsx", "mtv8ptmz-6aaba2.xlsx")) for u in by_scheme.values())


def test_as_on_comes_from_anchor_text() -> None:
    links = portfolio_links(ANCHORS)
    assert as_on_from_links(links, 2026, 8) == date(2026, 8, 31)
    # nothing parseable -> first of month
    assert as_on_from_links([("JioBlackRock Fund", "x.xlsx")], 2026, 8) == date(2026, 8, 1)


def test_list_scheme_entries_uses_links_of_chosen_month() -> None:
    s = _scraper()
    s._links = portfolio_links(ANCHORS)
    entries = s.list_scheme_entries(page=None)
    assert len(entries) == 16
    large = [e for e in entries if e.text.startswith("JioBlackRock Large Cap Fund")]
    assert len(large) == 1 and large[0].url.endswith("dd7d34.xlsx")


def test_fiscal_year_mapping_and_month_walk() -> None:
    assert _fy_label(2026, 8) == "2026-2027"
    assert _fy_label(2026, 2) == "2025-2026"
    walk = _enumerate_months_newest_first(date(2026, 9, 25))
    assert walk[:3] == [(2026, 9), (2026, 8), (2026, 7)]
    assert walk[-1] == (2026, 4)
