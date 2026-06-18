"""Helios Mutual Fund — per-scheme xlsx with URL-encoded scheme name.

Page lists anchors whose innerText is empty (icon links). Scheme name + date
live in the URL filename: Helios-<Scheme>-Monthly-Portfolio-as-on-<DD>th-<Month>-<Year>.xls
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf17")

# Matches URLs containing "Monthly-Portfolio" and NOT "Fortnightly".
_FILENAME_RE = re.compile(
    r"(?P<scheme>.+?)[_-]Monthly[_-]Portfolio[_-]+(?:as[_-]on[_-]+)?(?P<rest>.+?)\.xlsx?$",
    re.IGNORECASE,
)


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.heliosmf.in/portfolio-disclosure/"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(8000)

    def navigate_to_portfolio(self, page) -> None:
        pass

    def latest_month_label(self, page):
        # Collect all monthly xlsx links, parse dates from URL filenames.
        urls = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .map(a => a.href||'')
                .filter(h => /\.xlsx?$/i.test(h))
                .filter(h => /Monthly[-_ ]Portfolio/i.test(h))
                .filter(h => !/Fortnightly/i.test(h))
        """)
        if not urls:
            return None
        latest = None
        for u in urls:
            d = parse_as_on(urllib.parse.unquote(u.split("/")[-1]))
            if not d:
                ym = try_infer(urllib.parse.unquote(u.split("/")[-1]))
                if ym:
                    d = date(ym[0], ym[1], 1)
            if d and (latest is None or d > latest):
                latest = d
        if not latest:
            return None
        return (latest.year, latest.month, latest)

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        urls = page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .map(a => a.href||'')
                .filter(h => /\.xlsx?$/i.test(h))
                .filter(h => /Monthly[-_ ]Portfolio/i.test(h))
                .filter(h => !/Fortnightly/i.test(h))
        """)
        # Group by scheme name (extracted from filename) and keep the LATEST.
        from datetime import date as _date
        groups: dict[str, tuple[date, str, str]] = {}
        for u in urls:
            fname = urllib.parse.unquote(u.split("/")[-1])
            d = parse_as_on(fname) or _date(2000, 1, 1)
            # Parse scheme name = everything before "Monthly Portfolio" / "MF"
            m = re.match(
                r"^(?:Helios[\s_-]+)?(?P<scheme>.+?)[\s_-]+Monthly[\s_-]Portfolio",
                fname,
                re.IGNORECASE,
            )
            if not m:
                continue
            scheme = m.group("scheme").replace("-", " ").replace("_", " ").strip()
            scheme = re.sub(r"\s+", " ", scheme)
            scheme = f"Helios {scheme}" if "helios" not in scheme.lower() else scheme
            existing = groups.get(scheme.lower())
            if not existing or d > existing[0]:
                groups[scheme.lower()] = (d, scheme, u)
        return [SchemeEntry(text=name, url=u) for d, name, u in groups.values()]
