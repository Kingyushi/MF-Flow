"""Filesystem-safe filenames. Never truncates; collisions surface at runtime."""
from __future__ import annotations

import re

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_MULTI_WS = re.compile(r"\s+")


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a Windows filename component.

    Replaces reserved chars with space, collapses repeated whitespace, strips
    trailing dot/space (Windows breaks on those). Does NOT truncate.
    """
    if not name:
        raise ValueError("safe_filename: empty input")
    cleaned = _BAD.sub(" ", name)
    cleaned = _MULTI_WS.sub(" ", cleaned).strip()
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        raise ValueError(f"safe_filename: result empty for {name!r}")
    # Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    upper = cleaned.upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if upper in reserved or upper.split(".")[0] in reserved:
        cleaned = "_" + cleaned
    return cleaned


def assert_unique(names: list[str]) -> None:
    """Raise if two inputs sanitize to the same filename. Called by the runner
    before placing per-scheme files for an MF."""
    seen: dict[str, str] = {}
    for raw in names:
        safe = safe_filename(raw).lower()
        if safe in seen and seen[safe] != raw:
            raise ValueError(
                f"Filename collision: {raw!r} and {seen[safe]!r} both sanitize to {safe!r}"
            )
        seen[safe] = raw
