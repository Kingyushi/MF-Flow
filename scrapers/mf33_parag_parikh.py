"""Parag Parikh — single consolidated xls titled "Consolidated" per month.

Page at /downloads/portfolio-disclosure/ lists ~383 files grouped by year+month.
Each group has one "Consolidated" xls plus per-scheme xlsx files. We filter to
links whose text is exactly "Consolidated" and pick the latest (year, month).
The month info comes from the href (e.g. "April_30_2026" in the filename).
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

log = get_logger("mf33")


def _is_consolidated(text: str, href: str) -> bool:
    return text.strip().lower() == "consolidated"


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://amc.ppfas.com/downloads/portfolio-disclosure/"

    def _parse_links(self, links: list[tuple[str, str]]) -> tuple[tuple[int, int], list[FilteredLink]]:
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=(),
            exclude_terms=(),
            custom_filter=_is_consolidated,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Parag Parikh: no consolidated portfolio links found")
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
