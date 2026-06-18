"""Old Bridge Mutual Fund — per-scheme xlsx via static <a href> links.

Page renders all disclosures under "Monthly Portfolio" tab. Each xlsx link's
visible text is just "Download" — the scheme name + month live in the URL:

    https://oldbridgemf.com/uploads/Old_Bridge_Flexi_Cap_Fund_Apr_26_Portfolio_<hash>.xlsx

We filter to xlsx whose href contains "portfolio" (case-insensitive), drop
half-yearly / fortnightly / unrelated files, infer (year, month) from the
URL, keep only the latest month, then match per-scheme.
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

log = get_logger("mf31")

# Old Bridge link text is always "Download"; all filtering is by href.
# Include: href must contain "portfolio".
# Exclude: half yearly, financials, etc.
_INCLUDE_TERMS = ("portfolio",)
_EXCLUDE_TERMS = (
    "half_yearly", "half yearly", "half-year", "halfyearly",
    "fortnightly", "weekly",
    "financials", "factsheet", "fact sheet",
    "addendum", "notice", "complaints", "proxy",
    "compensation", "geography", "associates",
    "performance", "avg_asset", "avg asset",
)


def _custom_filter(text: str, href: str) -> bool:
    """Keep only links whose URL contains 'portfolio' (case-insensitive)."""
    return "portfolio" in href.lower()


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://oldbridgemf.com/statutory-disclosures.html"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=_INCLUDE_TERMS,
            exclude_terms=_EXCLUDE_TERMS,
            include_either=True,
            custom_filter=_custom_filter,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Old Bridge: no monthly portfolio links found")
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
        # Link text is "Download" — use URL-decoded href as the display text
        # for scheme matching, since the scheme name lives in the URL.
        from urllib.parse import unquote
        return [
            SchemeEntry(
                text=unquote(fl.href.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " "),
                url=fl.href,
            )
            for fl in self._latest_links
        ]
