"""Pattern: month dropdown where some recent months may have no data.

Currently only Jio BlackRock — site lists current FY's months but only
populates the ones already disclosed. Iterate backward from newest until
one has a real download link.

Subclass contract:
    DISCLOSURES_URL : str
    def dismiss_consent(self, page): optional
    def available_months_newest_first(self, page) -> list[tuple[int, int, str]]:
        Return [(year, month, dropdown_value_or_token), ...] from the
        current page's month picker, newest first.
    def link_for_month(self, page, month_token: str, year: int, month: int):
        Click the appropriate dropdown option, return (url, label, as_on)
        for that month — or None if that month has no data.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from lib.fetcher import Fetcher, SIG_XLSX, fresh_dest
from lib.log import get_logger
from lib.month_hint import parse_as_on

from ..base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)

log = get_logger("pattern.toggle")

MAX_BACKWARD_STEPS = 6


class ToggleUntilDataScraper(BaseScraper):
    PATTERN = "toggle_until_data"

    DISCLOSURES_URL: str = ""

    def dismiss_consent(self, page) -> None:
        return None

    def available_months_newest_first(self, page) -> list[tuple[int, int, str]]:
        raise NotImplementedError

    def link_for_month(self, page, month_token: str, year: int, month: int):
        """Return (url, label, as_on) or None if no data for this month."""
        raise NotImplementedError

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        host = host_of(self.DISCLOSURES_URL)
        page = fetcher.browser.open_page(self.DISCLOSURES_URL, host)
        try:
            self.dismiss_consent(page)
            months = self.available_months_newest_first(page)
            if not months:
                raise NoDataYetError(f"{self.mf.name}: no months listed at all")
            tried = 0
            for year, month, token in months:
                if tried >= MAX_BACKWARD_STEPS:
                    log.warning("%s: hit MAX_BACKWARD_STEPS=%d", self.mf.name, MAX_BACKWARD_STEPS)
                    break
                tried += 1
                hit = self.link_for_month(page, token, year, month)
                if hit:
                    url, label, as_on = hit
                    if not as_on:
                        as_on = parse_as_on(label, url)
                    self._url = url
                    self._label = label
                    return DiscoveryResult(
                        year=year, month=month, as_on_date=as_on,
                        available_months=[(y, m) for (y, m, _) in months],
                        notes=f"selected month after {tried} toggles",
                    )
            raise NoDataYetError(f"{self.mf.name}: no toggled month had data within {tried} steps")
        finally:
            try:
                page.close()
            except Exception:
                pass

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = self._url
        host = host_of(url) or host_of(self.DISCLOSURES_URL)
        dest = fresh_dest(self.mf.id, "xlsx")
        ok = fetcher.browser.download_file(
            url, dest, host,
            referer=self.DISCLOSURES_URL,
            expected_signatures=(SIG_XLSX,),
        )
        if not ok:
            raise ScraperError(f"{self.mf.name}: download failed for {url}")
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=url,
            label=self.mf.name,
        )]
