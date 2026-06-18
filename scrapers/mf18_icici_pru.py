"""ICICI Prudential Mutual Fund — monthly zip via direct URL construction.

The /media-center/downloads page is React + IP-blocked from cloud hosts, but
the blob URL is open and predictable:

    https://www.icicipruamc.com/blob/downloads/Files/Monthly%20Portfolio%20Disclosures/<yyyy>/<MonShort>/Monthly-Portfolio-Disclosure-<MonthFull>-<yyyy>.zip

We probe URLs backward from the current month. First HTTP 200 wins.
"""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import requests

from lib.fetcher import Fetcher, _proxy_dict_for, fresh_dest
from lib.log import get_logger
from lib.month_hint import MONTH_NAMES

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    host_of,
    retry,
)
from .patterns.zip_pattern import LatestMonthZipScraper

log = get_logger("mf18")


def _icici_url(year: int, month: int) -> str:
    mon_short = MONTH_NAMES[month - 1][:3]
    mon_full = MONTH_NAMES[month - 1]
    return (
        f"https://www.icicipruamc.com/blob/downloads/Files/"
        f"Monthly%20Portfolio%20Disclosures/{year}/{mon_short}/"
        f"Monthly-Portfolio-Disclosure-{mon_full}-{year}.zip"
    )


class Scraper(LatestMonthZipScraper):
    DISCLOSURES_URL = "https://www.icicipruamc.com/media-center/downloads?currentTabFilter=Disclosures&&subCatTabFilter=MonthlyPortfolioDisclosures"

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        today = date.today()
        y, m = today.year, today.month
        H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
        proxies = _proxy_dict_for("www.icicipruamc.com")
        for _ in range(6):
            url = _icici_url(y, m)
            try:
                r = requests.head(url, timeout=10, allow_redirects=True, headers=H, proxies=proxies)
                if r.status_code == 200:
                    self._discovered_url = url
                    return DiscoveryResult(year=y, month=m, as_on_date=date(y, m, 1))
            except Exception:
                pass
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        raise NoDataYetError("ICICI Pru: no Monthly Portfolio zip URL responded with 200")

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = self._discovered_url
        host = host_of(url) or host_of(self.DISCLOSURES_URL)
        zip_path = fresh_dest(self.mf.id, "zip")
        ok = fetcher.browser.download_file(
            url, zip_path, host,
            referer=self.DISCLOSURES_URL,
            expected_signatures=(b"PK\x03\x04",),
        )
        if not ok:
            raise ScraperError(f"{self.mf.name}: zip download failed for {url}")

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
        out.append(DownloadedFile(
            src_path=zip_path,
            scheme_name=None,
            source_url=url,
            label=f"{self.mf.name} - archive",
        ))
        return out
