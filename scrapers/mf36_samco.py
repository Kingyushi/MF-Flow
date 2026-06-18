"""SAMCO Mutual Fund — per-scheme xlsx via static <a href> links.

Page renders thousands of xlsx links. The monthly portfolio links follow:

    IN_MF_MONTHLY_PORTFOLIO_<Month>_<Year>_<SchemeName>_<timestamp>.xlsx

We filter to xlsx whose href contains "MONTHLY_PORTFOLIO" (case-insensitive),
drop fortnightly / half-yearly / overnight fund fortnightly, infer
(year, month), keep only the latest month, then match per-scheme.

SAMCO duplicates every link under two domains (www.samcomf.com and
media1.samco.in). We de-duplicate by keeping only www.samcomf.com links.
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

log = get_logger("mf36")

_INCLUDE_TERMS = ("monthly_portfolio",)
_EXCLUDE_TERMS = (
    "fortnightly", "weekly", "half year", "half-year", "halfyearly",
    "hy_portfolio", "HY_PORTFOLIO",
    "factsheet", "fact sheet",
    "overnight",
)


def _split_camelcase(s: str) -> str:
    """Split CamelCase into separate words: 'SamcoLargeCapFund' -> 'Samco Large Cap Fund'."""
    return re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', s)


_SAMCO_TYPOS = {
    "Apirl": "April",
    "apirl": "april",
    "APIRL": "APRIL",
}


def _fix_samco_typos(url: str) -> str:
    """Fix known SAMCO URL typos so month inference works."""
    for wrong, right in _SAMCO_TYPOS.items():
        if wrong in url:
            url = url.replace(wrong, right)
    return url


def _custom_filter(text: str, href: str) -> bool:
    """Keep only www.samcomf.com links with MONTHLY_PORTFOLIO in the path."""
    h = href.lower()
    if "media1.samco.in" in h:
        return False
    return "monthly_portfolio" in h


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.samcomf.com/StatutoryDisclosure"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data.

        SAMCO uploaded April 2026 files under the typo "Apirl_2026" — the
        files only resolve at the typo'd URL. We normalize the typo into a
        SEPARATE label string used only for month inference, but keep the
        original href intact so the download hits the URL that actually has
        a file behind it.
        """
        # Run the standard filter against (typo-fixed-text-for-month-parse, real-href).
        fixed_for_parse = [(_fix_samco_typos(text + " " + href), href) for text, href in links]
        filtered = filter_monthly_xlsx_links(
            fixed_for_parse,
            include_terms=_INCLUDE_TERMS,
            exclude_terms=_EXCLUDE_TERMS,
            include_either=True,
            custom_filter=_custom_filter,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("SAMCO: no monthly portfolio links found")
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

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        from urllib.parse import unquote
        return [
            SchemeEntry(
                text=_split_camelcase(
                    unquote(fl.href.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " ")
                ),
                url=fl.href,
            )
            for fl in self._latest_links
        ]
