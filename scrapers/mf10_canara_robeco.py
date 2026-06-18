"""Canara Robeco Mutual Fund — per-scheme xlsx, year+month dropdowns + Submit.

User: "Select year as latest year and month as latest month and click submit.
As the disclosures are individual schemes download as per the schemes row only".
Site has `<select id="year">` and `<select id="month">` and a Submit button.

Droplet bypass: when the page is IP-blocked (Cloudflare 403), construct
file URLs directly from hardcoded scheme codes. URL pattern observed:
    https://www.canararobeco.com/wp-content/uploads/<yyyy>/<mm_pub>/<CODE>-%E2%80%93-Canara-Robeco-<Scheme-Name-With-Dashes>-%E2%80%93-<Month>-<Year>.xlsx
"""
from __future__ import annotations

import urllib.parse
from datetime import date

import requests

from lib.fetcher import _proxy_dict_for
from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, MONTH_NAMES

from .base import DiscoveryResult, NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry


def _proxy_for_canara():
    return _proxy_dict_for("www.canararobeco.com")

log = get_logger("mf10")

MAX_BACKWARD = 6

# (scheme code, canonical name as it appears in URL) — based on observed
# Canara Robeco file URLs from May 2026.
CANARA_SCHEMES: list[tuple[str, str]] = [
    ("VF", "Canara Robeco Value Fund"),
    ("SC", "Canara Robeco Small Cap Fund"),
    ("MF", "Canara Robeco Multi Cap Fund"),
    ("MN", "Canara Robeco Manufacturing Fund"),
    ("MD", "Canara Robeco Mid Cap Fund"),
    ("LC", "Canara Robeco Large Cap Fund"),
    ("FE", "Canara Robeco Focused Fund"),
    ("EQ", "Canara Robeco Large and Mid Cap Fund"),
    ("DV", "Canara Robeco Flexi cap Fund"),                # lowercase 'c' — site casing
    ("BF", "Canara Robeco Banking and Financial Services Fund"),
]

_EM_DASH_ENC = "%E2%80%93"


def _canara_urls_for(year: int, month: int) -> list[tuple[str, str]]:
    """Generate (scheme_label, url) tuples for a given data year+month.

    Two URL variants observed: em-dash both sides, em-dash only between code
    and scheme. Both are returned per scheme so the caller can probe.
    """
    month_name = MONTH_NAMES[month - 1]
    pub_year = year if month != 12 else year + 1
    pub_month = month + 1 if month < 12 else 1
    out = []
    for code, name in CANARA_SCHEMES:
        name_dashed = name.replace(" ", "-")
        base = f"https://www.canararobeco.com/wp-content/uploads/{pub_year}/{pub_month:02d}"
        # Three observed variants (em-dash sides vary by scheme):
        variants = [
            f"{base}/{code}-{_EM_DASH_ENC}-{name_dashed}-{_EM_DASH_ENC}-{month_name}-{year}.xlsx",
            f"{base}/{code}-{name_dashed}-{_EM_DASH_ENC}-{month_name}-{year}.xlsx",  # MD pattern
            f"{base}/{code}-{_EM_DASH_ENC}-{name_dashed}-{month_name}-{year}.xlsx",
        ]
        for url in variants:
            out.append((f"{code} – {name}", url))
    return out


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.canararobeco.com/documents/statutory-disclosures/scheme-dashboard/scheme-monthly-portfolio/"

    def _try_construct_urls(self, fetcher):
        """Bypass page navigation via direct URL construction. Used when
        Cloudflare blocks the page (droplet IP). HEAD-probes each URL and
        returns the working (label, url) pairs for the latest month."""
        today = date.today()
        y, m = today.year, today.month
        for _ in range(MAX_BACKWARD):
            pairs = _canara_urls_for(y, m)
            hits: list[tuple[str, str]] = []
            seen_url: set[str] = set()
            for label, url in pairs:
                if url in seen_url:
                    continue
                try:
                    r = requests.head(
                        url, timeout=10, allow_redirects=True,
                        proxies=_proxy_for_canara(),
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
                    )
                    if r.status_code == 200:
                        hits.append((label, url))
                        seen_url.add(url)
                except Exception:
                    continue
            if hits:
                self._construct_year, self._construct_month = y, m
                return hits
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return []

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(6000)
        # If the page is bot-blocked (403, "Forbidden", etc.) raise to trigger
        # URL-construction fallback in discover_latest_month.
        title = (page.title() or "").lower()
        if "forbidden" in title or "access denied" in title or "rejected" in title:
            from .base import ScraperError
            raise ScraperError(f"Canara Robeco: page blocked (title={title!r})")

    def discover_latest_month(self, fetcher):
        # Quick HEAD check — if the disclosures page is blocked (403), skip
        # the expensive Playwright flow and go straight to URL construction.
        try:
            r = requests.head(
                self.DISCLOSURES_URL, timeout=8, allow_redirects=True,
                proxies=_proxy_for_canara(),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            page_blocked = r.status_code in (401, 403, 503)
        except Exception:
            page_blocked = False

        if not page_blocked:
            try:
                return super().discover_latest_month(fetcher)
            except Exception as page_err:
                log.info("Canara Robeco page-based discovery failed (%s); trying URL construction", type(page_err).__name__)
        else:
            log.info("Canara Robeco: page returns HTTP %s, skipping to URL construction", r.status_code)

        hits = self._try_construct_urls(fetcher)
        if not hits:
            raise NoDataYetError("Canara Robeco: page blocked AND no URL constructed")
        entries = [SchemeEntry(text=label, url=url) for label, url in hits]
        self._constructed_entries = entries
        self._entries = entries  # what the base download() looks for
        y, m = self._construct_year, self._construct_month
        import calendar
        day = calendar.monthrange(y, m)[1]
        return DiscoveryResult(year=y, month=m, as_on_date=date(y, m, day))

    def _try_submit(self, page, year: int, month: int) -> int:
        """Set year + month, click Submit, return number of xlsx links found."""
        page.evaluate(
            f"""() => {{
                const y = document.getElementById('year');
                if (y) {{ y.value = '{year}'; y.dispatchEvent(new Event('change', {{bubbles: true}})); }}
                const m = document.getElementById('month');
                if (m) {{ m.value = '{month:02d}'; m.dispatchEvent(new Event('change', {{bubbles: true}})); }}
            }}"""
        )
        page.wait_for_timeout(1500)
        try:
            page.locator('button:has-text("Submit")').first.click(timeout=8000)
        except Exception:
            return 0
        page.wait_for_timeout(4000)
        return page.evaluate(r"""
            () => [...document.querySelectorAll('a')]
                .filter(a => /\.xlsx?$/i.test(a.href||''))
                .filter(a => /Canara/i.test((a.href||'') + ' ' + (a.innerText||'')))
                .length
        """)

    def navigate_to_portfolio(self, page) -> None:
        # Iterate latest-month backward until results appear (typically April 2026
        # is latest as of this build).
        today = date.today()
        y, m = today.year, today.month
        for _ in range(MAX_BACKWARD):
            count = self._try_submit(page, y, m)
            if count:
                self._discovered_y, self._discovered_m = y, m
                return
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        raise NoDataYetError("Canara Robeco: no month yielded results")

    def latest_month_label(self, page):
        y = getattr(self, "_discovered_y", date.today().year)
        m = getattr(self, "_discovered_m", date.today().month)
        # Use end-of-month as a sensible as-on date.
        try:
            import calendar
            day = calendar.monthrange(y, m)[1]
            as_on = date(y, m, day)
        except Exception:
            as_on = date(y, m, 1)
        return (y, m, as_on)

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        # If discovery used URL construction (page was blocked), use those.
        constructed = getattr(self, "_constructed_entries", None)
        if constructed:
            return constructed
        # Page paginates with numbered buttons. Click through pages 2..10 until
        # no new xlsx links appear.
        seen_urls: set[str] = set()
        items: list[dict] = []
        for page_num in range(1, 10):
            batch = page.evaluate(r"""
                () => [...document.querySelectorAll('a')]
                    .filter(a => /\.xlsx?$/i.test(a.href||''))
                    .filter(a => /canara/i.test((a.href||'') + ' ' + (a.innerText||'')))
                    .map(a => ({text: (a.innerText||'').trim(), href: a.href}))
            """)
            new_items = [b for b in batch if b["href"] not in seen_urls]
            for b in new_items:
                seen_urls.add(b["href"])
            items.extend(new_items)
            if not new_items and page_num > 1:
                break
            # Click the next page number (if exists). Look for plain "<n+1>".
            next_n = page_num + 1
            try:
                page.locator(f'a:text-is("{next_n}")').first.click(timeout=4000)
                page.wait_for_timeout(3000)
            except Exception:
                break
        # Two anchors per scheme (descriptive label + "Download" icon).
        # Keep the LONGER text (descriptive); for fully empty/short, derive from URL.
        import urllib.parse
        by_url: dict[str, str] = {}
        for it in items:
            url = it["href"]
            txt = it["text"].strip()
            if url not in by_url or len(txt) > len(by_url[url]):
                by_url[url] = txt
        out = []
        for url, txt in by_url.items():
            if not txt or txt.lower() == "download" or len(txt) < 5:
                # Fallback: extract scheme name from URL filename.
                fname = urllib.parse.unquote(url.split("/")[-1])
                txt = fname.rsplit(".", 1)[0]
            out.append(SchemeEntry(text=txt, url=url))
        return out
