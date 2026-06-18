"""DSP Mutual Fund — monthly zip of per-scheme files.

Page lists multiple sections; the relevant one is "Month End Portfolio
Disclosures". Each row has anchor text like:
    "Portfolio Details as on April 30, 2026"
URL like:
    https://www.dspim.com/.../<random-hex-id>-<timestamp>/monthend-portfolios_30-april-2026.zip

**Droplet caveat:** the random ID + timestamp in the URL makes it impossible
to construct directly. dspim.com is Cloudflare-protected and IP-blocks the
DigitalOcean ASN at every endpoint (page, API, file CDN, even /robots.txt).
The only way to run DSP from the droplet is to set MF_FLOW_PROXY to a
residential proxy. On Windows the page works direct.
"""
from __future__ import annotations

import os
import re
from datetime import date

from lib.fetcher import _should_proxy
from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError, ScraperError
from .patterns.zip_pattern import LatestMonthZipScraper

log = get_logger("mf12")


class Scraper(LatestMonthZipScraper):
    DISCLOSURES_URL = "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)
        # Detect Cloudflare 403 / IP-block → emit a clear actionable error
        # so the user knows to set MF_FLOW_PROXY.
        title = (page.title() or "")
        if "Just a moment" in title or "Access denied" in title.lower() or "403" in title:
            running_proxied = _should_proxy("www.dspim.com")
            hint = (
                "" if running_proxied else
                " — set MF_FLOW_PROXY (and optionally MF_FLOW_PROXY_HOSTS=dspim.com) "
                "to a residential proxy, or run from Windows where direct access works."
            )
            raise ScraperError(f"DSP: site rejected request (title={title!r}){hint}")
        try:
            page.evaluate(
                "() => document.querySelectorAll('.cookie-banner, .cookie-consent, [class*=\"modal\"]').forEach(el => { try { el.remove(); } catch(e){} })"
            )
        except Exception:
            pass

    def find_latest_link(self, page):
        items = page.evaluate("""
            () => [...document.querySelectorAll('a')]
                .filter(a => {
                    const h = (a.href||'').toLowerCase();
                    return h.endsWith('.zip') && h.includes('monthend-portfolio');
                })
                .map(a => ({text: a.innerText.trim(), href: a.href}))
        """)
        if not items:
            raise NoDataYetError("DSP: no month-end portfolio zips found")
        best = None
        best_date = None
        for it in items:
            d = parse_as_on(it["text"], it["href"])
            if not d:
                ym = try_infer(it["text"], it["href"])
                if ym:
                    d = date(ym[0], ym[1], 1)
            if d and (best_date is None or d > best_date):
                best_date = d
                best = it
        if not best:
            raise NoDataYetError("DSP: could not parse dates from any zip link")
        return (best["href"], best["text"], best_date)
