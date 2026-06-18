"""Invesco Mutual Fund — XML API for monthly holdings.

The site's literature page calls `/api/CompleteMonthlyHoldings?year=YYYY&classification=equity`
which returns ArrayOfclsCompleteMonthlyHoldings XML. Each scheme entry has
<Name> + per-month <AprUrl>/<MarUrl>/etc.

Hit the API directly instead of fighting the JS UI.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_NAMES

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf19")

_NS = "{http://schemas.datacontract.org/2004/07/SitefinityWebApp.Models}"
_MONTH_SHORT_TAGS = [
    ("AprUrl", "AprName", 4),
    ("MayUrl", "MayName", 5),
    ("JunUrl", "JunName", 6),
    ("JulUrl", "JulName", 7),
    ("AugUrl", "AugName", 8),
    ("SepUrl", "SepName", 9),
    ("OctUrl", "OctName", 10),
    ("NovUrl", "NovName", 11),
    ("DecUrl", "DecName", 12),
    ("JanUrl", "JanName", 1),
    ("FebUrl", "FebName", 2),
    ("MarUrl", "MarName", 3),
]


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://invescomutualfund.com/literature-and-form?tab=Complete"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(5000)

    def navigate_to_portfolio(self, page) -> None:
        pass

    def _fetch_api(self, fetcher, year: int, classification: str) -> list[dict]:
        """Hit the CompleteMonthlyHoldings API and parse the per-scheme rows."""
        url = f"https://invescomutualfund.com/api/CompleteMonthlyHoldings?year={year}&classification={classification}"
        result = fetcher.static.fetch_html(url, "invescomutualfund.com")
        if not result.ok or not result.html:
            return []
        try:
            root = ET.fromstring(result.html)
        except ET.ParseError:
            return []
        out = []
        for entry in root:
            name_el = entry.find(f"{_NS}Name")
            if name_el is None or not (name_el.text or "").strip():
                continue
            name = name_el.text.strip()
            row = {"name": name}
            for url_tag, name_tag, month_num in _MONTH_SHORT_TAGS:
                u = entry.find(f"{_NS}{url_tag}")
                if u is not None and (u.text or "").strip():
                    row[month_num] = u.text.strip()
            out.append(row)
        return out

    def discover_latest_month(self, fetcher):
        # Override base — Invesco uses an XML API, no need for a browser page.
        today = date.today()
        rows = []
        for cls in ("equity", "hybrid", "fixed-income"):
            rows.extend(self._fetch_api(fetcher, today.year, cls))
        if not rows:
            raise NoDataYetError("Invesco: API returned no rows")
        # Find the LATEST month with at least one valid URL.
        all_months = set()
        for r in rows:
            for k in r:
                if isinstance(k, int):
                    all_months.add(k)
        if not all_months:
            raise NoDataYetError("Invesco: no month columns populated")
        # Map calendar year to each month — current calendar year for months
        # 1..today.month, previous year otherwise.
        candidates = []
        for m in all_months:
            year = today.year if m <= today.month else today.year - 1
            candidates.append((year, m))
        candidates.sort()
        # Get the LATEST (year, month) that actually has data — try months
        # closest to today first.
        latest = max(candidates)
        self._rows = rows
        self._latest_month = latest[1]
        self._latest_year = latest[0]
        from .base import DiscoveryResult
        return DiscoveryResult(year=latest[0], month=latest[1], as_on_date=date(latest[0], latest[1], 1))

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        # Unused — discover_latest_month already fetched everything.
        return []

    def download(self, fetcher, target):
        # Build entries from in-memory rows + selected month, run matcher + download.
        from .base import DownloadedFile, ScraperError
        from lib.fetcher import fresh_dest
        from lib.scheme_filter import match_schemes

        rows = self._rows
        month = self._latest_month
        entries = []
        link_pairs = []
        for r in rows:
            u = r.get(month)
            if u:
                entries.append((r["name"], u))
                link_pairs.append((r["name"], u))
        if not entries:
            raise ScraperError(f"{self.mf.name}: no rows had URL for month {month}")
        report = match_schemes(self.mf.schemes, link_pairs)
        log.info(report.summary(self.mf.id, self.mf.name))
        self._match_report = report

        files: list[DownloadedFile] = []
        for m in report.matched:
            safe_seg = "".join(c for c in m.scheme_name if c.isalnum())[:20]
            dest = fresh_dest(f"{self.mf.id}-{safe_seg}", "xlsx")
            ok = fetcher.browser.download_file(
                m.link_url, dest, "invescomutualfund.com",
                referer=self.DISCLOSURES_URL,
                expected_signatures=(),
            )
            if not ok:
                log.warning("Invesco: download failed for %s", m.scheme_name)
                continue
            files.append(DownloadedFile(
                src_path=dest,
                scheme_name=m.scheme_name,
                source_url=m.link_url,
                label=m.scheme_name,
            ))
        if not files:
            raise ScraperError(f"{self.mf.name}: no scheme files downloaded")
        return files
