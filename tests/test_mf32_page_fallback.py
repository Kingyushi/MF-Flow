"""mf32 PGIM — GET-only page fallback used when the POST API is unreachable.

Background (2026-09-12): PGIM's AWS WAF answers 403 to datacenter IPs (the
droplet), and the residential proxy refuses POST (HTTP 402), so discovery
must work from the server-rendered page titles alone — through the proxy if
the direct GET is blocked as well. Fixture is a trimmed copy of the real page
(first tab, ten cards, SVGs stripped).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.config import MFConfig
from lib.fetcher import FetchResult
from scrapers.base import ScraperError
from scrapers.mf32_pgim import (
    Scraper,
    _parse_page_titles,
    _probe_entries_for_missing_schemes,
    file_url_for_title,
)

PAGE_FIXTURE = Path(__file__).parent / "fixtures" / "mf32" / "monthly_portfolio_page.html"
SCHEMES = [
    "PGIM INDIA SMALL CAP FUND",
    "PGIM INDIA MULTI CAP FUND",
    "PGIM INDIA MIDCAP FUND",
    "PGIM INDIA LARGE CAP FUND",
    "PGIM INDIA LARGE AND MIDCAP FUND",
    "PGIM INDIA FLEXI CAP FUND",
]


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf32",
        name="PGIM India Mutual Fund",
        url="https://www.pgimindia.com/mutual-funds/disclosures/Portfolios/Monthly-Portfolio",
        schemes=list(SCHEMES),
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf32_pgim",
    )
    return Scraper(mf)


def _page_html() -> str:
    return PAGE_FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr("scrapers.base.time.sleep", lambda s: None)


# ----------------------------------------------------------------- pure parse

def test_parse_page_titles_fixture():
    entries = _parse_page_titles(_page_html())
    assert len(entries) == 10
    assert {(e["year"], e["month"]) for e in entries} == {(2026, 8)}
    assert all(e["month_token"] == "Aug 2026" for e in entries)
    assert not any(e["probe"] for e in entries)
    lc = next(e for e in entries if e["title"] == "PGIM INDIA LARGE CAP FUND Aug 2026")
    assert lc["url"] == (
        "https://www.pgimindia.com/api/v1/brochure/about-us/image/PGIM INDIA LARGE CAP FUND Aug 2026.xlsx"
    )


def test_parse_page_titles_keeps_only_month_titles_and_sorts_newest_first():
    html = (
        '<label class="w-100 file-title">Scheme Information Document</label>'
        '<label class="w-100 file-title">PGIM INDIA X FUND Jul 2026</label>'
        '<label class="w-100 file-title">PGIM INDIA Y FUND August 2026</label>'
        '<label class="w-100 file-title">PGIM INDIA X FUND Jul 2026</label>'  # duplicate card
    )
    entries = _parse_page_titles(html)
    assert [e["title"] for e in entries] == ["PGIM INDIA Y FUND August 2026", "PGIM INDIA X FUND Jul 2026"]
    assert entries[0]["month_token"] == "August 2026"
    assert entries[1]["month"] == 7


def test_probe_entries_only_for_schemes_missing_from_page():
    entries = _parse_page_titles(_page_html())
    probes = _probe_entries_for_missing_schemes(SCHEMES, entries, "Aug 2026", 2026, 8)
    assert [p["title"] for p in probes] == ["PGIM INDIA MULTI CAP FUND Aug 2026"]
    assert probes[0]["probe"] is True
    assert probes[0]["url"] == file_url_for_title("PGIM INDIA MULTI CAP FUND Aug 2026")
    assert (probes[0]["year"], probes[0]["month"]) == (2026, 8)


# ------------------------------------------------------- scraper (fake fetcher)

class _Resp:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.ok = 200 <= status < 300

    def json(self):
        return {}


class _FakeStatic:
    """Stands in for Fetcher.static.

    The POST is blocked (403). GETs succeed directly unless `direct_blocked`,
    in which case only `force_proxy=True` requests succeed (droplet + WAF).
    """

    def __init__(self, html: str, *, direct_blocked: bool = False) -> None:
        self.html = html
        self.direct_blocked = direct_blocked
        self.posts = 0
        self.fetches: list[bool] = []          # force_proxy flag per fetch_html call
        self.downloads: list[tuple[str, tuple, bool]] = []  # (url, signatures, force_proxy)
        self.missing_substrings: tuple[str, ...] = ()

    def _session(self, host):
        return self

    def _polite(self, host):
        pass

    def post(self, *a, **k):
        self.posts += 1
        return _Resp(403)

    def fetch_html(self, url, host, *, force_proxy=False):
        self.fetches.append(force_proxy)
        if self.direct_blocked and not force_proxy:
            return FetchResult(ok=False, url=url, engine="static", status_code=403, error="HTTP 403")
        return FetchResult(
            ok=True, url=url, final_url=url, html=self.html, status_code=200, engine="static", error=""
        )

    def download_file(self, url, dest, host, *, referer="", expected_signatures=(), force_proxy=False):
        self.downloads.append((url, expected_signatures, force_proxy))
        if self.direct_blocked and not force_proxy:
            return False
        if any(s in url for s in self.missing_substrings):
            return False  # PGIM answers HTTP 204 / empty body for a file that is not there
        dest.write_bytes(b"PK\x03\x04fake")
        return True


def _fake_fetcher(static: _FakeStatic):
    def browser_download(*a, **k):
        raise AssertionError("browser fallback must not run in these scenarios")

    return SimpleNamespace(static=static, browser=SimpleNamespace(download_file=browser_download))


def test_discover_falls_back_to_page_when_api_is_blocked(monkeypatch):
    monkeypatch.setattr("scrapers.mf32_pgim.proxy_available", lambda: False)
    static = _FakeStatic(_page_html())
    s = _scraper()
    res = s.discover_latest_month(_fake_fetcher(static))
    assert (res.year, res.month) == (2026, 8)
    assert res.as_on_date is None
    assert static.posts == 1
    assert static.fetches == [False]
    titles = [e["title"] for e in s._entries]
    assert len(titles) == 11
    assert "PGIM INDIA MULTI CAP FUND Aug 2026" in titles


def test_download_keeps_real_files_and_reports_probe_without_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapers.mf32_pgim.fresh_dest", lambda name, ext: tmp_path / f"{name}.{ext}")
    monkeypatch.setattr("scrapers.mf32_pgim.proxy_available", lambda: False)
    static = _FakeStatic(_page_html())
    static.missing_substrings = ("MULTI CAP",)
    s = _scraper()
    files = s.download(_fake_fetcher(static), s.discover_latest_month(_fake_fetcher(static)))
    got = sorted(f.scheme_name for f in files)
    assert got == sorted(x for x in SCHEMES if x != "PGIM INDIA MULTI CAP FUND")
    assert s._download_failures == ["PGIM INDIA MULTI CAP FUND"]
    assert s._match_report.matched_count == 6
    probe_calls = [c for c in static.downloads if "MULTI CAP" in c[0]]
    assert probe_calls == [(file_url_for_title("PGIM INDIA MULTI CAP FUND Aug 2026"), (b"PK",), False)]
    assert all(c[1] == () and c[2] is False for c in static.downloads if "MULTI CAP" not in c[0])


def test_droplet_scenario_direct_blocked_retries_through_proxy(tmp_path, monkeypatch):
    """Server IP blocked for everything (403), proxy configured but pgimindia.com
    not in MF_FLOW_PROXY_HOSTS: API 403 -> page 403 -> page via proxy -> files via proxy."""
    monkeypatch.setattr("scrapers.mf32_pgim.fresh_dest", lambda name, ext: tmp_path / f"{name}.{ext}")
    monkeypatch.setattr("scrapers.mf32_pgim.proxy_available", lambda: True)
    static = _FakeStatic(_page_html(), direct_blocked=True)
    s = _scraper()
    res = s.discover_latest_month(_fake_fetcher(static))
    assert (res.year, res.month) == (2026, 8)
    assert static.fetches == [False, True]
    assert s._force_proxy is True

    files = s.download(_fake_fetcher(static), res)
    assert sorted(f.scheme_name for f in files) == sorted(SCHEMES)
    assert s._download_failures == []
    assert all(c[2] is True for c in static.downloads), "every file must go through the proxy"


def test_direct_blocked_without_proxy_is_a_clear_error(monkeypatch):
    monkeypatch.setattr("scrapers.mf32_pgim.proxy_available", lambda: False)
    static = _FakeStatic(_page_html(), direct_blocked=True)
    s = _scraper()
    with pytest.raises(ScraperError, match="disclosure page failed too"):
        s.discover_latest_month(_fake_fetcher(static))
    assert static.fetches == [False, False, False]  # 3 attempts, never a proxy retry


def test_download_retries_file_through_proxy_when_direct_download_blocked(tmp_path, monkeypatch):
    """Page came through directly, but the file host blocks the IP: retry via proxy."""
    monkeypatch.setattr("scrapers.mf32_pgim.fresh_dest", lambda name, ext: tmp_path / f"{name}.{ext}")
    monkeypatch.setattr("scrapers.mf32_pgim.proxy_available", lambda: True)
    static = _FakeStatic(_page_html())
    s = _scraper()
    res = s.discover_latest_month(_fake_fetcher(static))
    static.direct_blocked = True  # from now on only proxied downloads succeed
    files = s.download(_fake_fetcher(static), res)
    assert len(files) == 6
    assert s._force_proxy is True
    first_url = static.downloads[0][0]
    assert [c[2] for c in static.downloads if c[0] == first_url] == [False, True]
