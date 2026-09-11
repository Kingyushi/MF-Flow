"""mf40 Tata Mutual Fund — official AMC portfolio page (React Server Components payload).

Fixture: a trimmed copy of https://www.tatamutualfund.com/schemes-related/portfolio
captured 2026-09-12 — only the payload chunk that carries the portfolio list,
kept verbatim (197 rows back to 2010).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.config import MFConfig
from lib.fetcher import FetchResult
from scrapers.base import ScraperError
from scrapers.mf40_tata import (
    PORTFOLIO_URL,
    Scraper,
    is_month_end,
    parse_portfolio_entries,
    rsc_payload,
    title_date,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mf40" / "portfolio_page.html"
AUG_URL = (
    "https://betacms.tatamutualfund.com/system/files/2026-09/"
    "Monthly%20Portfolio%20as%20on%2031st%20August%202026.xlsx"
)
WORKBOOK = b"PK\x03\x04" + b"0" * 20000


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


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr("scrapers.base.time.sleep", lambda s: None)


# ----------------------------------------------------------------- pure parse

def test_is_month_end():
    assert is_month_end(date(2026, 8, 31))
    assert is_month_end(date(2024, 2, 29))
    assert not is_month_end(date(2026, 8, 30))
    assert not is_month_end(date(2017, 12, 15))


def test_title_date_variants():
    assert title_date("Portfolio as on 31st August, 2026") == date(2026, 8, 31)
    assert title_date("Portfolio as on 30th June 2026") == date(2026, 6, 30)
    assert title_date("Portfolio as on 29th February, 2024") == date(2024, 2, 29)
    assert title_date("Portfolio for the month of April 2010") is None
    assert title_date("Portfolio as on 31st Juny, 2026") is None


def test_rsc_payload_decodes_js_string_escapes():
    html = (
        '<script>self.__next_f.push([1,"a:[\\"x\\",{\\"k\\":\\"Monthly \\u0026 more\\"}]"])</script>'
        '<script nonce="abc">self.__next_f.push([1,"\\nb:tail"])</script>'
    )
    assert rsc_payload(html) == 'a:["x",{"k":"Monthly & more"}]\nb:tail'


def test_parse_entries_latest_is_august_2026():
    entries = parse_portfolio_entries(_html())
    latest = entries[0]
    assert latest.title == "Portfolio as on 31st August, 2026"
    assert latest.as_on == date(2026, 8, 31)
    assert latest.url == AUG_URL
    assert latest.section == "For the year 2026"


def test_parse_entries_are_consolidated_month_end_spreadsheets_only():
    entries = parse_portfolio_entries(_html())
    assert len(entries) >= 150
    for e in entries:
        assert is_month_end(e.as_on), e.title
        assert e.url.lower().rsplit("?", 1)[0].endswith((".xls", ".xlsx")), e.url
        assert "fund" not in e.title.lower(), e.title  # scheme-level one-offs excluded
    assert not any(e.as_on == date(2017, 12, 15) for e in entries)
    assert not any(e.url.lower().endswith(".pdf") for e in entries)


def test_parse_entries_newest_first_and_unique():
    entries = parse_portfolio_entries(_html())
    dates = [e.as_on for e in entries]
    assert dates == sorted(dates, reverse=True)
    assert len({e.url for e in entries}) == len(entries)
    months_2026 = [e.as_on.month for e in entries if e.as_on.year == 2026]
    assert months_2026 == [8, 7, 6, 5, 4, 3, 2, 1]


def test_parse_entries_empty_page():
    assert parse_portfolio_entries("<html><body>nothing here</body></html>") == []


# ------------------------------------------------------- scraper (fake fetcher)

class _FakeStatic:
    """Stands in for Fetcher.static. With `direct_blocked` only proxied calls succeed."""

    def __init__(self, html: str, body: bytes = WORKBOOK, *, direct_blocked: bool = False) -> None:
        self.html = html
        self.body = body
        self.direct_blocked = direct_blocked
        self.fetches: list[bool] = []
        self.downloads: list[tuple[str, str, bool]] = []  # (url, referer, force_proxy)

    def fetch_html(self, url, host, *, force_proxy=False):
        self.fetches.append(force_proxy)
        if self.direct_blocked and not force_proxy:
            return FetchResult(ok=False, url=url, engine="static", status_code=403, error="HTTP 403")
        return FetchResult(
            ok=True, url=url, final_url=url, html=self.html, status_code=200, engine="static", error=""
        )

    def download_file(self, url, dest, host, *, referer="", expected_signatures=(), force_proxy=False):
        self.downloads.append((url, referer, force_proxy))
        if self.direct_blocked and not force_proxy:
            return False
        dest.write_bytes(self.body)
        return True


def _fake_fetcher(static: _FakeStatic):
    def browser_download(*a, **k):
        raise AssertionError("browser fallback must not run in these scenarios")

    return SimpleNamespace(static=static, browser=SimpleNamespace(download_file=browser_download))


def test_discover_and_download_from_amc_page(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapers.mf40_tata.fresh_dest", lambda name, ext: tmp_path / f"{name}.{ext}")
    monkeypatch.setattr("scrapers.mf40_tata.proxy_available", lambda: False)
    static = _FakeStatic(_html())
    s = Scraper(_make_mf())
    res = s.discover_latest_month(_fake_fetcher(static))
    assert (res.year, res.month, res.as_on_date) == (2026, 8, date(2026, 8, 31))

    files = s.download(_fake_fetcher(static), res)
    assert len(files) == 1
    f = files[0]
    assert f.label == "Tata Mutual Fund" and f.scheme_name is None
    assert f.source_url == AUG_URL
    assert f.src_path.suffix == ".xlsx" and f.src_path.exists()
    assert static.downloads == [(AUG_URL, PORTFOLIO_URL, False)]
    assert static.fetches == [False]


def test_droplet_scenario_direct_blocked_retries_through_proxy(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapers.mf40_tata.fresh_dest", lambda name, ext: tmp_path / f"{name}.{ext}")
    monkeypatch.setattr("scrapers.mf40_tata.proxy_available", lambda: True)
    static = _FakeStatic(_html(), direct_blocked=True)
    s = Scraper(_make_mf())
    res = s.discover_latest_month(_fake_fetcher(static))
    assert (res.year, res.month) == (2026, 8)
    assert static.fetches == [False, True]
    files = s.download(_fake_fetcher(static), res)
    assert len(files) == 1 and files[0].src_path.exists()
    assert [c[2] for c in static.downloads] == [True]  # already known to need the proxy


def test_discover_raises_when_page_has_no_list(monkeypatch):
    monkeypatch.setattr("scrapers.mf40_tata.proxy_available", lambda: False)
    static = _FakeStatic("<html><body>maintenance</body></html>")
    s = Scraper(_make_mf())
    with pytest.raises(ScraperError, match="layout changed"):
        s.discover_latest_month(_fake_fetcher(static))


def test_discover_blocked_without_proxy_is_a_clear_error(monkeypatch):
    monkeypatch.setattr("scrapers.mf40_tata.proxy_available", lambda: False)
    static = _FakeStatic(_html(), direct_blocked=True)
    s = Scraper(_make_mf())
    with pytest.raises(ScraperError, match="portfolio page fetch failed"):
        s.discover_latest_month(_fake_fetcher(static))
    assert static.fetches == [False, False, False]


def test_download_rejects_non_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapers.mf40_tata.fresh_dest", lambda name, ext: tmp_path / f"{name}.{ext}")
    monkeypatch.setattr("scrapers.mf40_tata.proxy_available", lambda: False)
    static = _FakeStatic(_html(), body=b"<?xml version='1.0'?><Error><Code>AccessDenied</Code></Error>")
    s = Scraper(_make_mf())
    res = s.discover_latest_month(_fake_fetcher(static))
    with pytest.raises(ScraperError, match="not an Excel workbook"):
        s.download(_fake_fetcher(static), res)
