"""Pattern: AMC publishes ONE zip per month containing per-scheme files.

Examples: DSP, ICICI Prudential.

Subclass contract: same as SingleXlsxScraper.find_latest_link, but the URL
points to a zip. After download, the zip is preserved verbatim AND
unzipped into the same month folder (the user wants raw files).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from lib.fetcher import Fetcher, fresh_dest
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

log = get_logger("pattern.zip")

# Zip header. Used as signature for download verification.
SIG_ZIP = b"PK\x03\x04"


class LatestMonthZipScraper(BaseScraper):
    PATTERN = "latest_month_zip"

    DISCLOSURES_URL: str = ""

    def dismiss_consent(self, page) -> None:
        return None

    def find_latest_link(self, page):
        """Return (zip_url, label_text, as_on_date_or_None)."""
        raise NotImplementedError

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        host = host_of(self.DISCLOSURES_URL)
        page = fetcher.browser.open_page(self.DISCLOSURES_URL, host)
        try:
            self.dismiss_consent(page)
            url, label, as_on = self.find_latest_link(page)
            if not url:
                raise NoDataYetError(f"{self.mf.name}: no download link visible")
            ym = (as_on.year, as_on.month) if as_on else try_infer(label, url)
            if not ym:
                raise ScraperError(f"{self.mf.name}: could not parse month from {label!r}")
            if not as_on:
                as_on = parse_as_on(label, url)
            self._discovered_url = url
            return DiscoveryResult(year=ym[0], month=ym[1], as_on_date=as_on)
        finally:
            try:
                page.close()
            except Exception:
                pass

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = self._discovered_url
        host = host_of(url) or host_of(self.DISCLOSURES_URL)
        zip_path = fresh_dest(self.mf.id, "zip")
        ok = fetcher.browser.download_file(
            url, zip_path, host,
            referer=self.DISCLOSURES_URL,
            expected_signatures=(SIG_ZIP,),
        )
        if not ok:
            raise ScraperError(f"{self.mf.name}: zip download failed for {url}")

        # Extract members into a sibling temp folder.
        out: list[DownloadedFile] = []
        extract_dir = zip_path.with_suffix("")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                target_path = extract_dir / Path(member).name
                with zf.open(member) as src, target_path.open("wb") as dst:
                    dst.write(src.read())
                out.append(DownloadedFile(
                    src_path=target_path,
                    scheme_name=None,
                    source_url=url,
                    label=Path(member).stem,
                ))
        # Also keep the zip itself.
        out.append(DownloadedFile(
            src_path=zip_path,
            scheme_name=None,
            source_url=url,
            label=f"{self.mf.name} - archive",
        ))
        return out
