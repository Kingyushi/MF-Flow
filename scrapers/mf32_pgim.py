"""PGIM India Mutual Fund — API-driven per-scheme xlsx.

Page structure (Angular SPA):
The probe captured two critical API endpoints:

1. /api/v1/brochure/disclosure/section — returns the full section/tab structure
   including the "Monthly Portfolio" section (SectionId "SECTION_747960037")
   with tabs: Equity (TabId 12), Debt (13), Fund of Funds (14), Prior to June
   2021 (66).

2. /api/v1/brochure/published/disclosure — returns the actual disclosure entries
   for a given section+tab. Each entry has: title, pdfPath (which is actually
   xlsx despite the name), dateMonthYear, year, month, date.

The SPA calls these APIs from its Angular frontend. The probe captured
body_samples with full JSON structure. We can call these APIs directly via
Fetcher.static (no Playwright needed), then parse the response to find
the latest entries under Equity tab.

The pdfPath URLs look like:
  https://www.pgimindia.com/api/v1/brochure/about-us/image/<filename>

Post-June-2021 entries are per-scheme xlsx files (one per fund).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_FULL, parse_as_on

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)

log = get_logger("mf32")

API_BASE = "https://www.pgimindia.com/api/v1/brochure"
DISCLOSURES_URL = "https://www.pgimindia.com/mutual-funds/disclosures/Portfolios/Monthly-Portfolio"

# Section and Tab IDs from the disclosure/section API response
SECTION_MONTHLY = "SECTION_747960037"
TAB_EQUITY = 12


def _parse_disclosure_entries(data: list[dict]) -> list[dict]:
    """Pure parse: extract and sort disclosure entries from API response.

    Filters to Equity tab monthly portfolio entries, parses year/month,
    returns sorted newest-first.
    """
    results = []
    for tab_group in data:
        tab_id = tab_group.get("tabId")
        if tab_id != TAB_EQUITY:
            continue
        for entry in tab_group.get("content", []):
            title = entry.get("title", "")
            year_str = entry.get("year", "")
            month_str = entry.get("month", "")
            pdf_path = entry.get("pdfPath", "")

            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue

            month_num = ALL_MONTHS.get((month_str or "").lower())
            if not month_num:
                continue

            results.append({
                "title": title,
                "url": pdf_path,
                "year": year,
                "month": month_num,
                "date_str": entry.get("dateMonthYear", ""),
            })

    results.sort(key=lambda e: (e["year"], e["month"]), reverse=True)
    return results


class Scraper(BaseScraper):
    PATTERN = "per_scheme_xlsx"

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        host = host_of(DISCLOSURES_URL)

        # The disclosure API requires POST with a JSON body containing the sectionId.
        # GET returns HTTP 405; POST without sectionId returns a generic error.
        import json
        import requests as _requests

        url = f"{API_BASE}/published/disclosure"
        session = fetcher.static._session(host)
        fetcher.static._polite(host)
        resp = session.post(
            url,
            json={"sectionId": SECTION_MONTHLY},
            timeout=30,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.pgimindia.com",
                "Referer": DISCLOSURES_URL,
            },
        )
        if not resp.ok:
            raise ScraperError(f"PGIM disclosure API HTTP {resp.status_code}")

        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise ScraperError(f"PGIM: JSON parse error: {e}")

        data = body.get("data", [])
        if not data:
            raise NoDataYetError("PGIM: no data in disclosure API response")

        entries = _parse_disclosure_entries(data)
        if not entries:
            raise NoDataYetError("PGIM: no Equity monthly portfolio entries")

        # Find latest month
        latest_year = entries[0]["year"]
        latest_month = entries[0]["month"]
        at_latest = [e for e in entries if e["year"] == latest_year and e["month"] == latest_month]

        as_on: Optional[date] = None
        for e in at_latest:
            as_on = parse_as_on(e.get("date_str", ""), e.get("title", ""))
            if as_on:
                break

        self._entries = at_latest
        self._host = host
        return DiscoveryResult(year=latest_year, month=latest_month, as_on_date=as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        entries = getattr(self, "_entries", None)
        if entries is None:
            self.discover_latest_month(fetcher)
            entries = getattr(self, "_entries", None)
        if entries is None:
            raise ScraperError("PGIM: no entries after discovery")

        host = getattr(self, "_host", host_of(DISCLOSURES_URL))

        from lib.scheme_filter import match_schemes

        # Build link pairs for scheme matching
        link_pairs = [(e["title"], e["url"]) for e in entries]
        report = match_schemes(self.mf.schemes, link_pairs)
        log.info(report.summary(self.mf.id, self.mf.name))

        files: list[DownloadedFile] = []
        for m in report.matched:
            # Find the entry by title
            entry = next((e for e in entries if e["title"] == m.link_text), None)
            if not entry:
                continue
            url = entry["url"]
            if not url:
                log.warning("PGIM: no URL for %s", m.scheme_name)
                continue

            safe_seg = "".join(c for c in m.scheme_name if c.isalnum())[:20]
            # Detect extension from URL
            ext = "xlsx"
            if url.lower().endswith(".xlsb"):
                ext = "xlsb"
            dest = fresh_dest(f"{self.mf.id}-{safe_seg}", ext)

            ok = fetcher.static.download_file(
                url, dest, host_of(url) or host,
                referer=DISCLOSURES_URL,
                expected_signatures=(),
            )
            if not ok:
                # Try browser download as fallback
                ok = fetcher.browser.download_file(
                    url, dest, host_of(url) or host,
                    referer=DISCLOSURES_URL,
                    expected_signatures=(),
                )
            if not ok:
                log.warning("PGIM: download failed for %s", m.scheme_name)
                continue

            files.append(DownloadedFile(
                src_path=dest,
                scheme_name=m.scheme_name,
                source_url=url,
                label=m.scheme_name,
            ))

        if not files:
            raise ScraperError(f"{self.mf.name}: no schemes downloaded")
        return files
