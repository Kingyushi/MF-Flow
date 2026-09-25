"""Tests for scheme matching — the HDFC large-vs-large+mid trap is the
canary in this coal mine."""
from __future__ import annotations

from lib.scheme_filter import match_schemes, normalize


def test_normalize_basic():
    # normalize collapses case + punctuation + plan suffixes, and joins
    # common compound tokens ("Large Cap" -> "largecap") so they survive
    # tokenization. The "fund" token is dropped later in _tokens().
    assert normalize("HDFC Large Cap Fund") == "hdfc largecap fund"
    assert normalize("HDFC Large Cap Fund - Direct Plan (G)") == "hdfc largecap fund"
    assert normalize("HDFC Large Cap Fund - Direct Plan - Growth Option") == "hdfc largecap fund"


def test_normalize_em_dash_prefix():
    # Canara Robeco rows in user's xlsx have "MF – Canara Robeco Multi Cap Fund"
    assert "canara robeco multicap" in normalize("MF – Canara Robeco Multi Cap Fund ")


def test_normalize_formerly_known_as():
    assert normalize(
        "Franklin India Mid Cap Fund (Formerly known as Franklin India Prima Fund) ^"
    ) == "franklin india midcap fund"


def test_midcap_variants_match():
    """User says "HDFC Midcap Fund"; HDFC site lists "HDFC Mid Cap Fund".
    The compound-token collapse must normalize both to the same tokens."""
    schemes = ["HDFC Midcap Fund"]
    site_links = [("HDFC Mid Cap Fund - Direct Plan", "https://hdfc.example/midcap.xlsx")]
    report = match_schemes(schemes, site_links)
    assert report.matched_count == 1, f"unmatched: {report.unmatched_schemes}"


def test_jm_large_and_midcap_one_word_variants_match():
    """JM: user xlsx says 'JM Large and Midcap Fund', site files have said both
    'JM Large and Midcap Fund' and 'JM Large & Mid Cap Fund' (2026-09-25).
    All spellings must collapse to the same 'largemidcap' token, and the plain
    'JM Large Cap Fund' must NOT match a large-and-midcap link."""
    links = [
        ("Monthly Portfolio - JM Large & Mid Cap Fund - Aug 31, 2026", "u-lmc"),
        ("Monthly Portfolio - JM Large Cap Fund - Aug 31, 2026", "u-lc"),
    ]
    r = match_schemes(["Monthly Portfolio - JM Large and Midcap Fund", "Monthly Portfolio - JM Large Cap Fund"], links)
    got = {m.scheme_name: m.link_url for m in r.matched}
    assert got == {
        "Monthly Portfolio - JM Large and Midcap Fund": "u-lmc",
        "Monthly Portfolio - JM Large Cap Fund": "u-lc",
    }
    for variant in ("JM Large and Midcap Fund", "JM Large & Midcap Fund", "JM Large Midcap Fund", "JM Large and Mid Cap Fund"):
        assert "largemidcap" in normalize(variant), variant


def test_hdfc_large_vs_large_and_mid():
    """The critical trap: HDFC Large Cap must NOT steal the HDFC Large and
    Mid cap fund link, and vice-versa."""
    schemes = ["HDFC Large Cap Fund", "HDFC Large and Mid cap fund"]
    site_links = [
        ("HDFC LARGE CAP FUND - Direct Plan", "https://hdfc.example/largecap.xlsx"),
        ("HDFC Large and Mid Cap Fund - Direct Plan", "https://hdfc.example/largemid.xlsx"),
    ]
    report = match_schemes(schemes, site_links)
    assert report.total_schemes == 2
    assert report.matched_count == 2
    by_scheme = {m.scheme_name: m.link_url for m in report.matched}
    assert by_scheme["HDFC Large Cap Fund"] == "https://hdfc.example/largecap.xlsx"
    assert by_scheme["HDFC Large and Mid cap fund"] == "https://hdfc.example/largemid.xlsx"


def test_hdfc_large_only_link_no_largemid_scheme():
    """If only "HDFC Large and Mid Cap" link exists, "HDFC Large Cap" scheme
    must NOT match it (contiguous-subseq rule)."""
    schemes = ["HDFC Large Cap Fund"]
    site_links = [
        ("HDFC Large and Mid Cap Fund - Direct Plan", "https://hdfc.example/largemid.xlsx"),
    ]
    report = match_schemes(schemes, site_links)
    assert report.matched_count == 0
    assert report.unmatched_schemes == ["HDFC Large Cap Fund"]


def test_canara_robeco_em_dash_variants():
    schemes = [
        "MF – Canara Robeco Multi Cap Fund ",
        "EQ – Canara Robeco Large and Mid Cap Fund ",
    ]
    site_links = [
        ("Canara Robeco Multi Cap Fund - Direct Plan", "https://canara.example/multicap.xlsx"),
        ("Canara Robeco Large & Mid Cap Fund - Regular Plan", "https://canara.example/lmcap.xlsx"),
    ]
    report = match_schemes(schemes, site_links)
    assert report.matched_count == 2


def test_unmatched_scheme_listed():
    schemes = ["HDFC Innovation Fund", "HDFC Flexi cap fund"]
    site_links = [
        ("HDFC Flexi Cap Fund - Direct Plan", "https://hdfc.example/flexi.xlsx"),
    ]
    report = match_schemes(schemes, site_links)
    assert report.matched_count == 1
    assert report.unmatched_schemes == ["HDFC Innovation Fund"]
    summary = report.summary("mf16", "HDFC")
    assert "matched 1/2" in summary
    assert "HDFC Innovation Fund" in summary


def test_audit_summary_format():
    schemes = ["A Fund", "B Fund"]
    report = match_schemes(schemes, [])
    assert report.matched_count == 0
    assert "matched 0/2" in report.summary("mfXX", "Test")
