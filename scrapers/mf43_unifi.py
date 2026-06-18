"""Unifi Mutual Fund — per-scheme xlsx (single scheme: Unifi Flexi Cap Fund).

Page has 158 xlsx links across many disclosure categories. Monthly portfolio
links for Flexi Cap follow patterns like:
    MP-Unifi-Flexi-Cap-Fund-30042026.xlsx   (newer: "MP-" prefix + date)
    Unifi-Flexi-Cap-Fund-30062025.xlsx      (older: direct name + date)

We filter to links containing "flexi" AND "cap" in href, exclude half-yearly
("HY" in filename), and pick the latest month.
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry
from .patterns.static_links_filter import (
    FilteredLink,
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf43")


def parse_links(links: list[tuple[str, str]]) -> tuple[tuple[int, int], list[FilteredLink]]:
    """Pure parse step — extracted so tests can feed fixture data."""
    def _flexi_cap_monthly(text: str, href: str) -> bool:
        h = href.lower()
        # Must be Flexi Cap related
        if "flexi" not in h or "cap" not in h:
            return False
        # Exclude half-yearly files (contain "-HY-" in filename)
        fname = href.split("/")[-1].lower()
        if "-hy-" in fname or "half" in fname:
            return False
        # Exclude scheme performance files
        if "scheme_performance" in h or "scheme-performance" in h:
            return False
        return True

    filtered = filter_monthly_xlsx_links(
        links,
        include_terms=(),  # custom_filter handles inclusion
        exclude_terms=(
            "fortnightly", "half year", "half-year", "commission",
            "complaint", "proxy", "vote", "aaum", "aum",
            "performance", "factsheet",
        ),
        custom_filter=_flexi_cap_monthly,
    )
    latest, at_latest = latest_month_links(filtered)
    if not latest:
        raise NoDataYetError("Unifi: no monthly Flexi Cap portfolio links found")
    return latest, at_latest


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://unifimf.com/statutorydocuments/#monthly-portfolio-disclosure"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def _parse_links(self, links: list[tuple[str, str]]):
        return parse_links(links)

    def latest_month_label(self, page):
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        (year, month), at_latest = parse_links([(t, h) for t, h in hrefs])
        self._latest_links = at_latest
        as_on = None
        for fl in at_latest:
            as_on = parse_as_on(fl.text, fl.href)
            if as_on:
                break
        if not as_on:
            as_on = date(year, month, 1)
        return year, month, as_on

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        return [
            SchemeEntry(text=_entry_label(fl), url=fl.href)
            for fl in self._latest_links
        ]


def _entry_label(fl) -> str:
    """Build a descriptive label from the link.

    The page text is often just "April 2026" — not useful for scheme matching.
    Extract a better name from the URL filename (e.g. "MP-Unifi-Flexi-Cap-Fund-30042026.xlsx"
    -> "Unifi Flexi Cap Fund").
    """
    import re
    fname = fl.href.rsplit("/", 1)[-1]
    # Strip extension
    fname = re.sub(r"\.\w+$", "", fname)
    # Strip leading "MP-" prefix
    fname = re.sub(r"^MP-", "", fname)
    # Strip trailing date (8 digits or "Monthly" suffix)
    fname = re.sub(r"-\d{8}$", "", fname)
    fname = re.sub(r"-Monthly$", "", fname, flags=re.IGNORECASE)
    # Replace hyphens with spaces
    return fname.replace("-", " ").strip()
