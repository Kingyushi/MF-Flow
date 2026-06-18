"""Pattern: AMC publishes ONE xlsx per scheme per month. Filter by scheme list.

Subclass contract:
    DISCLOSURES_URL : str
    def dismiss_consent(self, page): optional
    def navigate_to_portfolio(self, page): optional, default no-op
    def latest_month_label(self, page) -> (year, month, as_on_or_None)
    def list_scheme_entries(self, page) -> list[SchemeEntry]
        Return [(visible_text, "url:<href>" | "click:<idx>"), ...].
        For click-driven sites, register a per-entry click via list_scheme_entries
        AND override fetch_scheme_file(page, entry, dest, fetcher).

For sites with stable URL links, override list_scheme_links(page) instead
which returns [(text, url), ...] and the base handles downloads via
download_file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from lib.fetcher import Fetcher, SIG_XLSX, fresh_dest
from lib.log import get_logger
from lib.scheme_filter import MatchReport, match_schemes

from ..base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)

log = get_logger("pattern.per_scheme")


@dataclass
class SchemeEntry:
    text: str
    url: Optional[str] = None
    click: Optional[Callable[[], None]] = None
    # Per-scheme month override (for AMCs with rolling publication where
    # different schemes are published in different months). When set, the
    # download flows these onto the resulting DownloadedFile so the runner
    # places each file in its own month folder.
    year: Optional[int] = None
    month: Optional[int] = None


class PerSchemeXlsxScraper(BaseScraper):
    PATTERN = "per_scheme_xlsx"

    DISCLOSURES_URL: str = ""

    def dismiss_consent(self, page) -> None:
        return None

    def navigate_to_portfolio(self, page) -> None:
        return None

    def latest_month_label(self, page):
        raise NotImplementedError

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
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
        ym_as = self.latest_month_label(page)
        if not ym_as:
            try:
                page.close()
            except Exception:
                pass
            raise NoDataYetError(f"{self.mf.name}: no month label")
        year, month, as_on = ym_as
        entries = self.list_scheme_entries(page)
        if not entries:
            try:
                page.close()
            except Exception:
                pass
            raise NoDataYetError(f"{self.mf.name}: no scheme entries")
        self._page = page
        self._host = host
        self._entries = entries
        return DiscoveryResult(year=year, month=month, as_on_date=as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        entries = getattr(self, "_entries", None)
        if entries is None:
            self.discover_latest_month(fetcher)
            entries = getattr(self, "_entries", None)
        if entries is None:
            raise ScraperError(
                f"{self.mf.name}: discover_latest_month returned without populating "
                "_entries — subclass bug, check that the override sets self._entries "
                "before returning DiscoveryResult"
            )
        page = getattr(self, "_page", None)
        host = getattr(self, "_host", host_of(self.DISCLOSURES_URL))

        # Match scheme names against entry texts. Build links list for matcher.
        text_to_entry: dict[str, SchemeEntry] = {}
        link_pairs: list[tuple[str, str]] = []
        for i, e in enumerate(entries):
            placeholder = e.url if e.url else f"__entry_{i}__"
            link_pairs.append((e.text, placeholder))
            text_to_entry[e.text] = e

        report: MatchReport = match_schemes(self.mf.schemes, link_pairs)
        log.info(report.summary(self.mf.id, self.mf.name))
        self._match_report = report

        files: list[DownloadedFile] = []
        download_failures: list[str] = []
        for m in report.matched:
            entry = text_to_entry[m.link_text]
            safe_seg = "".join(c for c in m.scheme_name if c.isalnum())[:20]
            dest = fresh_dest(f"{self.mf.id}-{safe_seg}", "xlsx")
            if entry.url:
                ok = fetcher.browser.download_file(
                    entry.url, dest, host_of(entry.url) or host,
                    referer=self.DISCLOSURES_URL,
                    expected_signatures=(),
                )
                source_url = entry.url
            elif entry.click and page:
                ok = fetcher.browser.click_to_download(
                    page, entry.click, dest,
                    expected_signatures=(),
                )
                source_url = self.DISCLOSURES_URL
            else:
                log.warning("Entry has no url or click action: %s", m.scheme_name)
                download_failures.append(m.scheme_name)
                continue
            if not ok:
                log.warning("download failed for %s", m.scheme_name)
                download_failures.append(m.scheme_name)
                continue
            files.append(DownloadedFile(
                src_path=dest,
                scheme_name=m.scheme_name,
                source_url=source_url,
                label=m.scheme_name,
                year=entry.year,
                month=entry.month,
            ))
        # Expose failures so the runner can surface them in STATUS / reports —
        # otherwise a partial outcome reads as "OK" and silent data loss hides.
        self._download_failures = download_failures
        if not files:
            raise ScraperError(f"{self.mf.name}: no schemes downloaded")
        return files
