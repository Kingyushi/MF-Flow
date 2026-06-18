"""ITI Mutual Fund — Portfolio Disclosures > Monthly sub-tab, click-to-download.

Page structure (Angular):
- Left nav: click "Portfolio Disclosures"
- Then click "Monthly" sub-tab (default may be "Half yearly")
- File list shows rows like "Monthly Portfolio - April 2026"
- Click row to trigger xlsx download.
"""
from __future__ import annotations

import re

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf20")

_MONTHLY_RE = re.compile(
    r"^Monthly Portfolio\s*[\-–]\s*(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})$",
    re.IGNORECASE,
)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.itiamc.com/statuory-disclosure?type=Portfolio%20Disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(8000)

    def navigate_to_portfolio(self, page) -> None:
        # URL ?type=Portfolio%20Disclosures pre-selects the section. The
        # Monthly Portfolio rows are already present in the DOM via the
        # Angular file-list-section divs; no click required.
        page.wait_for_timeout(2000)

    def find_target(self, page) -> Target:
        # Find all file-list rows matching "Monthly Portfolio - <Month> <Year>"
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('div.file-list-section--name, div.file-list-section')]
                .map(d => (d.innerText||'').trim())
                .filter(t => /^Monthly Portfolio[\s\-–]/i.test(t))
        """)
        if not rows:
            raise NoDataYetError("ITI: no Monthly Portfolio rows under Portfolio Disclosures > Monthly")
        # Pick the latest.
        candidates = []
        for r in rows:
            m = _MONTHLY_RE.match(r)
            if not m:
                continue
            month_word = m.group("month").lower()
            month = ALL_MONTHS.get(month_word)
            if not month:
                continue
            year = int(m.group("year"))
            candidates.append((year, month, m.group("month"), r))
        if not candidates:
            raise NoDataYetError("ITI: no parseable Monthly Portfolio entries")
        candidates.sort()
        year, month, month_word, label = candidates[-1]

        def click_action():
            page.evaluate(
                f"""() => {{
                    const els = [...document.querySelectorAll('div.file-list-section--name')];
                    const target = els.find(e => (e.innerText||'').trim() === {label!r});
                    if (!target) throw new Error('target name row not found');
                    // The download anchor lives inside the sibling .file-list-section--actions
                    const parent = target.parentElement;
                    const link = parent?.querySelector('a.file-download-link') ||
                                 parent?.querySelector('a[href*="javascript"]') ||
                                 parent?.querySelector('a');
                    if (!link) throw new Error('download link not found');
                    link.click();
                }}"""
            )

        from datetime import date as _date
        return Target(
            year=year, month=month, label=label,
            as_on=_date(year, month, 1), kind="click", payload=click_action,
        )
