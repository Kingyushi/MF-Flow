"""mf32 PGIM India Mutual Fund — parser test against synthesized API fixture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf32_pgim import Scraper, _parse_disclosure_entries

FIXTURE = Path(__file__).parent / "fixtures" / "mf32" / "api_response.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf32",
        name="PGIM India Mutual Fund",
        url="https://www.pgimindia.com/mutual-funds/disclosures/Portfolios/Monthly-Portfolio",
        schemes=[
            "PGIM INDIA SMALL CAP FUND",
            "PGIM INDIA MULTI CAP FUND",
            "PGIM INDIA MIDCAP FUND",
            "PGIM INDIA LARGE CAP FUND",
            "PGIM INDIA LARGE AND MIDCAP FUND",
            "PGIM INDIA FLEXI CAP FUND",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf32_pgim",
    )
    return Scraper(mf)


def test_parse_disclosure_entries_equity_tab():
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entries = _parse_disclosure_entries(body["data"])
    # Should only have Equity tab entries, not Debt
    assert len(entries) >= 6
    for e in entries:
        assert "liquid" not in e["title"].lower(), "Debt fund should be excluded"


def test_parse_picks_latest_month():
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entries = _parse_disclosure_entries(body["data"])
    # Latest should be May 2026
    assert entries[0]["year"] == 2026
    assert entries[0]["month"] == 5


def test_parse_has_download_urls():
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entries = _parse_disclosure_entries(body["data"])
    for e in entries:
        assert e["url"], f"Entry {e['title']} has no URL"
        assert "pgimindia.com" in e["url"]


def test_scheme_matching():
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entries = _parse_disclosure_entries(body["data"])
    # Filter to latest month
    latest_y, latest_m = entries[0]["year"], entries[0]["month"]
    at_latest = [e for e in entries if e["year"] == latest_y and e["month"] == latest_m]

    s = _scraper()
    link_pairs = [(e["title"], e["url"]) for e in at_latest]
    report = match_schemes(s.mf.schemes, link_pairs)
    assert report.matched_count >= 5, (
        f"expected >=5 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
