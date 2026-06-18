"""Mirae Asset Mutual Fund — per-scheme xlsx via static <a href> links.

Page renders monthly portfolios under "Monthly Portfolio" tab. Each link text:
    "Portfolio Details as on 30th April 2026 for Mirae Asset <Scheme Name>"
and the href is .xlsx under /docs/default-source/portfolios/.

The page is paginated (Bootstrap pagination — `a.page-link`). The first page
shows only ~10 schemes; the user's funds span multiple pages. We click through
each pagination page, accumulating hrefs, then filter to monthly portfolio
xlsx, find latest (year, month), and match per-scheme against the user's list.
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf26")


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.miraeassetmf.co.in/downloads/portfolio"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=("portfolio",),
            exclude_terms=(
                "fortnightly", "weekly", "half year", "half-year", "halfyearly",
                "half yearly", "factsheet", "fact sheet",
                "commission", "addendum", "notice",
                "etf", "index", "overlap",
            ),
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Mirae Asset: no monthly portfolio links found")
        return latest, at_latest

    def _collect_all_pages(self, page) -> list[tuple[str, str]]:
        """Walk Bootstrap pagination by repeatedly clicking 'next' until
        the active page stops advancing. Bootstrap windows the visible page
        numbers (1..5, then 4..8, etc), so a single scan of `a.page-link`
        only sees a slice; clicking next walks the full sequence."""
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

        def active_page() -> int:
            try:
                return int(page.evaluate("""
                    () => {
                        const a = document.querySelector('li.page-item.active a.page-link');
                        const t = (a?.innerText || '').trim();
                        return /^\\d+$/.test(t) ? parseInt(t,10) : 0;
                    }
                """) or 0)
            except Exception:
                return 0

        harvest()
        max_pages = 40   # hard cap to prevent infinite loop on misbehaved sites
        last_active = active_page()
        for _ in range(max_pages):
            # Try to click "next" or the next numeric page-link.
            advanced = page.evaluate("""
                () => {
                    // Prefer an aria-labeled Next button.
                    let next = document.querySelector('a.page-link[aria-label*="Next" i]');
                    if (next && !next.parentElement?.classList.contains('disabled')) {
                        next.click(); return true;
                    }
                    // Fall back to the highest currently-visible numeric link past active.
                    const active = parseInt(document.querySelector('li.page-item.active a.page-link')?.innerText?.trim()||'0', 10) || 0;
                    const links = [...document.querySelectorAll('a.page-link')];
                    const numericTargets = links
                        .map(a => ({ a, n: parseInt((a.innerText||'').trim(), 10) }))
                        .filter(o => Number.isFinite(o.n) && o.n > active);
                    if (numericTargets.length) {
                        numericTargets[0].a.click(); return true;
                    }
                    return false;
                }
            """)
            if not advanced:
                break
            page.wait_for_timeout(1500)
            now = active_page()
            if now <= last_active:
                break
            last_active = now
            harvest()
        log.info("Mirae: harvested %d unique hrefs (last page %d)", len(all_hrefs), last_active)
        return all_hrefs

    def latest_month_label(self, page):
        hrefs = self._collect_all_pages(page)
        latest, at_latest = self._parse_links(hrefs)
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
        return [SchemeEntry(text=fl.text, url=fl.href) for fl in self._latest_links]
