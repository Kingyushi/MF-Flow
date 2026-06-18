"""Quantum — single consolidated xlsx titled "<Month> <Year> - All Funds".

Page at /portfolio/combined/-1/1/0/0 lists ~20 xlsx links, each a single
all-funds portfolio file per month. We filter to links containing "all funds"
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

log = get_logger("mf35")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.quantumamc.com/portfolio/combined/-1/1/0/0"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]) -> tuple[tuple[int, int], list[FilteredLink]]:
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=("all funds",),
            exclude_terms=(),
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Quantum: no 'All Funds' portfolio links found")
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
