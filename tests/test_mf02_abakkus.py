"""Regression test for mf02 Abakkus — Monthly Portfolio row identification.

Bug (June 2026): Abakkus renamed the May monthly-portfolio file so its href no
longer contained 'monthly_portfolio' (.../Abakkus_Mutual_Fund_31_05_2026_*.xls).
The old find_target filtered solely on that href token and so silently fell back
to April. The fix also accepts rows whose visible text uses the section's
'<Month> <DD>, <YYYY>' comma-date format, which uniquely marks the Monthly
Portfolio rows (Fortnightly = '15th May 2026', Dashboard/AUM = 'May 2026').
"""
from scrapers.mf02_abakkus import _FULLDATE_TEXT
from lib.month_hint import parse_as_on


def test_fulldate_text_matches_monthly_rows():
    assert _FULLDATE_TEXT.search("DOWNLOAD\nMAY 31, 2026")
    assert _FULLDATE_TEXT.search("DOWNLOAD APRIL 30, 2026")
    assert _FULLDATE_TEXT.search("DOWNLOAD DECEMBER 31, 2025")


def test_fulldate_text_excludes_other_sections():
    # Fortnightly: day-first, no comma.
    assert not _FULLDATE_TEXT.search("Download 15th May 2026")
    assert not _FULLDATE_TEXT.search("Download 31st May 2026")
    # Scheme Dashboard / AUM: no day component.
    assert not _FULLDATE_TEXT.search("Download May 2026")
    assert not _FULLDATE_TEXT.search("Download May")


def test_may_row_picked_over_april():
    """Simulate the live DOM: April keeps the legacy token, May was renamed.
    The filter+date-parse must select May."""
    rows = [
        {"text": "DOWNLOAD APRIL 30, 2026",
         "href": "https://www.abakkusmf.com/uploads/IN_MF_MONTHLY_PORTFOLIO_April_30_2026_x.xls"},
        {"text": "DOWNLOAD MAY 31, 2026",
         "href": "https://www.abakkusmf.com/uploads/Abakkus_Mutual_Fund_31_05_2026_y.xls"},
    ]
    import re
    kept = [
        r for r in rows
        if re.search(r"monthly[_\-]portfolio", r["href"], re.IGNORECASE)
        or _FULLDATE_TEXT.search(r["text"])
    ]
    assert len(kept) == 2
    best = max(kept, key=lambda r: parse_as_on(r["href"], r["text"]))
    assert "31_05_2026" in best["href"]
    assert parse_as_on(best["href"], best["text"]).month == 5
