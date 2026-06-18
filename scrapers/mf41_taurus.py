"""Taurus Mutual Fund — per-scheme xlsx via Drupal AJAX views.

The page at /monthly-portfolio uses Drupal "Better Exposed Filters" with two
<select> dropdowns:
    - select[name="field_monthly_portfolio_target_id"] for year (Drupal taxonomy IDs, not year numbers)
    - select[name="field_month_target_id"] for month (also taxonomy IDs)

After selecting both year and month via Playwright select_option (by label),
Drupal fires a views/ajax POST that replaces the content area with per-scheme
xlsx links.

IMPORTANT: select by label text (e.g. "2026", "May"), NOT by value. The values
are Drupal taxonomy term IDs (e.g. "567" for 2026, "285" for May) which may
change if terms are re-created. Use name-based selectors since element IDs
change after each AJAX reload.
"""
from __future__ import annotations

from datetime import date

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_NAMES, parse_as_on

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf41")

_INCLUDE_TERMS = ("portfolio",)
_EXCLUDE_TERMS = (
    "fortnightly", "weekly", "half year", "half-year", "halfyearly", "half yearly",
    "factsheet", "fact sheet",
    "addendum", "notice", "riskometer", "risk-o-meter",
)

_YEAR_SELECT = 'select[name="field_monthly_portfolio_target_id"]'
_MONTH_SELECT = 'select[name="field_month_target_id"]'


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://taurusmutualfund.com/monthly-portfolio"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def navigate_to_portfolio(self, page) -> None:
        """Select the latest year and latest month with data from the Drupal filters."""
        # Get available years from the year select (by label text, not value)
        year_options = page.evaluate(f"""() => {{
            const sel = document.querySelector('{_YEAR_SELECT}');
            if (!sel) return [];
            return [...sel.options]
                .map(o => o.text.trim())
                .filter(t => /^\\d{{4}}$/.test(t))
                .sort((a, b) => parseInt(b) - parseInt(a));
        }}""")
        if not year_options:
            log.warning("Taurus: no year options found")
            return

        latest_year = year_options[0]
        log.info("Taurus: selecting year %s", latest_year)
        page.select_option(_YEAR_SELECT, label=latest_year)
        page.wait_for_timeout(5000)

        # Try months from latest (current month) backward until xlsx links appear
        # Month names in the select are full English names
        month_order = list(range(12, 0, -1))  # December first
        for month_num in month_order:
            month_name = MONTH_NAMES[month_num - 1]  # "January", "February", ...
            log.info("Taurus: trying %s %s", month_name, latest_year)
            try:
                page.select_option(_MONTH_SELECT, label=month_name)
            except Exception:
                log.debug("Taurus: month %s not available", month_name)
                continue
            page.wait_for_timeout(5000)

            # Check for xlsx links
            xlsx_count = page.evaluate("""() => {
                return [...document.querySelectorAll('a[href]')]
                    .filter(a => a.href && (a.href.includes('.xlsx') || a.href.includes('.xls')))
                    .length;
            }""")
            if xlsx_count > 0:
                log.info("Taurus: found %d xlsx links for %s %s", xlsx_count, month_name, latest_year)
                self._selected_year = int(latest_year)
                self._selected_month = month_num
                return

        log.warning("Taurus: no xlsx links found for any month in %s", latest_year)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data."""
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=_INCLUDE_TERMS,
            exclude_terms=_EXCLUDE_TERMS,
            include_either=True,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Taurus: no monthly portfolio links found")
        return latest, at_latest

    def latest_month_label(self, page):
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        """) or []

        # If we already selected year/month in navigate_to_portfolio and have links,
        # use those directly. The link text from Taurus is just the scheme name
        # (e.g. "Taurus Flexi Cap Fund") — no month info. But the URLs contain the month.
        links = [(t, h) for t, h in hrefs]

        # Filter to xlsx/xls links only (the page may have nav links too)
        file_links = [(t, h) for t, h in links
                      if '.xlsx' in h.lower() or '.xls' in h.lower()]

        if file_links:
            # Try to infer month from URLs
            from lib.month_hint import try_infer
            for t, h in file_links:
                ym = try_infer(t, h)
                if ym:
                    year, month = ym
                    self._latest_links_raw = file_links
                    as_on = date(year, month, 1)
                    return year, month, as_on

        # Fallback to _parse_links if the links have month info
        try:
            latest, at_latest = self._parse_links(links)
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
        except NoDataYetError:
            # If we have the selected year/month from navigate_to_portfolio
            year = getattr(self, '_selected_year', None)
            month = getattr(self, '_selected_month', None)
            if year and month:
                raise NoDataYetError(
                    f"Taurus: selected {year}/{month} but no portfolio links after filter"
                )
            raise

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        from urllib.parse import unquote

        # If we have raw file links from latest_month_label
        raw_links = getattr(self, '_latest_links_raw', None)
        if raw_links:
            entries = []
            for text, href in raw_links:
                # The visible text is the scheme name (e.g. "Taurus Flexi Cap Fund")
                # If text is just "Download" or empty, derive from filename
                label = text
                if not label or label.lower() in ("download", ""):
                    fname = unquote(href.rsplit("/", 1)[-1].rsplit(".", 1)[0])
                    label = fname.replace("_", " ")
                entries.append(SchemeEntry(text=label, url=href))
            return entries

        # Fallback: use _latest_links from _parse_links
        return [
            SchemeEntry(
                text=unquote(fl.href.rsplit("/", 1)[-1].rsplit(".", 1)[0]).replace("_", " ") if fl.text.lower() in ("download", "") else fl.text,
                url=fl.href,
            )
            for fl in self._latest_links
        ]
