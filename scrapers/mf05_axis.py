"""Axis Mutual Fund — direct CMS API for Monthly Scheme Portfolios.

The SPA at transact.axismf.com loads a JSON manifest and then fires:
    /cms/api/statutory-disclosures-scheme?cat=Monthly%20Scheme%20Portfolios
which returns ALL files (consolidated + per-scheme, monthly + weekly + daily).

We filter to:
    field_aboutus_scheme_code == "Consolidated"
    field_pdf_name_statutory contains "Monthly Portfolio"
    (exclude weekly, daily, adhoc)

Then pick the latest by (field_year, field_months). The download URL is
    https://transact.axismf.com{field_related_file}
"""
from __future__ import annotations

import re
from urllib.parse import unquote

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, parse_as_on

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    retry,
)

log = get_logger("mf05")

_API_URL = "https://transact.axismf.com/cms/api/statutory-disclosures-scheme?cat=Monthly%20Scheme%20Portfolios"
_BASE_URL = "https://transact.axismf.com"


def _is_monthly_portfolio(entry: dict) -> bool:
    """True if the entry is a monthly consolidated portfolio (not weekly/daily/adhoc)."""
    name = (entry.get("field_pdf_name_statutory") or "").lower()
    if "weekly" in name or "daily" in name or "adhoc" in name:
        return False
    if "monthly" in name or "in_mf_monthly" in name:
        return True
    fpath = (entry.get("field_related_file") or "").lower()
    if "monthly" in fpath:
        return True
    return False


def _parse_api_entries(entries: list[dict]) -> list[dict]:
    """Pure parse: filter to monthly consolidated entries, add year/month ints.

    This is the testable pure function. Returns list sorted newest-first.
    """
    results = []
    for e in entries:
        code = e.get("field_aboutus_scheme_code", "")
        if code != "Consolidated":
            continue
        if not _is_monthly_portfolio(e):
            continue
        year_str = e.get("field_year", "")
        month_str = (e.get("field_months") or "").strip().lower()
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            continue
        month = ALL_MONTHS.get(month_str)
        if not month:
            continue
        results.append({**e, "_year": year, "_month": month})
    results.sort(key=lambda d: (d["_year"], d["_month"]), reverse=True)
    return results


class Scraper(BaseScraper):
    PATTERN = "single_xlsx_multi_sheet"

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        # Fetch the API via the browser engine (shares stealth context)
        host = "transact.axismf.com"
        page = fetcher.browser.open_page(_API_URL, host)
        try:
            raw = page.evaluate("() => document.body?.innerText || ''")
        finally:
            try:
                page.close()
            except Exception:
                pass

        import json
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            raise ScraperError(f"Axis: API response not JSON: {e}")

        parsed = _parse_api_entries(data)
        if not parsed:
            raise NoDataYetError("Axis: no monthly consolidated portfolio entries in API")

        latest = parsed[0]
        year = latest["_year"]
        month = latest["_month"]
        fpath = latest.get("field_related_file", "")
        # URL-decode the path (it's double-encoded in the API)
        fpath = unquote(fpath)
        url = _BASE_URL + fpath

        name = latest.get("field_pdf_name_statutory", "")
        as_on = parse_as_on(name, fpath)

        self._download_url = url
        self._label = name or f"Monthly Portfolio {year}-{month:02d}"
        return DiscoveryResult(year=year, month=month, as_on_date=as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = getattr(self, "_download_url", None)
        if url is None:
            self.discover_latest_month(fetcher)
            url = self._download_url

        # Detect extension from URL
        if url.lower().endswith(".xls") or url.lower().endswith(".xlsb"):
            ext = url.rsplit(".", 1)[-1].lower()
        else:
            ext = "xlsx"
        dest = fresh_dest(self.mf.id, ext)

        ok = fetcher.browser.download_file(
            url, dest, "transact.axismf.com",
            referer="https://transact.axismf.com/statutory-disclosures",
            expected_signatures=(),
        )
        if not ok:
            raise ScraperError(f"Axis: download failed for {url[:140]}")
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=url,
            label=self.mf.name,
        )]

    @staticmethod
    def _parse_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Pure parse step for testing: filter links to monthly portfolio xlsx."""
        out = []
        for text, href in links:
            h = (href or "").lower()
            t = (text or "").lower()
            if not h.endswith(".xlsx") and ".xlsx" not in h:
                continue
            combined = f"{t} {h}"
            if "monthly" not in combined and "portfolio" not in combined:
                continue
            if any(ex in combined for ex in ("fortnightly", "half year", "factsheet")):
                continue
            out.append((text, href))
        return out
