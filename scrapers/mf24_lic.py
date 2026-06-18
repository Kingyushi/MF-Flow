"""LIC Mutual Fund — per-scheme xlsx via cascading form submission.

The page has a 4-step cascading AJAX form:
  1. fund_category (Equity/Hybrid/...) -> populates fund_name
  2. fund_name (scheme code) -> populates year
  3. year -> populates month
  4. Submit -> triggers AJAX POST to /downloads/portfolio-files

The submit does NOT trigger a browser download event.  Instead jQuery posts to
``/downloads/portfolio-files`` with ``scheme_code``, ``year``, ``month``,
``type=monthly_portfolio``.  The server returns an HTML fragment containing an
``<a href="/assets/downloads/portfolio/monthly/…xlsx">`` link.  We intercept
that response, extract the URL, and download via static fetcher.

The select elements use name= attributes (NOT id=), so we use
select[name="..."] CSS selectors.

The AJAX endpoint for cascading is:
  POST /downloads/portfolio-filter-options
  with body: scheme_code=X&filter=fund_name&type=monthly_portfolio (step 2)
             year=Y&filter=year&type=monthly_portfolio&scheme_code=X (step 3)

Since year/month only appear after selecting a specific fund, we pick the
first Equity fund to discover available year/months, then use that for all
scheme downloads.

The _parse_year_month_options and _parse_scheme_options methods are extracted
for testability.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_NAMES
from lib.scheme_filter import MatchReport, match_schemes

from .base import (
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf24")

_PORTFOLIO_FILES_URL = "https://www.licmf.com/downloads/portfolio-files"
_XLSX_HREF_RE = re.compile(r'href="([^"]+\.xlsx[^"]*)"', re.IGNORECASE)

# CSS selectors — the LIC page uses name= not id= on its form selects.
SEL_CATEGORY = 'select[name="fund_category"]'
SEL_FUND     = 'select[name="fund_name"]'
SEL_YEAR     = 'select[name="year"]'
SEL_MONTH    = 'select[name="month"]'
SEL_SUBMIT   = 'button.monthly-submit-btn'


def _parse_year_month_options(
    years: list[str], months: list[str],
) -> Optional[tuple[int, int]]:
    """Given raw year/month option strings, return (latest_year, latest_month)."""
    int_years = sorted([int(y) for y in years if y.isdigit()], reverse=True)
    if not int_years:
        return None
    latest_year = int_years[0]
    month_nums = []
    for m in months:
        ml = m.strip().lower()
        if ml in ALL_MONTHS:
            month_nums.append(ALL_MONTHS[ml])
    if not month_nums:
        return None
    return latest_year, max(month_nums)


def _parse_scheme_options(options: list[tuple[str, str]]) -> list[SchemeEntry]:
    """Given [(value, display_text)] from the fund_name dropdown,
    return list of SchemeEntry with text=display_name.
    The option value (scheme_code) is stored in SchemeEntry.url for later use
    in the POST request to /downloads/portfolio-files."""
    return [
        SchemeEntry(text=text.strip(), url=value)
        for value, text in options
        if value and text.strip()
    ]


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.licmf.com/downloads/monthly-portfolio"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def _select_equity_category(self, page):
        page.select_option(SEL_CATEGORY, "Equity")
        page.wait_for_timeout(3000)

    def latest_month_label(self, page):
        self._select_equity_category(page)

        # Read scheme options from the now-populated fund_name dropdown
        fund_options = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'select[name=\"fund_name\"] option'))"
            ".map(o => [o.value, (o.textContent || '').trim()])"
            ".filter(([v, t]) => v && t && t !== 'Scheme Name')"
        ) or []
        if not fund_options:
            raise NoDataYetError("LIC MF: no fund options after category select")

        # The form is cascading: year populates after selecting a fund, month
        # populates after selecting a year. Pick the first fund to discover
        # available year/month options.
        first_fund_code = fund_options[0][0]
        log.info("LIC MF: selecting fund %s to discover year/month", first_fund_code)
        page.select_option(SEL_FUND, first_fund_code)
        page.wait_for_timeout(3000)

        # Read year options
        years = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'select[name=\"year\"] option'))"
            ".map(o => o.value).filter(v => v)"
        ) or []
        if not years:
            raise NoDataYetError("LIC MF: no year options after fund select")

        # Select the latest year to populate month
        int_years = sorted([int(y) for y in years if y.isdigit()], reverse=True)
        if not int_years:
            raise NoDataYetError("LIC MF: no valid year values")
        latest_year_str = str(int_years[0])
        page.select_option(SEL_YEAR, latest_year_str)
        page.wait_for_timeout(3000)

        # Read month options
        months = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'select[name=\"month\"] option'))"
            ".map(o => o.textContent.trim()).filter(v => v && v !== 'Month')"
        ) or []

        result = _parse_year_month_options(years, months)
        if not result:
            raise NoDataYetError("LIC MF: no year/month options found")
        year, month = result
        self._sel_year = str(year)
        self._sel_month = MONTH_NAMES[month - 1]
        return year, month, date(year, month, 1)

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        options = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'select[name=\"fund_name\"] option'))"
            ".map(o => [o.value, (o.textContent || '').trim()])"
            ".filter(([v, t]) => v && t && t !== 'Scheme Name')"
        ) or []
        return _parse_scheme_options(options)

    # ------------------------------------------------------------------
    # Override download: the submit button fires an AJAX POST that returns
    # an HTML fragment with the xlsx link — NOT a browser download event.
    # ------------------------------------------------------------------
    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        entries = getattr(self, "_entries", None)
        if entries is None:
            self.discover_latest_month(fetcher)
            entries = getattr(self, "_entries", None)
        if entries is None:
            raise ScraperError(
                f"{self.mf.name}: discover_latest_month did not populate _entries"
            )
        page = getattr(self, "_page", None)
        host = getattr(self, "_host", host_of(self.DISCLOSURES_URL))

        # Match scheme names
        text_to_entry: dict[str, SchemeEntry] = {}
        link_pairs: list[tuple[str, str]] = []
        for i, e in enumerate(entries):
            placeholder = e.url if e.url else f"__entry_{i}__"
            link_pairs.append((e.text, placeholder))
            text_to_entry[e.text] = e

        report: MatchReport = match_schemes(self.mf.schemes, link_pairs)
        log.info(report.summary(self.mf.id, self.mf.name))
        self._match_report = report

        sel_year = self._sel_year
        sel_month_num = str(ALL_MONTHS.get(self._sel_month.lower(), ""))

        files: list[DownloadedFile] = []
        for m in report.matched:
            entry = text_to_entry[m.link_text]
            scheme_code = entry.url  # stored the option value here
            if not scheme_code:
                log.warning("LIC: no scheme_code for %s", m.scheme_name)
                continue

            # POST to /downloads/portfolio-files from within the page context
            # to preserve session cookies and CSRF tokens.
            resp_html = page.evaluate("""
                async (params) => {
                    const body = new URLSearchParams({
                        scheme_code: params.code,
                        fund_name: '',
                        type: 'monthly_portfolio',
                        month: params.month,
                        year: params.year,
                    });
                    const resp = await fetch('/downloads/portfolio-files', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body: body.toString(),
                    });
                    return await resp.text();
                }
            """, {"code": scheme_code, "year": sel_year, "month": sel_month_num})

            href_match = _XLSX_HREF_RE.search(resp_html or "")
            if not href_match:
                log.warning("LIC: no xlsx link in response for %s (%s): %s",
                            m.scheme_name, scheme_code, (resp_html or "")[:200])
                continue
            xlsx_path = href_match.group(1)
            xlsx_url = f"https://www.licmf.com{xlsx_path}" if xlsx_path.startswith("/") else xlsx_path

            safe_seg = "".join(c for c in m.scheme_name if c.isalnum())[:20]
            dest = fresh_dest(f"{self.mf.id}-{safe_seg}", "xlsx")

            ok = fetcher.browser.download_file(
                xlsx_url, dest, "www.licmf.com",
                referer=self.DISCLOSURES_URL,
                expected_signatures=(),
            )
            if not ok:
                log.warning("LIC: download failed for %s: %s", m.scheme_name, xlsx_url)
                continue
            files.append(DownloadedFile(
                src_path=dest,
                scheme_name=m.scheme_name,
                source_url=xlsx_url,
                label=m.scheme_name,
            ))

        if not files:
            raise ScraperError(f"{self.mf.name}: no schemes downloaded")
        return files
