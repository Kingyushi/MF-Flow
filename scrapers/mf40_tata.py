"""Tata Mutual Fund — single multi-sheet xlsx via advisorkhoj.com.

Page at advisorkhoj lists monthly portfolio xlsx links for every month,
each titled "Monthly Portfolio Disclosure - <Month> <YYYY>". The href
points to betacms.tatamutualfund.com. We filter to the latest month
and download the single consolidated xlsx.

Note: href paths contain the PUBLICATION month (data month + 1), so
date inference uses text only to avoid mismatch.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, parse_as_on

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target
from .patterns.static_links_filter import FilteredLink

log = get_logger("mf40")

_TITLE_RE = re.compile(
    r"Monthly Portfolio Disclosure\s*[-–]\s*([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
_PORTFOLIO_EXT_RE = re.compile(r"\.(xlsx|xls)(\?|$|#)", re.IGNORECASE)


def _parse_monthly_portfolio_links(
    links: list[tuple[str, str]],
) -> list[FilteredLink]:
    """Parse (text, href) pairs into FilteredLink using text-only date extraction."""
    out: list[FilteredLink] = []
    for text, href in links:
        if not href or not _PORTFOLIO_EXT_RE.search(href):
            continue
        m = _TITLE_RE.search(text)
        if not m:
            continue
        month_word = m.group(1).lower()
        month_num = ALL_MONTHS.get(month_word)
        if not month_num:
            continue
        year = int(m.group(2))
        out.append(FilteredLink(text=text, href=href, year=year, month=month_num))
    return out


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.advisorkhoj.com/form-download-centre/Mutual/Tata-Mutual-Fund/Monthly-Portfolio-Disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = _parse_monthly_portfolio_links(links)
        if not filtered:
            raise NoDataYetError("Tata: no monthly portfolio links found")
        latest = max((fl.year, fl.month) for fl in filtered)
        at_latest = [fl for fl in filtered if (fl.year, fl.month) == latest]
        return latest, at_latest

    def find_target(self, page) -> Target:
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        latest, at_latest = self._parse_links([(t, h) for t, h in hrefs])
        year, month = latest
        fl = at_latest[0]
        as_on = parse_as_on(fl.href)
        if not as_on:
            as_on = date(year, month, 1)
        return Target(
            year=year, month=month, label=fl.text,
            as_on=as_on, kind="url", payload=fl.href,
        )
