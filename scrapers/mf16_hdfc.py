"""HDFC Mutual Fund — per-scheme xlsx via direct URL construction.

Both the discovery page (www.hdfcfund.com) AND the file CDN
(files.hdfcfund.com) are Cloudflare IP-reputation-blocked from cloud hosts.
URLs are fully constructible from a hardcoded scheme list — on Windows they
work direct; on the droplet they need MF_FLOW_PROXY set to a residential
proxy.

URL pattern:
    https://files.hdfcfund.com/s3fs-public/<yyyy>-<mm_pub>/Monthly%20<Scheme%20Name>%20-%20<DD>%20<Month>%20<yyyy>.xlsx

where:
- yyyy-mm_pub = data month + 1 (April data published in May → 2026-05)
- DD = last day of the data month
- Scheme Name uses HDFC's canonical casing (NOT necessarily user's xlsx
  casing — that's why scheme_filter handles 'Midcap' vs 'Mid Cap' etc.).
"""
from __future__ import annotations

import calendar
import urllib.parse
from datetime import date

import requests

from lib.fetcher import _proxy_dict_for, _should_proxy
from lib.log import get_logger
from lib.month_hint import MONTH_NAMES

from .base import DiscoveryResult, NoDataYetError, ScraperError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf16")

# Canonical HDFC scheme names as they appear in the file URLs. Verified
# against files.hdfcfund.com/s3fs-public/2026-05/.
HDFC_SCHEMES: list[str] = [
    "HDFC Value Fund",
    "HDFC Technology Fund",
    "HDFC Small Cap Fund",
    "HDFC Pharma and Healthcare Fund",
    "HDFC Multi Cap Fund",
    "HDFC Mid Cap Fund",
    "HDFC Large Cap Fund",
    "HDFC Large and Mid Cap Fund",
    "HDFC Innovation Fund",
    "HDFC Focused Fund",
    "HDFC Flexi Cap Fund",
    "HDFC Equity Savings Fund",
]


def _hdfc_url(scheme: str, year: int, month: int) -> str:
    day = calendar.monthrange(year, month)[1]
    pub_year = year if month < 12 else year + 1
    pub_month = month + 1 if month < 12 else 1
    month_name = MONTH_NAMES[month - 1]
    filename = f"Monthly {scheme} - {day} {month_name} {year}.xlsx"
    return (
        f"https://files.hdfcfund.com/s3fs-public/"
        f"{pub_year}-{pub_month:02d}/{urllib.parse.quote(filename)}"
    )


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio"

    def discover_latest_month(self, fetcher):
        # Skip the IP-blocked page. HEAD-probe constructed URLs for each
        # scheme, iterating backward from current month until at least one
        # 200 hit.
        today = date.today()
        y, m = today.year, today.month
        H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
        proxies = _proxy_dict_for("files.hdfcfund.com")
        # Bright Data residential injects its own CA — disable verify when proxied.
        verify = not _should_proxy("files.hdfcfund.com")
        seen_403 = False
        for _ in range(6):
            hits: list[SchemeEntry] = []
            for scheme in HDFC_SCHEMES:
                url = _hdfc_url(scheme, y, m)
                try:
                    # GET with Range — Cloudflare blocks HEAD on this CDN.
                    r = requests.get(
                        url, timeout=10, allow_redirects=True,
                        headers={**H, "Range": "bytes=0-1023"},
                        proxies=proxies, stream=True, verify=verify,
                    )
                    if r.status_code in (200, 206):
                        hits.append(SchemeEntry(text=scheme, url=url))
                    elif r.status_code == 403:
                        seen_403 = True
                    r.close()
                except Exception:
                    pass
            if hits:
                # _entries is what the per-scheme base.download() looks for.
                self._entries = hits
                self._constructed_entries = hits
                self._construct_year, self._construct_month = y, m
                day = calendar.monthrange(y, m)[1]
                return DiscoveryResult(year=y, month=m, as_on_date=date(y, m, day))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        # Differentiate "site is blocking us" (need proxy) from "no data yet
        # this month" — actionable error messaging.
        if seen_403:
            running_proxied = _should_proxy("files.hdfcfund.com")
            hint = (
                "" if running_proxied else
                " — files.hdfcfund.com is IP-blocked on this network. "
                "Set MF_FLOW_PROXY (and optionally MF_FLOW_PROXY_HOSTS=files.hdfcfund.com) "
                "to a residential proxy, or run from a non-blocked IP."
            )
            raise ScraperError(f"HDFC: every constructed URL returned 403 (Cloudflare block){hint}")
        raise NoDataYetError("HDFC: no URLs returned 200 — data for this month may not be posted yet")

    def latest_month_label(self, page):
        # Unreachable when discover_latest_month succeeds; stub for protocol.
        return None

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        return getattr(self, "_constructed_entries", [])
