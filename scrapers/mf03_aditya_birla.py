"""Aditya Birla Sun Life Mutual Fund — monthly zip.

Page lists rows like "Monthly Portfolios as on April 30, 2026" each backed
by an anchor whose URL ends in .zip (despite the user's instructions saying
xlsx — zip is what the site actually serves; the zip presumably contains
an xlsx with many sheets per scheme).

URL pattern:
    https://.../monthly-portfolio/<year>/monthly-disclosure-april-30-2026.zip
    https://.../monthly-portfolio/<year>/sebi_monthly_portfolio-30-mar-2026.zip
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.zip_pattern import LatestMonthZipScraper

log = get_logger("mf03")


class Scraper(LatestMonthZipScraper):
    DISCLOSURES_URL = "https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(4000)

    def find_latest_link(self, page):
        # Each row has visible text like "Monthly Portfolios as on April 30, 2026"
        # and an anchor (usually an icon link) with href ending in .zip.
        rows = page.evaluate(r"""
            () => {
                // Find every element whose text is "Monthly Portfolios as on <date>",
                // then locate the nearest anchor with .zip href.
                const labels = [...document.querySelectorAll('*')]
                    .filter(e => e.children.length === 0 && /Monthly Portfolios as on/i.test((e.innerText||'')));
                const out = [];
                for (const el of labels) {
                    const text = (el.innerText || '').trim();
                    // Walk up to a row container, then look for .zip anchors below.
                    let row = el;
                    for (let i = 0; i < 5 && row; i++) {
                        const anchor = row.querySelector('a[href$=".zip"]');
                        if (anchor) {
                            out.push({text, href: anchor.href});
                            break;
                        }
                        row = row.parentElement;
                    }
                }
                return out;
            }
        """)
        if not rows:
            raise NoDataYetError("ABSL: no Monthly Portfolios rows with .zip href")
        # Pick latest by as-on date.
        best = None
        best_date = None
        for r in rows:
            d = parse_as_on(r["text"])
            if not d:
                ym = try_infer(r["text"])
                if ym:
                    d = date(ym[0], ym[1], 1)
            if d and (best_date is None or d > best_date):
                best_date = d
                best = r
        if not best:
            raise NoDataYetError("ABSL: could not parse any row dates")
        return (best["href"], best["text"], best_date)
