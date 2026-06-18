"""JM Financial Mutual Fund — per-scheme xlsx via static <a href> links.

Page renders all monthly portfolios in a flat list. The visible link text is
just "View" / "Download"; the scheme name and date live in the URL path:
    .../Monthly%20Portfolio%20-%20JM%20<Scheme>%20-%20May%2031%202026.xlsx

JM publishes per-scheme portfolios on a rolling basis (e.g. May 2026 for
3 schemes today, the other 3 over the next week). We use per-scheme-latest:
for each user scheme, take its OWN latest month, so a scheme with only April
data still ships in April folder while May-ready schemes ship in May.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import date
from pathlib import PurePosixPath

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    per_scheme_latest_links,
)

log = get_logger("mf22")


def _label_from_href(href: str) -> str:
    name = PurePosixPath(urllib.parse.urlparse(href).path).name
    return urllib.parse.unquote(name).rsplit(".", 1)[0]


def _scheme_key(label: str) -> str:
    """Strip date + 'Monthly Portfolio' boilerplate so the same scheme across
    different months hashes to the same key."""
    s = label.lower()
    s = re.sub(r"monthly\s+portfolio", "", s)
    s = re.sub(r"\b\d{1,2}[,\s]+\d{4}\b", "", s)
    s = re.sub(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.jmfinancialmf.com/downloads/Portfolio-Disclosure/Monthly-Portfolio-of-Schemes"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse: per-scheme-latest. Returns ((max_year, max_month),
        list[FilteredLink]) — one link per distinct scheme, at its own
        individual latest month."""
        enriched = [(_label_from_href(h) if t.lower() in ("view", "download", "") else t, h)
                    for t, h in links]
        filtered = filter_monthly_xlsx_links(
            enriched,
            include_terms=("monthly", "portfolio"),
            include_either=False,
        )
        max_ym, picks = per_scheme_latest_links(
            filtered,
            scheme_key=lambda fl: _scheme_key(fl.text),
        )
        if not max_ym:
            raise NoDataYetError("JM Financial: no monthly portfolio links found")
        return max_ym, picks

    def _collect_paginated_hrefs(self, page) -> list[tuple[str, str]]:
        """JM's disclosures page shows ~5 entries per page via rc-pagination.
        Walk pages until every user-listed scheme has been seen OR we hit a
        hard cap (defensively, JM lists 100s of historical pages — we only
        need the first handful to cover the latest month per scheme)."""
        all_hrefs: list[tuple[str, str]] = []
        seen_hrefs: set[str] = set()

        def harvest():
            page_hrefs = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
            """) or []
            for t, h in page_hrefs:
                if h not in seen_hrefs:
                    seen_hrefs.add(h)
                    all_hrefs.append((t, h))

        wanted_keys = {_scheme_key(s) for s in self.mf.schemes}

        def coverage() -> int:
            seen_keys = set()
            for _t, h in all_hrefs:
                if ".xlsx" not in h.lower() or "fortnight" in h.lower():
                    continue
                seen_keys.add(_scheme_key(_label_from_href(h)))
            return len(wanted_keys & seen_keys)

        harvest()
        max_pages = 15
        for _ in range(max_pages):
            if coverage() >= len(wanted_keys):
                break
            advanced = page.evaluate("""
                () => {
                    const next = document.querySelector(
                      'li.rc-pagination-next:not(.rc-pagination-disabled) a, '
                      + 'li.rc-pagination-next:not(.rc-pagination-disabled) button'
                    );
                    if (next) { next.click(); return true; }
                    return false;
                }
            """)
            if not advanced:
                break
            page.wait_for_timeout(2000)
            before = len(all_hrefs)
            harvest()
            if len(all_hrefs) == before:
                # No new links — site might have stopped responding
                break
        log.info("JM: paginated %d unique hrefs, scheme coverage %d/%d",
                 len(all_hrefs), coverage(), len(wanted_keys))
        return all_hrefs

    def latest_month_label(self, page):
        hrefs = self._collect_paginated_hrefs(page)
        max_ym, picks = self._parse_links(hrefs)
        self._picks = picks
        year, month = max_ym
        as_on = None
        for fl in picks:
            if (fl.year, fl.month) == max_ym:
                as_on = parse_as_on(fl.text, fl.href)
                if as_on:
                    break
        if not as_on:
            as_on = date(year, month, 1)
        return year, month, as_on

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        return [
            SchemeEntry(text=fl.text, url=fl.href, year=fl.year, month=fl.month)
            for fl in self._picks
        ]
