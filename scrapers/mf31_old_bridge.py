"""Old Bridge Mutual Fund — per-scheme xlsx from the "Monthly Portfolio" tab.

=== 2026-07 MAINTENANCE FIX (filename-scheme change) ===
Old Bridge stopped putting the month/scheme in the file NAME. From June 2026
the monthly files are uploaded with opaque codes and no "portfolio" token, e.g.

    /uploads/OBFE_9d7d1d029f.xlsx   (Focused Fund - June 2026)
    /uploads/OBFX_c2050b88e7.xlsx   (Flexi Cap Fund - June 2026)
    /uploads/OBAF_199025492f.xlsx   (Arbitrage Fund - June 2026)

The OLD scraper inferred (year, month) from the file NAME and required the
word "portfolio" in the href, so it went blind to June and kept reporting the
last month whose file still had a descriptive name (May 2026).

FIX: read the month + scheme from the VISIBLE ROW LABEL instead of the filename.
Every download link carries a reliable, consistently-formatted attribute:

    <li>
      <h2>Old Bridge Focused Fund - June 2026</h2>
      <a href="/uploads/OBFE_....xlsx"
         aria-label="Download Old Bridge Focused Fund - June 2026 (opens in new tab)">
         Download</a>
    </li>

We scope to the "Monthly Portfolio" tab pane, take each xlsx anchor's
aria-label (fallback: its <li> text), and infer month + scheme from that.
The chaotic filenames no longer matter.
"""
from __future__ import annotations

import re
from datetime import date

from lib.log import get_logger
from lib.month_hint import parse_as_on

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry
from .patterns.static_links_filter import (
    filter_monthly_xlsx_links,
    latest_month_links,
)

log = get_logger("mf31")

# All month/scheme info now comes from the row LABEL (aria-label), not the href.
# Exclude any stray non-monthly items should the tab-pane scoping ever widen.
_EXCLUDE_TERMS = (
    "half_yearly", "half yearly", "half-year", "halfyearly", "half year",
    "fortnightly", "weekly",
    "financials", "factsheet", "fact sheet",
    "addendum", "notice", "complaints", "proxy",
    "compensation", "geography", "associates",
    "performance", "avg_asset", "avg asset", "dashboard",
    "assets under management", "aum",
)


def _custom_filter(text: str, href: str) -> bool:
    """Keep only real scheme rows. Their label is always
    'Download Old Bridge <Scheme> Fund - <Month> <Year> ...' — i.e. contains
    'fund'. Half-yearly financials / AUM / dashboards do not, so this drops
    them even if the tab scoping ever over-captures."""
    return "fund" in (text or "").lower()


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://oldbridgemf.com/statutory-disclosures.html"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(3000)

    def _parse_links(self, links: list[tuple[str, str]]):
        """Pure parse step — extracted so tests can feed fixture data.

        `links` is [(label, href), ...] where `label` is the anchor's
        aria-label (e.g. 'Download Old Bridge Focused Fund - June 2026 ...').
        Month is inferred from the LABEL via try_infer inside
        filter_monthly_xlsx_links; the href is no longer relied on for dates.
        """
        filtered = filter_monthly_xlsx_links(
            links,
            include_terms=(),          # tab-scoped already; month inference gates
            exclude_terms=_EXCLUDE_TERMS,
            include_either=True,
            custom_filter=_custom_filter,
        )
        latest, at_latest = latest_month_links(filtered)
        if not latest:
            raise NoDataYetError("Old Bridge: no monthly portfolio links found")
        return latest, at_latest

    def latest_month_label(self, page):
        # Scope to the "Monthly Portfolio" tab pane, then return
        # [aria-label-or-<li>-text, href] for each xlsx anchor inside it.
        pairs = page.evaluate(r"""
            () => {
                // Locate the "Monthly Portfolio" tab (NOT "Half Yearly ...").
                let root = null;
                const tabs = Array.from(
                    document.querySelectorAll('[data-bs-target], [data-bs-toggle], a[href^="#"]'));
                for (const t of tabs) {
                    const label = (t.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    if (label === 'monthly portfolio') {
                        const sel = t.getAttribute('data-bs-target') || t.getAttribute('href');
                        if (sel && sel.charAt(0) === '#') {
                            const el = document.querySelector(sel);
                            if (el) { root = el; break; }
                        }
                    }
                }
                if (!root) root = document;   // fallback: _custom_filter still guards
                return Array.from(root.querySelectorAll('a[href]'))
                    .filter(a => /\.(xlsx|xls)(\?|#|$)/i.test(a.href))
                    .map(a => {
                        const aria = a.getAttribute('aria-label') || '';
                        const li = a.closest('li');
                        const label = (aria || (li ? li.innerText : (a.innerText || ''))) || '';
                        return [label.replace(/\s+/g, ' ').trim(), a.href];
                    });
            }
        """) or []
        latest, at_latest = self._parse_links([(t, h) for t, h in pairs])
        self._latest_links = at_latest
        year, month = latest
        as_on = None
        for fl in at_latest:
            as_on = parse_as_on(fl.text, fl.href)
            if as_on:
                break
        if not as_on:
            as_on = date(year, month, 1)
        return year, month, as_on

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        # Scheme name lives in the label:
        #   'Download Old Bridge Focused Fund - June 2026 (opens in new tab)'
        # Strip the 'Download ' prefix and the ' - <Month> <Year> ...' suffix.
        entries: list[SchemeEntry] = []
        for fl in self._latest_links:
            label = fl.text or ""
            m = re.match(
                r"\s*download\s+(.*?)\s*-\s*[A-Za-z]+\s+\d{4}",
                label, re.IGNORECASE,
            )
            scheme = m.group(1).strip() if m else label
            entries.append(SchemeEntry(text=scheme, url=fl.href))
        return entries
