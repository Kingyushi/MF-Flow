"""Pattern: AMC factsheet only (no portfolio xlsx). Angel One.

The user's spreadsheet has NIL schemes for this MF. Just grab the latest
factsheet PDF.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from lib.fetcher import Fetcher, SIG_PDF, fresh_dest
from lib.log import get_logger
from lib.month_hint import try_infer, parse_as_on

from ..base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)

log = get_logger("pattern.factsheet")


class FactsheetOnlyScraper(BaseScraper):
    PATTERN = "factsheet_only"

    DISCLOSURES_URL: str = ""

    def dismiss_consent(self, page) -> None:
        return None

    def find_latest_factsheet(self, page):
        """Return (url, label, as_on_date_or_None)."""
        raise NotImplementedError

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        host = host_of(self.DISCLOSURES_URL)
        page = fetcher.browser.open_page(self.DISCLOSURES_URL, host)
        try:
            self.dismiss_consent(page)
            url, label, as_on = self.find_latest_factsheet(page)
            if not url:
                raise NoDataYetError(f"{self.mf.name}: no factsheet link visible")
            ym = (as_on.year, as_on.month) if as_on else try_infer(label, url)
            if not ym:
                raise ScraperError(f"{self.mf.name}: could not parse month from {label!r}")
            self._url = url
            self._label = label
            return DiscoveryResult(year=ym[0], month=ym[1], as_on_date=as_on)
        finally:
            try:
                page.close()
            except Exception:
                pass

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = self._url
        host = host_of(url) or host_of(self.DISCLOSURES_URL)
        dest = fresh_dest(self.mf.id, "pdf")
        ok = fetcher.browser.download_file(
            url, dest, host,
            referer=self.DISCLOSURES_URL,
            expected_signatures=(SIG_PDF,),
        )
        if not ok:
            raise ScraperError(f"{self.mf.name}: factsheet download failed")
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=url,
            label=f"{self.mf.name} - Factsheet",
        )]
