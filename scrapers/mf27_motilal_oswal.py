"""Motilal Oswal — single consolidated xlsx "Scheme Portfolio Details".

The downloads page is a JS app listing many files. Two traits make naive
parsing wrong, both learned the hard way:

1. **Folder month != data month.** Motilal files the month-end portfolio under
   the *publish* month's folder, not the as-on month. The May-31 portfolio
   (published 10 Jun) lives at `.../2026/june/Scheme Portfolio Details
   31-05-2026.xlsx`. Inferring the month from the URL folder ("june") mislabels
   it. The FILENAME carries the true as-on date ("31-05-2026" -> May) — so we
   parse the month from the filename only and ignore the folder.

2. **Separator drift.** Older files were named `...scheme-portfolio-details-...`
   (hyphens) or `PortfolioHolding_...`; the republished ones use spaces
   (`Scheme Portfolio Details 31-05-2026.xlsx`, URL-encoded %20). A hyphen-only
   substring filter silently dropped the newest month. We normalize separators
   before matching.

Fortnightly / half-yearly / factsheet rows live on the same page and must be
excluded — they're filtered by filename keyword.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target
from .patterns.static_links_filter import FilteredLink, latest_month_links

log = get_logger("mf27")

# Filename keywords (separator-normalized) that mark a monthly Scheme Portfolio
# Details file. "portfolio holding" / "portfolioholding" covers the legacy
# naming, "scheme portfolio details" the current one.
_INCLUDE_NAME = ("scheme portfolio details", "portfolioholding", "portfolio holding")
# Any of these in the (normalized) filename disqualifies the link.
_EXCLUDE = (
    "fortnightly", "forthnightly", "forthnight",
    "factsheet", "fact sheet", "half year", "half yearly", "halfyearly",
    "weekly", "quarterly", "commission", "distributor", "addendum", "notice",
    "sid", "kim", "presentation", "application", "form",
    "risk o meter", "riskometer",
)

_XLS_RE = re.compile(r"\.xlsx?(\?|$)", re.IGNORECASE)


def _filename(href: str) -> str:
    """URL-decoded last path segment, e.g. 'Scheme Portfolio Details 31-05-2026.xlsx'."""
    try:
        return unquote(urlparse(href).path.rsplit("/", 1)[-1])
    except Exception:
        return href


def _norm(s: str) -> str:
    """Lowercase and collapse separators so 'scheme portfolio details' matches
    'scheme-portfolio-details', 'Scheme_Portfolio_Details', spaces, etc."""
    return re.sub(r"[_\-.]+", " ", s.lower())


def _is_monthly_portfolio(href: str) -> bool:
    name = _norm(_filename(href))
    if any(x in name for x in _EXCLUDE):
        return False
    return any(x in name for x in _INCLUDE_NAME)


def _month_from_filename(name: str):
    """Return (year, month) from the as-on date encoded in the FILENAME, never
    the folder. Prefer a full date ('31-05-2026', 'May 31, 2026'); fall back to
    a bare 'month year' inferred from the filename only."""
    d = parse_as_on(name)
    if d:
        return (d.year, d.month)
    return try_infer(name)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.motilaloswalmf.com/downloads/scheme-portfolio-details"

    def dismiss_consent(self, page) -> None:
        # SPA: wait for the file list to render before reading anchors.
        page.wait_for_timeout(3000)
        try:
            page.wait_for_selector(
                "a[href*='month-end-portfolio']", timeout=12_000
            )
        except Exception:
            pass

    def _parse_links(self, links: list[tuple[str, str]]) -> tuple[tuple[int, int], list[FilteredLink]]:
        """Pure parse step — extracted so tests can feed fixture data.

        Month is derived from each file's FILENAME as-on date, not the URL
        folder, so Motilal's publish-month-folder convention can't mislabel it.
        """
        cands: list[FilteredLink] = []
        for text, href in links:
            if not href or not _XLS_RE.search(href):
                continue
            if not _is_monthly_portfolio(href):
                continue
            ym = _month_from_filename(_filename(href))
            if not ym:
                continue
            cands.append(FilteredLink(text=text or _filename(href), href=href, year=ym[0], month=ym[1]))
        latest, at_latest = latest_month_links(cands)
        if not latest:
            raise NoDataYetError("Motilal Oswal: no scheme portfolio detail links found")
        return latest, at_latest

    def find_target(self, page) -> Target:
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []
        latest, at_latest = self._parse_links([(t, h) for t, h in hrefs])
        year, month = latest
        winner = at_latest[0]
        as_on = parse_as_on(_filename(winner.href)) or parse_as_on(winner.text)
        return Target(
            year=year, month=month, label=winner.text or _filename(winner.href),
            as_on=as_on, kind="url", payload=winner.href,
        )
