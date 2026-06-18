"""Nippon India Mutual Fund — single multi-sheet xls via static links.

Page lists many "Download" links; hrefs contain NIMF-MONTHLY-PORTFOLIO-<dd>-<Mon>-<yy>.xls
for the consolidated monthly portfolio, plus FORTNIGHTLY, Risk-Parameter, etc.
We filter by "MONTHLY-PORTFOLIO" in the href and pick the latest month.
All link texts are just "Download" so filtering is purely href-based.
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf29")


def _is_monthly_portfolio(text: str, href: str) -> bool:
    return "MONTHLY-PORTFOLIO" in href.upper()


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=(),
            exclude_terms=(),
            custom_filter=_is_monthly_portfolio,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Nippon: no monthly portfolio links found")
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
