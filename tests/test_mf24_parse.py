"""Parse test for mf24 LIC Mutual Fund — per-scheme xlsx via form interaction."""
import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf24_lic import Scraper, _parse_year_month_options, _parse_scheme_options

FIXTURES = Path(__file__).parent / "fixtures" / "mf24"

SCHEMES = [
    "LIC MF Flexi Cap Fund",
    "LIC MF Large & Midcap Fund",
    "LIC MF Multicap Fund",
    "LICMF Focused Fund",
    "LICMF Midcap Fund",
    "LICMF Smallcap Fund",
    "LICMF Largecap Fund",
    "LICMF Value Fund",
    "LIC MF Technology Fund",
]


def _make_mf():
    return MFConfig(
        id="mf24",
        name="LIC Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES,
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf24_lic",
    )


def test_parse_year_month_options():
    with open(FIXTURES / "links.json") as f:
        data = json.load(f)
    result = _parse_year_month_options(data["years"], data["months"])
    assert result == (2026, 5)


def test_parse_scheme_options():
    with open(FIXTURES / "links.json") as f:
        data = json.load(f)
    entries = _parse_scheme_options(data["scheme_options"])
    assert len(entries) == 11
    texts = [e.text for e in entries]
    assert any("Flexi Cap" in t for t in texts)
    assert any("Focused" in t for t in texts)


def test_scheme_matching():
    with open(FIXTURES / "links.json") as f:
        data = json.load(f)
    entries = _parse_scheme_options(data["scheme_options"])
    link_pairs = [(e.text, e.url or "") for e in entries]
    report = match_schemes(SCHEMES, link_pairs)
    assert len(report.matched) == 9
