"""The Wealth Company Mutual Fund — SPA-click, per-scheme xlsx.

Page structure (Next.js + MUI at /literature-forms/portfolio-documents/monthly/):
- Left sidebar: Application & Service Request Forms / Editable Forms /
  Scheme Documents / Portfolio Holdings / Statutory Disclosures.
- "Portfolio Holdings" is the active section.
- Sub-tabs: Fortnightly / Monthly / Half Yearly / Notice for Declaration.
- "Monthly" sub-tab shows a list of scheme entries with "Download" buttons:
    "Monthly - The Wealth Company Flexi Cap Fund - April 30, 2026"
    "Monthly - The Wealth Company Small Cap Fund - April 30, 2026"
    etc.
- Each "Download" button triggers an xlsx download.

The probe's visible_text_hits show the full list of entries with dates.
The page URL already points to /monthly/ so the monthly sub-tab should be
pre-selected. Each entry has a "Download" button next to it.

We use Playwright to click each scheme's Download button.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lib.log import get_logger
from lib.month_hint import ALL_MONTHS, parse_as_on, try_infer

from .base import NoDataYetError
from .patterns.per_scheme import PerSchemeXlsxScraper, SchemeEntry

log = get_logger("mf45")

# Pattern: "Monthly - <Scheme Name> - <Date>"
_ENTRY_RE = re.compile(
    r"^Monthly\s*[\-–]\s*(?P<scheme>.+?)\s*[\-–]\s*"
    r"(?P<month>\w+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})$",
    re.IGNORECASE,
)


def _parse_visible_entries(
    entries: list[tuple[str, str]],
) -> tuple[Optional[tuple[int, int]], list[tuple[str, str]]]:
    """Pure parse: from (text, url_or_empty) pairs, find latest month entries.

    Returns ((year, month), filtered_entries) or (None, []).
    """
    candidates = []
    for text, url in entries:
        t = text.strip()
        if not t.lower().startswith("monthly"):
            continue
        ym = try_infer(t, url)
        if ym:
            candidates.append((ym[0], ym[1], t, url))

    if not candidates:
        return None, []

    latest_ym = max((c[0], c[1]) for c in candidates)
    at_latest = [(c[2], c[3]) for c in candidates if (c[0], c[1]) == latest_ym]
    return latest_ym, at_latest


class Scraper(PerSchemeXlsxScraper):
    DISCLOSURES_URL = "https://www.wealthcompanyamc.in/literature-forms/portfolio-documents/monthly/"

    def dismiss_consent(self, page) -> None:
        page.wait_for_timeout(8000)

    def navigate_to_portfolio(self, page) -> None:
        """Ensure Monthly sub-tab is active (URL already targets /monthly/)."""
        # The URL already points to /monthly/ so the tab should be pre-selected.
        # Click it explicitly just in case.
        try:
            monthly_tab = page.locator("a:text-is('Monthly')").first
            monthly_tab.click(timeout=5_000)
            page.wait_for_timeout(3000)
        except Exception:
            log.info("TWC: 'Monthly' tab already active or click failed")

    def latest_month_label(self, page):
        """Extract latest year+month from the visible entry list."""
        entries = self._collect_entries(page)
        ym, at_latest = _parse_visible_entries(entries)
        if not ym:
            raise NoDataYetError("TWC: no monthly portfolio entries found")

        self._latest_entries = at_latest
        year, month = ym
        as_on = None
        for text, _ in at_latest:
            as_on = parse_as_on(text)
            if as_on:
                break
        return year, month, as_on

    def list_scheme_entries(self, page) -> list[SchemeEntry]:
        entries = getattr(self, "_latest_entries", None)
        if entries is None:
            all_entries = self._collect_entries(page)
            _, entries = _parse_visible_entries(all_entries)

        result = []
        for text, url in entries:
            if url:
                result.append(SchemeEntry(text=text, url=url))
            else:
                # Click-based download: find the Download button next to this text
                entry_text = text

                def make_click(t=entry_text):
                    def click_action():
                        page.evaluate(f"""
                            () => {{
                                const spans = [...document.querySelectorAll('span, div')];
                                const target = spans.find(s =>
                                    (s.textContent || '').trim() === {t!r}
                                );
                                if (!target) throw new Error('Entry not found: ' + {t!r});
                                // Find the nearest Download button
                                const parent = target.closest('div[class]') || target.parentElement;
                                const btn = parent?.querySelector('a[href], button');
                                if (!btn) throw new Error('Download button not found');
                                btn.click();
                            }}
                        """)
                    return click_action

                result.append(SchemeEntry(text=text, click=make_click()))
        return result

    def _collect_entries(self, page) -> list[tuple[str, str]]:
        """Scrape visible entries from the page DOM."""
        raw = page.evaluate("""
            () => {
                const results = [];
                // Look for scheme entry containers (spans with scheme text)
                const spans = [...document.querySelectorAll('span, div')];
                for (const span of spans) {
                    const text = (span.textContent || '').trim();
                    if (!text.startsWith('Monthly -') && !text.startsWith('Monthly –'))
                        continue;
                    // Look for a sibling/nearby download link
                    const parent = span.closest('div[class]') || span.parentElement;
                    const link = parent ? parent.querySelector('a[href]') : null;
                    const href = link ? link.href : '';
                    results.push([text, href]);
                }
                return results;
            }
        """) or []
        return [(text, href) for text, href in raw]
