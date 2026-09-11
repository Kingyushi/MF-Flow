"""Regression tests for mf02 Abakkus — Monthly Portfolio row identification.

Bug 1 (June 2026): Abakkus renamed the May monthly-portfolio file so its href
no longer contained 'monthly_portfolio' (.../Abakkus_Mutual_Fund_31_05_2026_*.xls).
The old find_target filtered solely on that href token and so silently fell back
to April. The fix also accepts rows whose visible text uses the section's
'<Month> <DD>, <YYYY>' comma-date format.

Bug 2 (August 2026): the comma-date format stopped being unique — Abakkus
added a daily "Debt and money market transactions" section whose rows read
"August 03, 2026". That row won as "latest" and a daily TREPS file was
recorded as the phantom month "August 2026" (which would make the September
run skip the real August portfolio). Fix: anchors are scoped to the
#mpdOutput container, and _pick_monthly_row rejects rows whose date is not a
completed month-end.
"""
from datetime import date

from scrapers.mf02_abakkus import _FULLDATE_TEXT, _pick_monthly_row
from lib.month_hint import parse_as_on

# The full anchor list scraped live from the whole statutory-disclosures page
# on 2026-08-14 — the exact DOM state that produced the incident.
LIVE_ROWS_2026_08_14 = [
    {"text": "DOWNLOAD\nJULY 31, 2026",
     "href": "https://www.abakkusmf.com/uploads/Final_Monthly_Portfolio_Jul_31_a313e9e6dd.xls"},
    {"text": "Download 15th July 2026",
     "href": "https://www.abakkusmf.com/uploads/Abakkus_MF_July_15_2026_4d50735aa6.xls"},
    {"text": "Download 31 July 2026",
     "href": "https://www.abakkusmf.com/uploads/Final_Portfolio_Jul31_Fortntly_3603a16dc8.xls"},
    {"text": "Download All schemes Half Yearly Portfolio Disclosures as on March 31, 2026",
     "href": "https://www.abakkusmf.com/uploads/Half_Yearly_Portfolio_March_26_Final_dbce7a92f6.xls"},
    {"text": "Download July 2026",
     "href": "https://www.abakkusmf.com/uploads/Abakkus_MF_Scheme_Dashboard_July_2026_546aeb078b.xlsx"},
    # The trap: daily debt/TREPS disclosure in the new #dmmtOutput section.
    {"text": "Download August 03, 2026",
     "href": "https://www.abakkusmf.com/uploads/Aug_3_2026_077255a3bb.xls"},
    {"text": "Download IR Abakkus Mutual Fund 13/08/2026",
     "href": "https://www.abakkusmf.com/uploads/IR_Abakkus_Mutual_Fund_13082026_94a83b669d.xlsx"},
]


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


# --- Bug 2 regression: the August 2026 daily-TREPS trap ---------------------

def test_aug_daily_debt_row_rejected_july_wins():
    """On 2026-08-14, with the trap row present, selection must return the
    real July 31 monthly portfolio — NOT the Aug 3 daily debt file."""
    best, best_d = _pick_monthly_row(LIVE_ROWS_2026_08_14, today=date(2026, 8, 14))
    assert best is not None
    assert best_d == date(2026, 7, 31)
    assert "Monthly_Portfolio_Jul_31" in best["href"]


def test_trap_still_rejected_in_september():
    """Sept run, real August file not yet published: Aug 3 daily file is a
    completed month by then, but fails the month-end test — July must still win."""
    best, best_d = _pick_monthly_row(LIVE_ROWS_2026_08_14, today=date(2026, 9, 5))
    assert best_d == date(2026, 7, 31)


def test_real_august_file_wins_in_september():
    """When Abakkus publishes the genuine August month-end portfolio, it must
    be selected over both July and the trap row."""
    rows = LIVE_ROWS_2026_08_14 + [
        {"text": "DOWNLOAD\nAUGUST 31, 2026",
         "href": "https://www.abakkusmf.com/uploads/Final_Monthly_Portfolio_Aug_31_ffffffffff.xls"},
    ]
    best, best_d = _pick_monthly_row(rows, today=date(2026, 9, 5))
    assert best_d == date(2026, 8, 31)
    assert "Aug_31" in best["href"]


def test_fortnightly_15th_rejected():
    rows = [
        {"text": "Download 15th July 2026",
         "href": "https://www.abakkusmf.com/uploads/Abakkus_MF_July_15_2026_x.xls"},
    ]
    best, best_d = _pick_monthly_row(rows, today=date(2026, 8, 14))
    assert best is None


def test_no_plausible_rows_returns_none():
    best, best_d = _pick_monthly_row(
        [{"text": "Download August 03, 2026",
          "href": "https://www.abakkusmf.com/uploads/Aug_3_2026_x.xls"}],
        today=date(2026, 8, 14),
    )
    assert best is None and best_d is None
