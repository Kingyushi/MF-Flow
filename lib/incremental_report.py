"""Per-run incremental CSV + append-only master log.

Produced after each runner pass. The per-run CSV is a snapshot of what this
run did (one row per MF). The master log is the same row appended to a single
file that grows over time, so you can `tail` it or `git diff` it to see what
changed across runs.

`change_type` values:
    FIRST_RUN  — no month was on disk; downloaded for the first time
    NEW_MONTH  — site has a newer month than on-disk; downloaded the new one
    UNCHANGED  — on-disk already had the latest available month; nothing fetched
    REFRESH    — re-downloaded the same month (force flag, or partial re-run)
    NO_DATA    — site shows no portfolio data at all
    ERROR      — scrape failed
    SKIPPED    — MF intentionally filtered out (--only / --skip)
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from scrapers.base import ScrapeOutcome, ScrapeReport

from .paths import REPORTS_DIR

MASTER_LOG = REPORTS_DIR / "master-log.csv"

COLUMNS = [
    "run_date",
    "mf_id",
    "mf_name",
    "change_type",
    "previous_month",       # "2026-04" or "" if no prior
    "current_month",        # "2026-04" or "" if no data
    "as_on_date",           # "2026-04-30" or ""
    "files_added",
    "matched_schemes",
    "total_schemes",
    "download_failures",    # comma-separated scheme names that matched but failed download
    "error",
]


def _ym_str(year: int | None, month: int | None) -> str:
    if year is None or month is None:
        return ""
    return f"{year}-{month:02d}"


def _change_type(r: ScrapeReport) -> str:
    if r.outcome == ScrapeOutcome.ERROR:
        return "ERROR"
    if r.outcome == ScrapeOutcome.NO_DATA_YET:
        return "NO_DATA"
    prev = (r.previous_year, r.previous_month) if r.previous_year else None
    curr = (r.year, r.month) if r.year else None
    if r.outcome == ScrapeOutcome.SKIPPED_ALREADY_HAVE:
        # On-disk was already the latest; runner short-circuited
        return "UNCHANGED"
    if r.outcome == ScrapeOutcome.OK_DOWNLOADED:
        if prev is None:
            return "FIRST_RUN"
        if curr is not None and curr > prev:
            return "NEW_MONTH"
        if curr == prev:
            return "REFRESH"          # --force, same month re-downloaded
        return "NEW_MONTH"             # safety fallback
    return "SKIPPED"


def build_rows(run_date: date, reports: Iterable[ScrapeReport]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for r in reports:
        rows.append({
            "run_date": run_date.isoformat(),
            "mf_id": r.mf_id,
            "mf_name": r.mf_name,
            "change_type": _change_type(r),
            "previous_month": _ym_str(r.previous_year, r.previous_month),
            "current_month": _ym_str(r.year, r.month),
            "as_on_date": r.as_on_date.isoformat() if r.as_on_date else "",
            "files_added": str(len(r.files_placed)),
            "matched_schemes": str(r.matched_schemes) if r.total_schemes else "",
            "total_schemes": str(r.total_schemes) if r.total_schemes else "",
            "download_failures": ", ".join(r.download_failures),
            "error": r.error,
        })
    return rows


def write_run_incremental(run_date: date, reports: Iterable[ScrapeReport]) -> Path:
    """Write reports/run-<date>-incremental.csv (one row per MF, this run only)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"run-{run_date.isoformat()}-incremental.csv"
    rows = build_rows(run_date, reports)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def append_master_log(run_date: date, reports: Iterable[ScrapeReport]) -> Path:
    """Append rows to reports/master-log.csv (the cumulative cross-run log)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows(run_date, reports)
    new_file = not MASTER_LOG.exists()
    with MASTER_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()
        w.writerows(rows)
    return MASTER_LOG
