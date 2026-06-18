"""mf38 Shriram — parser test against captured static-links fixture."""
from __future__ import annotations

import json
from pathlib import Path

from scrapers.mf38_shriram import parse_links

FIXTURE = Path(__file__).parent / "fixtures" / "mf38" / "links.json"


def test_parse_picks_may_2026() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (year, month), at_latest = parse_links(links)
    assert (year, month) == (2026, 5)
    assert len(at_latest) == 1  # single monthly portfolio file per month


def test_correct_url_selected() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (_year, _month), at_latest = parse_links(links)
    fl = at_latest[0]
    assert "Monthly-Portfolio-Shriram-Mutual-Fund-May-2026" in fl.href


def test_excludes_non_portfolio() -> None:
    links = [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]
    (_year, _month), at_latest = parse_links(links)
    for fl in at_latest:
        # Check the filename, not the full path (parent path contains "fortnightly" as category)
        fname = fl.href.rsplit("/", 1)[-1].lower()
        assert fname.startswith("monthly-portfolio")
        assert "transaction" not in fname
        assert "complaint" not in fname
        assert "fortnightly" not in fname
