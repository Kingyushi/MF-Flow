"""Parse test for mf30 NJ Mutual Fund — per-scheme xlsx via static links."""
import json
from pathlib import Path

from lib.config import MFConfig
from lib.scheme_filter import match_schemes
from scrapers.mf30_nj import Scraper

FIXTURES = Path(__file__).parent / "fixtures" / "mf30"

SCHEMES = [
    "NJ MF Monthly Portfolio NJFCP",
    "NJ MF Monthly Portfolio NJELSTCH",
]


def _make_mf():
    return MFConfig(
        id="mf30",
        name="NJ Mutual Fund",
        url=Scraper.DISCLOSURES_URL,
        schemes=SCHEMES,
        instructions="",
        pattern="per_scheme_xlsx",
        module="scrapers.mf30_nj",
    )


def test_parse_links_finds_latest_month():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 3)
    assert len(at_latest) == 5  # 5 schemes for March 2026


def test_parse_links_excludes_fortnightly_and_halfyearly():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    _, at_latest = scraper._parse_links(links)
    for fl in at_latest:
        assert "fortnightly" not in fl.text.lower()
        assert "half year" not in fl.text.lower()


def test_parse_links_handles_underscore_format():
    """Regression: NJ flipped its newest links to 'NJ_MF_Monthly_Portfolio_<CODE>_<Month> <Year>'
    (text) / 'NJ-MF-Monthly-Portfolio-<CODE>-<Month>-<Year>' (href). A filter that
    required the literal 'monthly portfolio' WITH A SPACE dropped these, so May/April
    silently lost to March. The separator-normalized filter must keep them."""
    links = [
        ("Monthly Portfolio - March 31, 2026 - NJ Flexi Cap Fund",
         "https://downloads.njmutualfund.com/viewfile.php?file=NJ-MF-Monthly-Portfolio-NJFCP-March-2026-20260407122951.xlsx"),
        ("NJ_MF_Monthly_Portfolio_NJFCP_May 2026",
         "https://downloads.njmutualfund.com/viewfile.php?file=NJ-MF-Monthly-Portfolio-NJFCP-May-2026-20260609110402.xlsx"),
        ("NJ_MF_Monthly_Portfolio_NJELSTCH_May 2026",
         "https://downloads.njmutualfund.com/viewfile.php?file=NJ-MF-Monthly-Portfolio-NJELSTCH-May-2026-20260609110444.xlsx"),
        ("NJ_MF_Monthly_Portfolio_NJFCP_April 2026",
         "https://downloads.njmutualfund.com/viewfile.php?file=NJ-MF-Monthly-Portfolio-NJFCP-April-2026-20260508105235.xlsx"),
    ]
    scraper = Scraper(_make_mf())
    latest, at_latest = scraper._parse_links(links)
    assert latest == (2026, 5)
    assert len(at_latest) == 2  # NJFCP + NJELSTCH for May


def test_scheme_matching():
    with open(FIXTURES / "links.json") as f:
        links = json.load(f)
    scraper = Scraper(_make_mf())
    _, at_latest = scraper._parse_links(links)
    link_pairs = [(Scraper._entry_text(fl.text, fl.href), fl.href) for fl in at_latest]
    report = match_schemes(SCHEMES, link_pairs)
    assert len(report.matched) == 2
    matched_schemes = {m.scheme_name for m in report.matched}
    assert "NJ MF Monthly Portfolio NJFCP" in matched_schemes
    assert "NJ MF Monthly Portfolio NJELSTCH" in matched_schemes
