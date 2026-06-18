"""NJ Mutual Fund — per-scheme xlsx via static links.

Page lists per-scheme xlsx links titled:
    "Monthly Portfolio - <Month DD>, <YYYY> - <Scheme Name>"
with hrefs like NJ-MF-Monthly-Portfolio-NJFCP-March-2026-<timestamp>.xlsx.
We filter to monthly portfolio links, pick the latest month, then
match against the user's scheme list.

User's scheme names use URL shortcodes (NJFCP, NJELSTCH) rather than
display names. SchemeEntry texts include the shortcode extracted from
the href so scheme_filter can match.
"""
from __future__ import annotations

import re
from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf30")


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://downloads.njmutualfund.com/njmf_download.php?nme=127"

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=("monthly portfolio",),
            include_either=True,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("NJ MF: no monthly portfolio links found")
        return latest, at_latest

    def latest_month_label(self, page):
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        latest, at_latest = self._parse_links([(t, h) for t, h in hrefs])
        self._latest_links = at_latest
        year, month = latest
        as_on = None
        for fl in at_latest:
            as_on = parse_as_on(fl.text, fl.href)
            if as_on:
                break
        if not as_on:
            as_on = date(year, month, 1)
        return year, month, as_on

    @staticmethod
    def _entry_text(text: str, href: str) -> str:
        """Build a matchable text that includes the URL shortcode.
        Href pattern: NJ-MF-Monthly-Portfolio-<CODE>-<Month>-<Year>-...xlsx"""
        m = re.search(r"NJ-MF-Monthly-Portfolio-([A-Z]+)-", href)
        code = m.group(1) if m else ""
        return f"NJ MF Monthly Portfolio {code} {text}" if code else text

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        return [
            SchemeEntry(text=self._entry_text(fl.text, fl.href), url=fl.href)
            for fl in self._latest_links
        ]
