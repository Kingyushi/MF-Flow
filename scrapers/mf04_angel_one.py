"""Angel One Mutual Fund — factsheet PDF via direct URL construction.

The /downloads page lists factsheets via a WordPress media tab, but the page
itself is IP-blocked from cloud hosts (Cloudflare). Direct cms.angelonemf.com
URLs work from any IP.

URL pattern:
    https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/15/Factsheet-Angel-One-Mutual-Fund-Schemes-<Mon3>-<YYYY>.pdf

Strategy:
1. Try direct URL construction first (works on droplet, fast on Windows).
2. Iterate Mon3 backward from current month until a HEAD returns 200.
3. Fallback to page-based discovery only when no constructed URL exists.
"""
from __future__ import annotations

from datetime import date

import requests

from lib.fetcher import _proxy_dict_for
from lib.log import get_logger
from lib.month_hint import MONTH_NAMES

from .base import DiscoveryResult, NoDataYetError
from .patterns.factsheet import FactsheetOnlyScraper

log = get_logger("mf04")

_CMS_BASE = "https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/15"


def _mon3(month: int) -> str:
    """3-letter month abbreviation as Angel One uses it."""
    return MONTH_NAMES[month - 1][:3]


def _angel_url(year: int, month: int) -> str:
    return f"{_CMS_BASE}/Factsheet-Angel-One-Mutual-Fund-Schemes-{_mon3(month)}-{year}.pdf"


class Scraper(FactsheetOnlyScraper):
    DISCLOSURES_URL = "https://www.angelonemf.com/downloads"

    def discover_latest_month(self, fetcher):
        # Bypass the IP-blocked /downloads page entirely. Iterate factsheet
        # URLs backward from current month until one returns HTTP 200.
        today = date.today()
        y, m = today.year, today.month
        H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
        for _ in range(6):
            url = _angel_url(y, m)
            try:
                r = requests.head(
                    url, timeout=10, allow_redirects=True, headers=H,
                    proxies=_proxy_dict_for("cms.angelonemf.com"),
                )
                if r.status_code == 200:
                    self._url = url
                    self._label = f"Factsheet Angel One Mutual Fund Schemes {_mon3(m)} {y}"
                    return DiscoveryResult(year=y, month=m, as_on_date=date(y, m, 1))
            except Exception:
                pass
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        raise NoDataYetError("Angel One: no Factsheet URL responded with 200")

    # find_latest_factsheet is no longer called (we override discover_latest_month
    # to bypass page navigation entirely), but keep a stub for completeness.
    def find_latest_factsheet(self, page):
        raise RuntimeError("Angel One bypasses page navigation; this should not be called")
