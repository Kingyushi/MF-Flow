"""Pattern: AMC publishes ONE multi-sheet xlsx per month containing all schemes.

Subclass contract:
    DISCLOSURES_URL : str
    def dismiss_consent(self, page): optional
    def navigate_to_portfolio(self, page): optional, default no-op
        Use to click tabs, switch subcategories etc. before listing months.
    def find_target(self, page) -> Target:
        Return Target(year, month, as_on, kind, payload).
        kind is "url" (payload = absolute url string) OR
                "click" (payload = a callable that, when invoked, triggers a
                         download on `page` — wrapped in expect_download by base).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Literal, Optional, Union

from lib.fetcher import Fetcher, SIG_XLSX, fresh_dest
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

log = get_logger("pattern.single_xlsx")


@dataclass
class Target:
    year: int
    month: int
    label: str
    as_on: Optional[date]
    kind: Literal["url", "click"]
    payload: Union[str, Callable[[], None]]


class SingleXlsxScraper(BaseScraper):
    PATTERN = "single_xlsx_multi_sheet"

    DISCLOSURES_URL: str = ""

    def dismiss_consent(self, page) -> None:
        return None

    def navigate_to_portfolio(self, page) -> None:
        return None

    def find_target(self, page) -> Target:
        raise NotImplementedError

    def _open(self, fetcher: Fetcher):
        host = host_of(self.DISCLOSURES_URL)
        page = fetcher.browser.open_page(self.DISCLOSURES_URL, host)
        self.dismiss_consent(page)
        self.navigate_to_portfolio(page)
        return page, host

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        page, host = self._open(fetcher)
        try:
            target = self.find_target(page)
        except NoDataYetError:
            try:
                page.close()
            except Exception:
                pass
            raise
        # We keep the page alive across phases — runner calls discover then
        # download sequentially within one fetcher session.
        self._page = page
        self._host = host
        self._target = target
        if not target.as_on:
            target.as_on = parse_as_on(target.label)
        return DiscoveryResult(
            year=target.year, month=target.month, as_on_date=target.as_on,
        )

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        t = getattr(self, "_target", None)
        if t is None:
            self.discover_latest_month(fetcher)
            t = getattr(self, "_target", None)
        if t is None:
            raise ScraperError(
                f"{self.mf.name}: discover_latest_month returned without populating "
                "_target — subclass bug, check that the override sets self._target "
                "before returning DiscoveryResult"
            )
        page = getattr(self, "_page", None)
        host = getattr(self, "_host", host_of(self.DISCLOSURES_URL))

        # Honor the URL extension (.xls vs .xlsx). User wants raw files;
        # skip signature checks so legacy .xls (CFB) saves correctly.
        if t.kind == "url" and str(t.payload).lower().endswith(".xls"):
            dest = fresh_dest(self.mf.id, "xls")
        else:
            dest = fresh_dest(self.mf.id, "xlsx")
        if t.kind == "url":
            ok = fetcher.browser.download_file(
                t.payload, dest, host_of(t.payload) or host,
                referer=self.DISCLOSURES_URL,
                expected_signatures=(),
            )
            source_url = t.payload
        else:
            if page is None:
                page, host = self._open(fetcher)
                t = self.find_target(page)
                self._page = page
                self._target = t
            ok = fetcher.browser.click_to_download(
                page, t.payload, dest,
                expected_signatures=(),
            )
            source_url = self.DISCLOSURES_URL

        if not ok:
            raise ScraperError(f"{self.mf.name}: download failed for target {t.label!r}")
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=source_url,
            label=self.mf.name,
        )]
