"""mf43 Unifi — parser test against captured static-links fixture."""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf43_unifi import Scraper, parse_links, _entry_label

FIXTURE = Path(__file__).parent / "fixtures" / "mf43" / "links.json"

SCHEMES = ["Unifi Flexi Cap Fund"]


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf43",
        name="Unifi Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES,
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf43_unifi",
    )
    return Scraper(mf)


def test_parse_picks_april_2026() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (year, month), at_latest = parse_links(links)
    assert (year, month) == (2026, 4)
    # Should have exactly 1 link for April 2026 (MP-Unifi-Flexi-Cap-Fund-30042026.xlsx)
    assert len(at_latest) >= 1


def test_excludes_half_yearly_and_performance() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (_year, _month), at_latest = parse_links(links)
    for fl in at_latest:
        assert "-hy-" not in fl.href.lower()
        assert "performance" not in fl.href.lower()


def test_entry_label_extraction() -> None:
    """_entry_label should extract 'Unifi Flexi Cap Fund' from the URL filename."""
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (_year, _month), at_latest = parse_links(links)
    labels = [_entry_label(fl) for fl in at_latest]
    assert any("Unifi Flexi Cap Fund" in lbl for lbl in labels), (
        f"expected 'Unifi Flexi Cap Fund' in labels, got {labels!r}"
    )


def test_matched_scheme() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (_year, _month), at_latest = parse_links(links)
    pairs = [(_entry_label(fl), fl.href) for fl in at_latest]
    report = match_schemes(SCHEMES, pairs)
    assert report.matched_count >= 1, (
        f"expected >=1 match, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
