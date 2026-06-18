"""Bajaj Finserv Mutual Fund — single multi-sheet xlsx.

Page (www.bajajamc.com) is IP-blocked from cloud hosts but the file CDN
(media.bajajamc.com) is open. URL pattern is fully constructible:

    https://media.bajajamc.com/wp-content/uploads/<pub_yyyy>/<pub_mm>/Bajaj-Finserv-Mutual-Fund_Monthly-Portfolio-as-on-<DD>-<Mon3>-<yyyy>.xlsx

where DD is the last day of the data month and pub_yyyy/pub_mm is the data
month + 1 (April data published in May → /2026/05/).
"""
from __future__ import annotations

import calendar
from datetime import date

import requests

from lib.fetcher import _proxy_dict_for
from lib.log import get_logger
from lib.month_hint import MONTH_NAMES

from .base import NoDataYetError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf06")


def _bajaj_url(year: int, month: int) -> str:
    day = calendar.monthrange(year, month)[1]
    pub_year = year if month < 12 else year + 1
    pub_month = month + 1 if month < 12 else 1
    mon3 = MONTH_NAMES[month - 1][:3]
    return (
        f"https://media.bajajamc.com/wp-content/uploads/"
        f"{pub_year}/{pub_month:02d}/"
        f"Bajaj-Finserv-Mutual-Fund_Monthly-Portfolio-as-on-{day:02d}-{mon3}-{year}.xlsx"
    )


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.bajajamc.com/downloads?portfolio="

    def discover_latest_month(self, fetcher):
        # Bypass IP-blocked /downloads page. Iterate URLs backward from current
        # month; first HTTP 200 wins.
        today = date.today()
        y, m = today.year, today.month
        H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
        for _ in range(6):
            url = _bajaj_url(y, m)
            try:
                r = requests.head(
                    url, timeout=10, allow_redirects=True, headers=H,
                    proxies=_proxy_dict_for("media.bajajamc.com"),
                )
                if r.status_code == 200:
                    from .base import DiscoveryResult
                    mon3 = MONTH_NAMES[m - 1][:3]
                    day = calendar.monthrange(y, m)[1]
                    self._target = Target(
                        year=y, month=m,
                        label=f"Bajaj Finserv Monthly Portfolio {mon3} {y}",
                        as_on=date(y, m, day), kind="url", payload=url,
                    )
                    self._page = None  # Skip page reuse in download().
                    self._host = "media.bajajamc.com"
                    return DiscoveryResult(year=y, month=m, as_on_date=date(y, m, day))
            except Exception:
                pass
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        raise NoDataYetError("Bajaj Finserv: no URL responded with 200")

    # find_target is unreachable when discover_latest_month succeeds (we set
    # self._target directly), but keep a stub.
    def find_target(self, page) -> Target:
        raise RuntimeError("Bajaj bypasses page navigation; this should not be called")
