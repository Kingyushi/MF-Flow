"""Audit output/ for phantom month folders (and optionally delete them).

Context (2026-08): mf02 Abakkus downloaded a daily TREPS/debt file and
recorded it as the phantom month "August 2026". Because the incremental skip
keys on the newest on-disk month folder, a phantom month makes every later
run silently skip the REAL data for that month. This tool finds such folders
so they can be removed BEFORE the next run.

Detection (from each month folder's _meta.json):
  PHANTOM  — downloaded_at is on/before the last day of the folder's month.
             A real monthly portfolio for month M can only be downloaded
             after M ends, so this is conclusive.
  SUSPECT  — as_on_date falls mid-month (day 2..24). Monthly portfolios are
             as-on month-end; a mid-month as_on usually means a fortnightly/
             daily file slipped through. Day 1 is NOT flagged (several
             patterns store day 1 as a month-only placeholder) and day >= 25
             is NOT flagged (last-business-day AMCs, e.g. Franklin's
             as-on 2026-05-29). Review SUSPECT rows by eye.
  (folders without _meta.json are listed as NO_META for eyeballing)

A PHANTOM folder is not always garbage: Capital Mind's "November 2026"
phantom actually held the genuine JUNE 2026 portfolio (the upload-hash
"..._June_2026_11dcac4356.xlsx" misparsed as 2026-11). The tool infers the
TRUE month from each phantom's source_url and reports it, so real data can
be salvaged by renaming instead of lost by deleting.

Usage:
    python tools/audit_month_folders.py            # report only
    python tools/audit_month_folders.py --fix      # rename salvageable
                                                   # phantoms to their true
                                                   # month folder
    python tools/audit_month_folders.py --delete   # delete phantoms that
                                                   # remain (unsalvageable,
                                                   # e.g. Abakkus daily TREPS)
                                                   # (never touches SUSPECT)

Recommended order on a poisoned machine: --fix first, review, then --delete.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.month_guard import is_completed_month, last_day_of_month  # noqa: E402
from lib.organizer import _MONTH_FOLDER_RE                         # noqa: E402
from lib.month_hint import ALL_MONTHS, format_month, try_infer     # noqa: E402
from lib.paths import OUTPUT_ROOT                                  # noqa: E402


def _true_month_from_meta(meta: dict, dl_date) -> "tuple[int, int] | None":
    """Infer the TRUE (year, month) of a phantom folder from its source URLs.
    Deliberately NOT the local filenames — those carry the wrong month label
    the phantom was created with. Only trust the answer if it is a plausible
    completed month as of the download date (otherwise the same misparse that
    created the phantom could steer the rename)."""
    hints: list[str] = [
        f.get("source_url") or "" for f in meta.get("files") or []
    ]
    ym = try_infer(*hints)
    if not ym:
        return None
    if dl_date is not None and not is_completed_month(ym[0], ym[1], dl_date):
        return None
    return ym


def audit(delete: bool = False, fix: bool = False) -> int:
    phantoms: list[tuple[Path, str]] = []
    suspects: list[tuple[Path, str]] = []
    no_meta: list[Path] = []

    for mf_dir in sorted(OUTPUT_ROOT.iterdir() if OUTPUT_ROOT.exists() else []):
        if not mf_dir.is_dir():
            continue
        for month_dir in sorted(mf_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            m = _MONTH_FOLDER_RE.match(month_dir.name)
            if not m:
                continue
            year = int(m.group("year"))
            month = ALL_MONTHS[m.group("month").lower()]
            month_end = date(year, month, last_day_of_month(year, month))

            meta_path = month_dir / "_meta.json"
            if not meta_path.exists():
                no_meta.append(month_dir)
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception as e:
                suspects.append((month_dir, f"unreadable _meta.json ({e})"))
                continue

            dl_raw = meta.get("downloaded_at_utc") or ""
            try:
                dl_date = datetime.fromisoformat(dl_raw).date()
            except ValueError:
                dl_date = None
            if dl_date is not None and dl_date <= month_end:
                true_ym = _true_month_from_meta(meta, dl_date)
                phantoms.append({
                    "dir": month_dir,
                    "why": (
                        f"downloaded {dl_date.isoformat()} but folder month only "
                        f"ends {month_end.isoformat()} — file cannot be the real "
                        "monthly portfolio"
                    ),
                    "true_ym": true_ym,
                    "meta": meta,
                    "meta_path": meta_path,
                })
                continue

            as_on_raw = meta.get("as_on_date")
            if as_on_raw:
                try:
                    as_on = date.fromisoformat(as_on_raw)
                except ValueError:
                    as_on = None
                # Day 1 = month-only placeholder used by several patterns;
                # day >= 25 = plausible last-business-day as-on. Only a
                # genuinely mid-month as_on is suspicious.
                if as_on is not None and 2 <= as_on.day <= 24:
                    suspects.append((month_dir, (
                        f"as_on_date {as_on.isoformat()} is mid-month, not a "
                        "month-end — verify this is really a monthly portfolio"
                    )))

    print(f"Scanned {OUTPUT_ROOT}")
    print(f"  PHANTOM folders : {len(phantoms)}")
    for ph in phantoms:
        print(f"    {ph['dir']}\n      -> {ph['why']}")
        srcs = [f.get("source_url") or "?" for f in ph["meta"].get("files") or []]
        for s in srcs[:3]:
            print(f"      source: {s}")
        if ph["true_ym"]:
            print(f"      true month appears to be {format_month(*ph['true_ym'])} "
                  "— salvageable with --fix (renames the folder)")
        else:
            print("      true month not inferable — junk file, remove with --delete")
    print(f"  SUSPECT folders : {len(suspects)}")
    for p, why in suspects:
        print(f"    {p}\n      -> {why}")
    if no_meta:
        print(f"  NO_META folders : {len(no_meta)} (pre-dating meta tracking; review manually)")
        for p in no_meta:
            print(f"    {p}")

    if fix:
        for ph in phantoms[:]:
            ym = ph["true_ym"]
            if not ym:
                continue
            src_dir: Path = ph["dir"]
            old_label = src_dir.name
            new_label = format_month(*ym)
            dst_dir = src_dir.parent / new_label
            if dst_dir.exists():
                print(f"  CANNOT FIX {src_dir} — {new_label} already exists; "
                      "resolve manually")
                continue
            src_dir.rename(dst_dir)
            # Rename files carrying the wrong month label + rewrite _meta.json.
            meta = ph["meta"]
            new_files = []
            for f in meta.get("files") or []:
                fn = f.get("filename") or ""
                new_fn = fn.replace(old_label, new_label)
                if new_fn != fn and (dst_dir / fn).exists():
                    (dst_dir / fn).rename(dst_dir / new_fn)
                f["filename"] = new_fn
                new_files.append(f)
            meta["month"] = new_label
            meta["year"], meta["month_num"] = ym
            meta["as_on_date"] = None   # original as_on was the misparse; unknown now
            meta["files"] = new_files
            (dst_dir / "_meta.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  FIXED {src_dir} -> {dst_dir}")
            phantoms.remove(ph)
        remaining = [ph for ph in phantoms if not ph["true_ym"]]
        if remaining:
            print(f"  {len(remaining)} unsalvageable phantom(s) remain — "
                  "remove with --delete")

    if delete:
        for ph in phantoms:
            print(f"  DELETING {ph['dir']}")
            shutil.rmtree(ph["dir"])
        print(f"Deleted {len(phantoms)} phantom folder(s). SUSPECT folders were NOT touched.")
    elif phantoms and not fix:
        print("\nRun with --fix to rename salvageable phantoms to their true "
              "month, then --delete for the rest (do this BEFORE the next "
              "scraper run).")
    return 1 if phantoms else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true",
                    help="rename salvageable PHANTOM folders to their true month")
    ap.add_argument("--delete", action="store_true",
                    help="delete remaining PHANTOM folders (SUSPECT never touched)")
    args = ap.parse_args()
    sys.exit(audit(delete=args.delete, fix=args.fix))
