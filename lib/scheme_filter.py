"""Normalize MF scheme names and match against site link text.

Why this exists:
- User's xlsx has scheme names like "HDFC Flexi cap fund", "Canara Robeco
  Value Fund " (trailing space), "MF – Canara Robeco Multi Cap Fund " (em-dash
  prefix).
- AMC sites render variants like "HDFC FLEXI CAP FUND - Direct Plan (G)",
  "Canara Robeco Value Fund - Direct Plan - Growth Option".
- A naive substring match has the HDFC large-vs-large+mid trap:
  "HDFC Large Cap Fund" tokens are a subset of "HDFC Large and Mid cap fund"
  tokens — that link would incorrectly match the Large Cap scheme.

The match rule:
1. Normalize both sides: lowercase, drop punctuation, collapse whitespace,
   drop plan-type suffixes ("direct plan", "regular plan", "growth", "(g)",
   "idcw", "dividend reinvestment", etc.).
2. Tokenize.
3. Match if scheme_tokens is a CONTIGUOUS subsequence of link_tokens
   (preserves order; "large cap" won't match a link with "large and mid cap").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Tokens / phrases that AMC sites append to scheme names but the user's xlsx
# omits. These are stripped from BOTH sides before tokenizing.
_PLAN_SUFFIX_PHRASES = [
    "direct plan",
    "regular plan",
    "growth option",
    "idcw option",
    "dividend reinvestment option",
    "dividend payout option",
    "dividend reinvestment",
    "dividend payout",
    "monthly dividend",
    "quarterly dividend",
    "growth",
    "dividend",
    "idcw",
    "(g)",
    "(d)",
    "(idcw)",
]

# Single tokens we always drop (noise words).
_DROP_TOKENS = {
    "an", "the", "of", "and", "&", "fund", "scheme", "plan", "option",
}

# "(Formerly known as ...)" is a parenthetical alias seen on many xlsx entries.
_FORMERLY_RE = re.compile(r"\(\s*formerly\s+known\s+as[^)]*\)", re.IGNORECASE)
# Hyphens / em-dashes used as bullets at the start ("MF – Canara Robeco ...")
_LEADING_TAG_RE = re.compile(r"^[a-z]{1,4}\s*[\-–—]\s*", re.IGNORECASE)


_COMPOUND_PAIRS = [
    # Longest first — compound pairs that should collapse to single tokens.
    ("large and mid cap", "largemidcap"),
    ("large & mid cap", "largemidcap"),
    ("large mid cap", "largemidcap"),
    ("mid and small cap", "midsmallcap"),
    ("mid & small cap", "midsmallcap"),
    ("mid small cap", "midsmallcap"),
    ("mid cap", "midcap"),
    ("large cap", "largecap"),
    ("small cap", "smallcap"),
    ("flexi cap", "flexicap"),
    ("multi cap", "multicap"),
    ("multi-cap", "multicap"),
    ("micro cap", "microcap"),
    ("mega cap", "megacap"),
    # AMC-name prefixes that get split/joined inconsistently across user xlsx
    # and AMC site labels. Collapsing to the joined form on both sides means
    # "LIC MF X" and "LICMF X" match identically.
    ("lic mf", "licmf"),
]


def normalize(name: str) -> str:
    """Lowercase, strip parentheticals, strip plan suffixes, normalize punctuation.

    Also collapses common compound tokens so that "Mid Cap" and "Midcap" match.
    """
    if not name:
        return ""
    s = name
    # Drop "(formerly known as ...)" parentheticals.
    s = _FORMERLY_RE.sub("", s)
    # Drop "MF – ", "SC – " style leading tags.
    s = _LEADING_TAG_RE.sub("", s)
    # Replace em/en-dashes and other punctuation with spaces. Also treat
    # underscore as a separator — AMC sheet names occasionally include rogue
    # underscores (e.g. SAMCO's `Samco_ Small_Cap_ Fund`) that would otherwise
    # collapse adjacent words into single garbage tokens.
    s = re.sub(r"[–—‘’“”_]", " ", s)
    s = re.sub(r"[^\w\s()]", " ", s)
    # Lowercase, collapse whitespace.
    s = re.sub(r"\s+", " ", s).strip().lower()
    # Strip plan-type suffix phrases.
    changed = True
    while changed:
        changed = False
        for phrase in _PLAN_SUFFIX_PHRASES:
            if s.endswith(" " + phrase) or s == phrase:
                s = s[: len(s) - len(phrase)].strip()
                changed = True
            s_clean = re.sub(rf"\b{re.escape(phrase)}\b", "", s)
            if s_clean != s:
                s = re.sub(r"\s+", " ", s_clean).strip()
                changed = True
    # Collapse common compound tokens — applied AFTER suffix stripping so
    # "Direct Plan" is gone before we look at "Large Cap".
    for spaced, joined in _COMPOUND_PAIRS:
        s = re.sub(rf"\b{re.escape(spaced)}\b", joined, s)
    return s


def _tokens(s: str) -> list[str]:
    out = [t for t in re.findall(r"[a-z0-9]+", s) if t not in _DROP_TOKENS]
    return out


@dataclass
class SchemeMatch:
    scheme_name: str       # original scheme name from xlsx
    link_text: str         # site-side text that matched
    link_url: str          # site-side URL


@dataclass
class MatchReport:
    matched: list[SchemeMatch]
    unmatched_schemes: list[str]
    total_schemes: int

    @property
    def matched_count(self) -> int:
        return len(self.matched)

    def summary(self, mf_id: str = "", mf_name: str = "") -> str:
        prefix = f"[{mf_id}/{mf_name}] " if mf_id or mf_name else ""
        s = f"{prefix}matched {self.matched_count}/{self.total_schemes} schemes"
        if self.unmatched_schemes:
            s += f" (unmatched: {', '.join(repr(x) for x in self.unmatched_schemes)})"
        return s


def _is_contiguous_subseq(small: list[str], big: list[str]) -> bool:
    if not small or len(small) > len(big):
        return False
    n = len(small)
    for i in range(0, len(big) - n + 1):
        if big[i : i + n] == small:
            return True
    return False


def match_schemes(
    scheme_names: Iterable[str],
    site_links: list[tuple[str, str]],
) -> MatchReport:
    """site_links is [(visible_text, url), ...].

    For each scheme, find the FIRST link whose normalized tokens contain the
    scheme's normalized tokens as a contiguous subsequence. Each link is
    consumed at most once across schemes (so HDFC Large Cap won't steal the
    HDFC Large and Mid Cap link).
    """
    scheme_list = [s for s in scheme_names if s and s.strip()]
    norm_schemes = [(s, _tokens(normalize(s))) for s in scheme_list]
    norm_links = [(text, url, _tokens(normalize(text))) for text, url in site_links]
    used = set()
    matched: list[SchemeMatch] = []
    unmatched: list[str] = []

    # Sort schemes by descending token count — longer/more-specific schemes get
    # first dibs so they don't lose their link to a shorter scheme that also
    # matches a more-specific link.
    indexed = sorted(enumerate(norm_schemes), key=lambda x: -len(x[1][1]))
    for orig_idx, (scheme, sch_tokens) in indexed:
        if not sch_tokens:
            unmatched.append(scheme)
            continue
        hit = None
        for li, (text, url, link_tokens) in enumerate(norm_links):
            if li in used:
                continue
            if _is_contiguous_subseq(sch_tokens, link_tokens):
                hit = (li, text, url)
                break
        if hit is None:
            unmatched.append(scheme)
        else:
            li, text, url = hit
            used.add(li)
            matched.append(SchemeMatch(scheme_name=scheme, link_text=text, link_url=url))

    # Preserve original spreadsheet order in the report.
    matched.sort(key=lambda m: scheme_list.index(m.scheme_name))
    unmatched.sort(key=lambda x: scheme_list.index(x))
    return MatchReport(
        matched=matched,
        unmatched_schemes=unmatched,
        total_schemes=len(scheme_list),
    )
