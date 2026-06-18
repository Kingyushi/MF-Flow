"""Shared helper for AMCs that publish portfolio files as static <a href> links.

Many AMC disclosure pages render the entire history of monthly-portfolio xlsx
files as static anchors. To find "the latest month" we:

  1. Collect every (text, href) pair.
  2. Filter to portfolio-like extensions (.xlsx, .xls, .zip).
  3. Filter to ones whose URL or visible text contains "monthly" / "portfolio"
     (configurable include_terms).
  4. Drop ones that look like fortnightly / weekly / half-yearly disclosures
     (configurable exclude_terms).
  5. Use month_hint.try_infer + parse_as_on on EACH candidate's text+href to
     extract its (year, month). Keep only the latest (year, month).
  6. Return both the (year, month) and the filtered link list for that month.

Why this exists: 18 of the 26 new AMCs surface their files this way. Without
this helper each scraper would re-implement the same filter logic with
subtle inconsistencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from lib.log import get_logger
from lib.month_hint import parse_as_on, try_infer

log = get_logger("pattern.static_filter")


# Default term lists. AMCs vary on phrasing — override per scraper as needed.
DEFAULT_INCLUDE = ("monthly", "portfolio")
DEFAULT_EXCLUDE = (
    "fortnightly", "weekly", "half year", "half-year", "halfyearly", "half yearly",
    "quarterly", "factsheet", "fact sheet",
    "presentation", "application", "form", "reckoner",
    "commission", "distributor", "addendum", "notice",
    "scheme information", "key information", "sid", "kim", "asset allocation",
    "risk-o-meter", "riskometer", "risk o meter",
)

# Heuristic: portfolio file extensions.
_PORTFOLIO_EXT_RE = re.compile(r"\.(xlsx|xls|zip)(\?|$|#)", re.IGNORECASE)


@dataclass
class FilteredLink:
    text: str
    href: str
    year: int
    month: int


def _norm_seps(s: str) -> str:
    """Lowercase and collapse `_`/`-`/`.` runs to a single space so a term like
    'monthly portfolio' matches 'Monthly_Portfolio', 'monthly-portfolio', etc.

    AMCs are wildly inconsistent about the separator between words in both link
    text and filenames; a space-only literal match silently drops valid links
    (NJ MF flipped its May links to 'NJ_MF_Monthly_Portfolio_...' and a strict
    'monthly portfolio' filter excluded the latest two months). Normalize once
    so the term lists stay readable and separator-agnostic.
    """
    return re.sub(r"[_\-.]+", " ", s.lower())


def _all_terms_in(haystack: str, terms: Iterable[str]) -> bool:
    h = _norm_seps(haystack)
    return all(_norm_seps(t) in h for t in terms)


def _any_term_in(haystack: str, terms: Iterable[str]) -> bool:
    h = _norm_seps(haystack)
    return any(_norm_seps(t) in h for t in terms)


def filter_monthly_xlsx_links(
    links: list[tuple[str, str]],
    *,
    include_terms: tuple[str, ...] = DEFAULT_INCLUDE,
    exclude_terms: tuple[str, ...] = DEFAULT_EXCLUDE,
    include_either: bool = True,
    custom_filter: Optional[callable] = None,
) -> list[FilteredLink]:
    """Filter (text, href) pairs to portfolio links and parse their month.

    Args:
        links: list of (visible_text, href) pairs.
        include_terms: terms that MUST appear (in text+href combined).
            If include_either=True (default), ANY include term is enough.
            If include_either=False, ALL include terms must be present.
        exclude_terms: ANY of these in text+href disqualifies the link.
        custom_filter: optional callable (text, href) -> bool — pre-filter.

    Returns:
        list of FilteredLink. NOT yet narrowed to latest month — caller
        can group and pick latest. Sort by (year, month) desc to find latest.
    """
    out: list[FilteredLink] = []
    for text, href in links:
        if not href:
            continue
        if not _PORTFOLIO_EXT_RE.search(href):
            continue
        haystack = f"{text}\n{href}"
        if custom_filter and not custom_filter(text, href):
            continue
        if exclude_terms and _any_term_in(haystack, exclude_terms):
            continue
        if include_terms:
            ok = (_any_term_in(haystack, include_terms) if include_either
                  else _all_terms_in(haystack, include_terms))
            if not ok:
                continue
        ym = try_infer(text, href)
        if not ym:
            continue
        out.append(FilteredLink(text=text, href=href, year=ym[0], month=ym[1]))
    return out


def latest_month_links(links: list[FilteredLink]) -> tuple[Optional[tuple[int, int]], list[FilteredLink]]:
    """Pick the latest (year, month) across links and return only those at it."""
    if not links:
        return None, []
    latest = max((l.year, l.month) for l in links)
    return latest, [l for l in links if (l.year, l.month) == latest]


def per_scheme_latest_links(
    links: list[FilteredLink],
    scheme_key: callable,
) -> tuple[Optional[tuple[int, int]], list[FilteredLink]]:
    """For each distinct scheme (per scheme_key callable), keep ONLY its latest
    (year, month) entry. Returns ((max_year, max_month) across schemes, picks).

    Use this when an AMC publishes per-scheme portfolios on a rolling basis —
    some schemes get month N before others. `latest_month_links` would drop
    older-month schemes; this preserves them at their individual latest.

    scheme_key: callable that takes a FilteredLink and returns a hashable key
    identifying the scheme (e.g. normalized URL filename).
    """
    if not links:
        return None, []
    best_per_scheme: dict[object, FilteredLink] = {}
    for l in links:
        k = scheme_key(l)
        prev = best_per_scheme.get(k)
        if prev is None or (l.year, l.month) > (prev.year, prev.month):
            best_per_scheme[k] = l
    picks = list(best_per_scheme.values())
    max_ym = max((l.year, l.month) for l in picks)
    return max_ym, picks
