"""Main runner — iterates all MFs in MF_TARGETS (45 as of 2026-06-08),
two-phase discover/download per scraper."""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from datetime import date
from pathlib import Path

# Make sibling packages importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.config import MFConfig, load_mfs                             # noqa: E402
from lib.fetcher import fetcher                                       # noqa: E402
from lib.incremental_report import (                                  # noqa: E402
    append_master_log,
    write_run_incremental,
)
from lib.log import get_logger                                        # noqa: E402
from lib.month_guard import check_discovered_month                    # noqa: E402
from lib.organizer import (                                           # noqa: E402
    FileMeta,
    find_existing_month_for_mf,
    list_existing_files,
    place_file,
    write_meta,
)
from lib.paths import INPUT_XLSX, OUTPUT_ROOT, REPORTS_DIR, ensure_runtime_dirs  # noqa: E402
from scrapers.base import (                                           # noqa: E402
    BaseScraper,
    NoDataYetError,
    ScrapeOutcome,
    ScrapeReport,
)

log = get_logger("runner")


def _load_scraper(mf: MFConfig) -> BaseScraper:
    module = importlib.import_module(mf.module)
    cls = getattr(module, "Scraper", None)
    if cls is None:
        raise RuntimeError(f"{mf.module} has no Scraper class")
    return cls(mf)


def _scrape_one(mf: MFConfig, fetch, *, force: bool, dry_run: bool) -> ScrapeReport:
    log.info("=== %s: %s [pattern=%s] ===", mf.id, mf.name, mf.pattern)
    # Snapshot the on-disk state BEFORE doing anything — the incremental report
    # uses this to compute NEW_MONTH vs UNCHANGED vs FIRST_RUN.
    pre = find_existing_month_for_mf(mf.name)
    prev_year, prev_month = (pre[0], pre[1]) if pre else (None, None)
    try:
        scraper = _load_scraper(mf)
    except Exception as e:
        log.error("Failed to import scraper for %s: %s", mf.id, e)
        return ScrapeReport(
            mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.ERROR,
            previous_year=prev_year, previous_month=prev_month,
            error=f"import failed: {e}",
        )

    try:
        latest = scraper.discover_latest_month(fetch)
    except NoDataYetError as e:
        log.info("%s: NO_DATA_YET (%s)", mf.name, e)
        return ScrapeReport(
            mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.NO_DATA_YET,
            year=prev_year, month=prev_month,
            previous_year=prev_year, previous_month=prev_month,
        )
    except Exception as e:
        log.error("%s: discovery failed: %s\n%s", mf.name, e, traceback.format_exc())
        return ScrapeReport(
            mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.ERROR,
            previous_year=prev_year, previous_month=prev_month,
            error=f"discover failed: {e}",
        )

    log.info("%s: site latest = %d-%02d (as_on=%s)", mf.name, latest.year, latest.month, latest.as_on_date)

    # Plausibility guard (see lib/month_guard.py): a monthly portfolio for the
    # current or a future month cannot exist yet. Rejecting here — BEFORE the
    # download and BEFORE anything lands in output/ — prevents a mislabeled
    # link (Abakkus daily TREPS file read as "August 2026") from poisoning the
    # on-disk month marker, which would make every later run skip the real
    # month. Applies to --force too: forcing a phantom month is still wrong.
    ok, why = check_discovered_month(latest.year, latest.month, latest.as_on_date)
    if not ok:
        log.error("%s: DISCOVERY REJECTED — %s", mf.name, why)
        return ScrapeReport(
            mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.ERROR,
            previous_year=prev_year, previous_month=prev_month,
            error=f"implausible discovery rejected: {why}",
        )

    if pre and not force:
        if (latest.year, latest.month) <= pre:
            log.info("%s: skipping, on-disk=%s >= site=%d-%02d", mf.name, pre, latest.year, latest.month)
            return ScrapeReport(
                mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.SKIPPED_ALREADY_HAVE,
                year=pre[0], month=pre[1], as_on_date=latest.as_on_date,
                previous_year=prev_year, previous_month=prev_month,
            )

    if dry_run:
        log.info("%s: dry-run, would download %d-%02d", mf.name, latest.year, latest.month)
        return ScrapeReport(
            mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.OK_DOWNLOADED,
            year=latest.year, month=latest.month, as_on_date=latest.as_on_date,
            previous_year=prev_year, previous_month=prev_month,
        )

    try:
        files = scraper.download(fetch, latest)
    except Exception as e:
        log.error("%s: download failed: %s\n%s", mf.name, e, traceback.format_exc())
        return ScrapeReport(
            mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.ERROR,
            year=latest.year, month=latest.month, as_on_date=latest.as_on_date,
            previous_year=prev_year, previous_month=prev_month,
            error=f"download failed: {e}",
        )

    # Per-scheme MFs with rolling publication can specify per-file (year, month)
    # — group by (year, month) so each cohort lands in its own month folder
    # with its own _meta.json.
    placed: list[Path] = []
    cohort: dict[tuple[int, int], list[FileMeta]] = {}
    rejected_files: list[str] = []
    for f in files:
        fy = f.year if f.year is not None else latest.year
        fm = f.month if f.month is not None else latest.month
        # Same plausibility guard for per-file (year, month) overrides used by
        # rolling per-scheme MFs — one bad per-file date must not create a
        # phantom month folder either.
        ok, why = check_discovered_month(fy, fm)
        if not ok:
            log.error("%s: file %r rejected — %s", mf.name, f.label, why)
            rejected_files.append(f.label)
            continue
        try:
            p = place_file(
                f.src_path, mf.name, fy, fm,
                label=f.label, overwrite=force,
            )
            placed.append(p)
            cohort.setdefault((fy, fm), []).append(FileMeta(
                filename=p.name,
                scheme_name=f.scheme_name,
                source_url=f.source_url,
            ))
        except Exception as e:
            log.error("%s: place_file failed for %s: %s", mf.name, f.label, e)

    # Write a _meta.json per cohort folder. The MF-level discovery month gets
    # the canonical _meta (with as_on_date); secondary cohorts (older months
    # bumped from previous run) get a meta without as_on_date.
    for (cy, cm), metas in cohort.items():
        as_on_iso = (latest.as_on_date.isoformat()
                     if latest.as_on_date and (cy, cm) == (latest.year, latest.month)
                     else None)
        write_meta(
            mf.name, cy, cm,
            pattern=mf.pattern,
            as_on_date=as_on_iso,
            files=metas,
        )

    report = ScrapeReport(
        mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.OK_DOWNLOADED,
        year=latest.year, month=latest.month, as_on_date=latest.as_on_date,
        files_placed=placed,
        previous_year=prev_year, previous_month=prev_month,
    )
    # Capture per-scheme audit if a PerSchemeXlsxScraper attached a match_report.
    mr = getattr(scraper, "_match_report", None)
    if mr is not None:
        report.matched_schemes = mr.matched_count
        report.total_schemes = mr.total_schemes
        report.unmatched_schemes = list(mr.unmatched_schemes)
    # Capture per-scheme download failures (matched a link but file didn't land)
    df = getattr(scraper, "_download_failures", None)
    if df:
        report.download_failures = list(df)
    # Files rejected by the month plausibility guard surface as PARTIAL so the
    # run summary is loud about them.
    if rejected_files:
        report.download_failures = list(report.download_failures) + [
            f"{lbl} (implausible month rejected)" for lbl in rejected_files
        ]
    return report


def _write_run_report(reports: list[ScrapeReport]) -> Path:
    import openpyxl
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MF Flow Run"
    headers = [
        "MF ID", "MF Name", "Outcome", "Year", "Month", "As-On Date",
        "Files Placed", "Matched Schemes", "Total Schemes", "Unmatched",
        "Download Failures", "Error",
    ]
    ws.append(headers)
    for r in reports:
        ws.append([
            r.mf_id, r.mf_name, r.outcome.value,
            r.year, r.month,
            r.as_on_date.isoformat() if r.as_on_date else "",
            len(r.files_placed),
            r.matched_schemes or "",
            r.total_schemes or "",
            ", ".join(r.unmatched_schemes) if r.unmatched_schemes else "",
            ", ".join(r.download_failures) if r.download_failures else "",
            r.error,
        ])
    path = REPORTS_DIR / f"run-{date.today().isoformat()}.xlsx"
    wb.save(path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="MF Flow scraper")
    ap.add_argument("--only", help="Run only this MF id (e.g. mf16)", default=None)
    ap.add_argument("--only-name", help="Filter by name substring", default=None)
    ap.add_argument("--skip", help="Comma-separated MF ids to skip", default="")
    ap.add_argument("--headed", action="store_true", help="Visible browser (debugging)")
    ap.add_argument("--force", action="store_true", help="Redownload even if on disk")
    ap.add_argument("--dry-run", action="store_true", help="Discover only, no downloads")
    args = ap.parse_args()

    ensure_runtime_dirs()
    log.info("=== MF Flow run start ===")
    log.info("INPUT_XLSX = %s", INPUT_XLSX)
    log.info("OUTPUT_ROOT = %s", OUTPUT_ROOT)

    mfs = load_mfs()
    skip_ids = {s.strip() for s in args.skip.split(",") if s.strip()}
    if args.only:
        mfs = [m for m in mfs if m.id == args.only]
    if args.only_name:
        s = args.only_name.lower()
        mfs = [m for m in mfs if s in m.name.lower()]
    if skip_ids:
        mfs = [m for m in mfs if m.id not in skip_ids]

    if not mfs:
        log.error("No MFs selected (filters too tight).")
        return 2

    reports: list[ScrapeReport] = []
    with fetcher(headed=args.headed) as fetch:
        for mf in mfs:
            try:
                report = _scrape_one(mf, fetch, force=args.force, dry_run=args.dry_run)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.error("%s: unhandled in runner: %s\n%s", mf.name, e, traceback.format_exc())
                pre = find_existing_month_for_mf(mf.name)
                py, pm = (pre[0], pre[1]) if pre else (None, None)
                report = ScrapeReport(
                    mf_id=mf.id, mf_name=mf.name, outcome=ScrapeOutcome.ERROR,
                    previous_year=py, previous_month=pm,
                    error=f"runner exc: {e}",
                )
            reports.append(report)
            log.info("STATUS: %s", report.status_line())

    # Summary
    ok = sum(1 for r in reports if r.outcome == ScrapeOutcome.OK_DOWNLOADED)
    skipped = sum(1 for r in reports if r.outcome == ScrapeOutcome.SKIPPED_ALREADY_HAVE)
    no_data = sum(1 for r in reports if r.outcome == ScrapeOutcome.NO_DATA_YET)
    errored = sum(1 for r in reports if r.outcome == ScrapeOutcome.ERROR)
    partial = sum(1 for r in reports if r.download_failures)

    print()
    print("=" * 78)
    print(f"MF Flow run finished: {len(reports)} MFs — "
          f"OK={ok}  skipped={skipped}  no_data_yet={no_data}  error={errored}"
          + (f"  PARTIAL={partial}" if partial else ""))
    print("=" * 78)
    for r in reports:
        print("  " + r.status_line())
    if partial:
        print()
        print("PARTIAL downloads (matched a link but file download failed):")
        for r in reports:
            if r.download_failures:
                print(f"  {r.mf_id} {r.mf_name}: {r.download_failures}")
    print()

    try:
        report_path = _write_run_report(reports)
        log.info("Wrote run report: %s", report_path)
    except Exception as e:
        log.error("Failed to write run report: %s", e)

    # Incremental CSV (per-run snapshot) + append to cumulative master log.
    try:
        today = date.today()
        inc_path = write_run_incremental(today, reports)
        master_path = append_master_log(today, reports)
        # One-line tally of what changed this run.
        changed = sum(1 for r in reports if r.outcome == ScrapeOutcome.OK_DOWNLOADED)
        unchanged = sum(1 for r in reports if r.outcome == ScrapeOutcome.SKIPPED_ALREADY_HAVE)
        log.info(
            "Incremental: %s -> %d new/refreshed, %d unchanged, %d no_data, %d error. "
            "Master log: %s",
            inc_path, changed, unchanged, no_data, errored, master_path,
        )
    except Exception as e:
        log.error("Failed to write incremental report: %s", e)

    return 0 if errored == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
