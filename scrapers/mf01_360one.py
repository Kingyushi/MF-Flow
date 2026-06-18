"""360 ONE Mutual Fund — single multi-sheet xlsx per month.

Page flow:
1. Land on /asset/mutual-funds/downloads/
2. A "Declaration for US Persons/Canada Residents" overlay may block clicks
   — nuke it via JS (more robust than waiting for the Agree button to render).
3. Click the "Disclosures" tab.
4. The default subcategory is "Monthly Portfolio". Right column shows
   year-grouped lists ("Monthly Portfolio 2026" -> April, March, ...).
5. Skip "Portfolio Overlap" rows (per user instructions); pick the latest
   plain month entry. Click it to trigger an xlsx download.

Beware: 360 ONE sits behind Cloudflare with aggressive rate limits. Avoid
re-running this scraper within a short window — Cloudflare 1015 will block
the IP for ~30 minutes if triggered.
"""
from __future__ import annotations

import re

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS

from .base import NoDataYetError, ScraperError
from .patterns.single_xlsx import SingleXlsxScraper, Target

log = get_logger("mf01")


class Scraper(SingleXlsxScraper):
    DISCLOSURES_URL = "https://www.360.one/asset/mutual-funds/downloads/"

    def dismiss_consent(self, page) -> None:
        # Wait for initial render then nuke any fixed-position overlay div.
        page.wait_for_timeout(4000)
        try:
            page.evaluate(
                "() => document.querySelectorAll('div.fixed.inset-0').forEach(el => el.remove())"
            )
        except Exception as e:
            log.info("360 ONE: overlay removal skipped: %s", e)
        page.wait_for_timeout(500)

    def navigate_to_portfolio(self, page) -> None:
        # Cloudflare check: bail loudly if rate-limited.
        title = page.title() or ""
        if "1015" in title or "rate limited" in (page.locator("body").inner_text(timeout=2000) or "").lower():
            raise ScraperError("360 ONE: Cloudflare 1015 — rate limited (try again in 30 min)")
        # Click Disclosures tab.
        page.locator('button[role="tab"]:has-text("Disclosures")').click(timeout=20_000)
        page.wait_for_selector('text=/Monthly Portfolio \\d{4}/', timeout=20_000)

    def find_target(self, page) -> Target:
        # Month labels are leaf SPAN/DIV/P nodes; don't restrict by tag.
        rows = page.evaluate(
            """() => {
                let year = null;
                const out = [];
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                while (walker.nextNode()) {
                    const el = walker.currentNode;
                    const t = (el.innerText||'').trim();
                    const ym = t.match(/^Monthly Portfolio (\\d{4})$/);
                    if (ym) { year = parseInt(ym[1], 10); continue; }
                    if (el.children.length === 0) {
                        const m = t.match(/^(January|February|March|April|May|June|July|August|September|October|November|December)( - Portfolio Overlap)?$/i);
                        if (m && year) { out.push({year, month: m[1], overlap: !!m[2]}); }
                    }
                }
                return out;
            }"""
        )
        if not rows:
            raise NoDataYetError("360 ONE: no month rows visible")
        plain = [r for r in rows if not r["overlap"]]
        if not plain:
            raise NoDataYetError("360 ONE: only Portfolio Overlap rows visible")

        def key(r):
            return (r["year"], ALL_MONTHS[r["month"].lower()])

        latest = max(plain, key=key)
        year = latest["year"]
        month_word = latest["month"]
        month = ALL_MONTHS[month_word.lower()]
        label = f"Monthly Portfolio {month_word} {year}"

        def click_action():
            page.evaluate(
                """([yr, mo]) => {
                    let year = null;
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        const t = (el.innerText||'').trim();
                        const ym = t.match(/^Monthly Portfolio (\\d{4})$/);
                        if (ym) { year = parseInt(ym[1], 10); continue; }
                        if (year === yr && el.children.length === 0 && t === mo) {
                            // Click the row container (parent) which has the download handler.
                            (el.closest('[class*="cursor"], [class*="row"], div') || el).click();
                            return;
                        }
                    }
                    throw new Error('target row not found at click time');
                }""",
                [year, month_word],
            )

        return Target(
            year=year, month=month, label=label,
            as_on=None, kind="click", payload=click_action,
        )
