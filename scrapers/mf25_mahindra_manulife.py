"""Mahindra Manulife — single consolidated xlsx titled "Monthly Portfolio Disclosure".

Page at /downloads lists ~4500 files. We filter to xlsx links whose text matches
"Monthly Portfolio Disclosure", exclude fortnightly/factsheet/commission/addendum,
and pick the latest (year, month).
"""
from __future__ import annotations

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target
from .patterns.static_links_filter import (
    FilteredLink,
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf25")

_INCLUDE = ("monthly", "portfolio")
_EXCLUDE = (
    "fortnightly", "factsheet", "fact sheet", "commission", "addendum",
    "half year", "half-year", "halfyearly", "half yearly",
    "weekly", "quarterly", "presentation", "application", "form",
    "distributor", "notice", "sid", "kim",
    "risk-o-meter", "riskometer", "risk o meter",
)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.mahindramanulife.com/downloads"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]) -> tuple[tuple[int, int], list[FilteredLink]]:
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=_INCLUDE,
            exclude_terms=_EXCLUDE,
            include_either=False,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Mahindra Manulife: no monthly portfolio disclosure links found")
        return latest, at_latest

    def find_target(self, page) -> Target:
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        latest, at_latest = self._parse_links([(t, h) for t, h in hrefs])
        year, month = latest
        winner = at_latest[0]
        as_on = parse_as_on(winner.text, winner.href)
        return Target(
            year=year, month=month, label=winner.text,
            as_on=as_on, kind="url", payload=winner.href,
        )
