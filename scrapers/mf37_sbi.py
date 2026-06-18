"""SBI — single consolidated xlsx titled "All Schemes Monthly Portfolio - as on <date>".

Page at /portfolios lists ~132 xlsx links. Each monthly file appears twice (once
with descriptive text, once as "Download"). We filter to links containing both
"all schemes" and "monthly", exclude fortnightly/factsheet/etc., and pick the
latest (year, month).
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

log = get_logger("mf37")

_INCLUDE = ("all schemes", "monthly")
_EXCLUDE = (
    "fortnightly", "factsheet", "fact sheet", "commission", "addendum",
    "half year", "half-year", "halfyearly", "half yearly",
    "weekly", "quarterly", "presentation", "application", "form",
    "distributor", "notice", "sid", "kim",
    "risk-o-meter", "riskometer", "risk o meter",
)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.sbimf.com/portfolios"

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
            raise NoDataYetError("SBI: no 'All Schemes Monthly Portfolio' links found")
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
