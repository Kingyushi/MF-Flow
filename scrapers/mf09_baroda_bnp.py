"""Baroda BNP Paribas Mutual Fund — single .xls per month.

Page surfaces "MONTHLY PORTFOLIO OF SCHEME" section with multiple download
links (READ/DOWNLOAD/Copy Link/WhatsApp) all pointing to the same file.
URL pattern: BOBBNPMF_Monthly_Portfolio_<DD-MM-YYYY>_<id>.xls

NOTE: site serves .xls, not .xlsx. Our fetcher's xlsx signature check (PK)
also matches .xls if it's the new format, but legacy .xls uses CFB header
(D0 CF 11 E0). Drop the signature check for this scraper.
"""
from __future__ import annotations

import re
from datetime import date

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)
from .patterns.single_xlsx import SingleXlsxScraper

log = get_logger("mf09")


# URL pattern: ...BOBBNPMF_Monthly_Portfolio_30-04-2026_18070.xls
_URL_DATE_RE = re.compile(
    r"BOBBNPMF_Monthly_Portfolio_(\d{2})-(\d{2})-(\d{4})_\d+\.xls",
    re.IGNORECASE,
)


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.barodabnpparibasmf.in/downloads/monthly-portfolio-scheme"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(4000)

    def find_target(self, page):
        from .patterns.single_xlsx import Target
        # Find any anchor pointing at a BOBBNPMF_Monthly_Portfolio file.
        rows = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => /BOBBNPMF_Monthly_Portfolio/i.test(a.href || ''))
                .filter(a => (a.href||'').toLowerCase().endsWith('.xls') || (a.href||'').toLowerCase().endsWith('.xlsx'))
                .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
        """)
        if not rows:
            raise NoDataYetError("Baroda BNP: no Monthly_Portfolio anchor")
        # Pick the row with the latest date encoded in the URL.
        best, best_d = None, None
        for r in rows:
            m = _URL_DATE_RE.search(r["href"])
            if not m:
                continue
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if best_d is None or d > best_d:
                best_d = d
                best = r
        if not best:
            raise NoDataYetError("Baroda BNP: no date parsed from any URL")
        return Target(
            year=best_d.year, month=best_d.month,
            label=f"Baroda BNP Monthly Portfolio {best_d.isoformat()}",
            as_on=best_d, kind="url", payload=best["href"],
        )

    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        # Override the base's xlsx-only download to allow .xls without signature check.
        t = getattr(self, "_target", None)
        if t is None:
            self.discover_latest_month(fetcher)
            t = self._target
        ext = "xls" if str(t.payload).lower().endswith(".xls") else "xlsx"
        dest = fresh_dest(self.mf.id, ext)
        host = host_of(t.payload) or host_of(self.DISCLOSURES_URL)
        ok = fetcher.browser.download_file(
            t.payload, dest, host,
            referer=self.DISCLOSURES_URL,
            expected_signatures=(),  # legacy .xls has different magic
        )
        if not ok:
            raise ScraperError(f"{self.mf.name}: download failed")
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=t.payload,
            label=self.mf.name,
        )]
