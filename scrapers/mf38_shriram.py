"""Shriram Mutual Fund — single xlsx (all schemes in one file) via static links.

Page structure:
- "Monthly, Fortnightly & Weekly Portfolio of Scheme(s)" section
- Sub-tab: "Monthly Portfolio for the FY"
- Links like:
    Monthly-Portfolio-Shriram-Mutual-Fund-May-2026.xls
    Monthly-Portfolio-Shriram-Mutual-Fund-April-2026.xls

We filter to links containing "monthly-portfolio" in the href, exclude
fortnightly/weekly, and pick the latest (year, month).
"""
from __future__ import annotations

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target
from .patterns.static_links_filter import (
    FilteredLink,
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf38")


def parse_links(links: list[tuple[str, str]]) -> tuple[tuple[int, int], list[FilteredLink]]:
    """Pure parse step — extracted so tests can feed fixture data.

    Shriram URLs embed the entire category path (e.g.
    "Monthly--Fortnightly--Weekly-Portfolio-of-Scheme(s)/...") so we cannot
    apply exclude_terms on the full href — "fortnightly" and "weekly" appear
    in the parent folder name even for monthly files.  Instead we use
    custom_filter to check that the **filename** starts with
    "Monthly-Portfolio" and pass empty exclude_terms.
    """
    def _is_monthly_portfolio(text: str, href: str) -> bool:
        fname = href.rsplit("/", 1)[-1].lower()
        return fname.startswith("monthly-portfolio")

    filtered = filter_monthly_xlsx_links(
        links,
        include_terms=("monthly",),
        exclude_terms=(),           # handled by custom_filter on filename
        custom_filter=_is_monthly_portfolio,
    )
    latest, at_latest = latest_month_links(filtered)
    if not latest:
        raise NoDataYetError("Shriram: no monthly portfolio links found")
    return latest, at_latest


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.shriramamc.in/investor-statutory-disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def find_target(self, page) -> Target:
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        (year, month), at_latest = parse_links([(t, h) for t, h in hrefs])
        # Pick the first (should be only one monthly portfolio per month)
        fl = at_latest[0]
        as_on = parse_as_on(fl.text, fl.href)
        return Target(
            year=year, month=month, label=fl.text or fl.href.split("/")[-1],
            as_on=as_on, kind="url", payload=fl.href,
        )
