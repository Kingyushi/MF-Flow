"""mf31 Old Bridge — parser test against captured Monthly-Portfolio fixture.

Fixture is real data from the live "Monthly Portfolio" tab pane. Each entry is
[aria-label, href] — the aria-label carries the scheme + month
(e.g. 'Download Old Bridge Focused Fund - June 2026 (opens in new tab)'), which
is what the scraper now keys on (the filenames no longer contain the month).
Snapshot frozen 2026-07-17, so the expected latest month is June 2026.
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf31_old_bridge import Scraper

FIXTURE = Path(__file__).parent / "fixtures" / "mf31" / "links.json"


def _scraper() -> Scraper:
    mf = MFConfig(
        id="mf31",
        name="Old Bridge Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=[
            "Old Bridge Flexi Cap Fund",
            "Old Bridge Focused Fund",
        ],
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf31_old_bridge",
    )
    return Scraper(mf)


def _links() -> list[tuple[str, str]]:
    return [tuple(p) for p in json.loads(FIXTURE.read_text(encoding="utf-8"))]


def test_parse_picks_june_2026() -> None:
    (year, month), at_latest = _scraper()._parse_links(_links())
    assert (year, month) == (2026, 6)
    # June 2026 has 3 scheme portfolios (Flexi Cap, Arbitrage, Focused).
    assert len(at_latest) == 3


def test_month_inferred_from_label_not_filename() -> None:
    # The June files have opaque names (OBFE_/OBFX_/OBAF_) with no month token;
    # detection must still work because it reads the aria-label.
    (_ym), at_latest = _scraper()._parse_links(_links())
    assert any(
        h in fl.href for fl in at_latest for h in ("OBFE_", "OBFX_", "OBAF_")
    ), "June files with opaque names should be selected"


def test_excludes_half_yearly_and_non_portfolio() -> None:
    (_year, _month), at_latest = _scraper()._parse_links(_links())
    for fl in at_latest:
        assert "half_yearly" not in fl.href.lower()
        assert "financials" not in fl.href.lower()
        assert "fund" in fl.text.lower()   # real scheme rows only


def test_matched_schemes_from_label() -> None:
    s = _scraper()
    (_ym), at_latest = s._parse_links(_links())
    # list_scheme_entries derives the scheme name from the aria-label.
    s._latest_links = at_latest
    entries = [(e.text, e.url) for e in s.list_scheme_entries(page=None)]
    report = match_schemes(s.mf.schemes, entries)
    assert report.matched_count == 2, (
        f"expected 2 matches, got {report.matched_count} "
        f"(unmatched={report.unmatched_schemes!r})"
    )
    matched = {m.scheme_name: m.link_url for m in report.matched}
    assert "OBFX_" in matched["Old Bridge Flexi Cap Fund"]
    assert "OBFE_" in matched["Old Bridge Focused Fund"]
