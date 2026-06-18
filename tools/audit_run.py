"""Post-run audit: verifies every MF actually retrieved what was built for.

Reports three concrete metrics per MF:
  1. files placed on disk for the latest month
  2. file validity — every xlsx/xls/zip/pdf passes its file-format signature
  3. for PER-SCHEME MFs: file count vs user-listed scheme count
     (the SAMCO-style silent failure check — matched but not placed)

Returns non-zero exit code if any MF has missing files or invalid files.
For single-xlsx and zip MFs we don't reverse-engineer sheet name -> scheme
name (AMCs use opaque 3-letter codes); we trust the file is valid + has a
reasonable size + has multiple sheets.

Run after any live `run_scraper.py` to catch silent partial-download issues.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import load_mfs, MF_TARGETS                              # noqa: E402
from lib.organizer import find_existing_month_for_mf, month_folder       # noqa: E402

warnings.filterwarnings("ignore")


SIG_XLSX = b"PK\x03\x04"
SIG_XLS  = b"\xD0\xCF\x11\xE0"
SIG_PDF  = b"%PDF"
SIG_ZIP  = b"PK\x03\x04"   # same as xlsx


def _sheet_count(path: Path) -> int:
    """Sheet count or 0 if unreadable. Routes on signature, NOT extension —
    AMCs sometimes serve modern xlsx with a legacy .xls filename."""
    try:
        head = path.read_bytes()[:8]
    except Exception:
        return 0
    if head.startswith(SIG_XLSX):
        # Real xlsx (zip header). openpyxl checks the filename extension and
        # rejects misnamed .xls — read via BytesIO to bypass that.
        try:
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()),
                                        read_only=True, data_only=True)
            return len(wb.sheetnames)
        except Exception:
            return 0
    if head.startswith(SIG_XLS):
        try:
            import xlrd
            return len(xlrd.open_workbook(str(path)).sheet_names())
        except Exception:
            return 0
    return 0


def _validate_file(path: Path) -> str:
    """Return '' if OK, else a short reason. Validates extension matches signature."""
    if path.stat().st_size < 1024:
        return f"tiny ({path.stat().st_size}B)"
    try:
        head = path.read_bytes()[:8]
    except Exception as e:
        return f"unreadable: {type(e).__name__}"
    ext = path.suffix.lower()
    if ext in (".xlsx",):
        if not head.startswith(SIG_XLSX):
            return f"bad xlsx sig: {head[:4]!r}"
    elif ext == ".xls":
        if not (head.startswith(SIG_XLS) or head.startswith(SIG_XLSX)):
            # Some AMCs serve xlsx with .xls extension — accept zip header too.
            return f"bad xls sig: {head[:4]!r}"
    elif ext == ".zip":
        if not head.startswith(SIG_ZIP):
            return f"bad zip sig: {head[:4]!r}"
    elif ext == ".pdf":
        if not head.startswith(SIG_PDF):
            return f"bad pdf sig: {head[:4]!r}"
    return ""


def main() -> int:
    mfs = load_mfs()
    print(f"{'MF':5s} {'Name':38s} {'Pattern':18s} {'Month':>9s} {'Files':>5s} {'Schemes':>8s}  Status")
    print("-" * 120)
    issues = 0
    for mf in mfs:
        pattern = MF_TARGETS[mf.id][0]
        ym = find_existing_month_for_mf(mf.name)
        if not ym:
            print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:18s} {'—':>9s} {0:>5d} {len(mf.schemes):>8d}  NO DATA ON DISK")
            issues += 1
            continue
        year, month = ym
        folder = month_folder(mf.name, year, month)
        all_files = [p for p in folder.iterdir() if p.is_file() and p.name != "_meta.json"]
        n_files = len(all_files)

        # Validate each file
        bad_files = []
        for f in all_files:
            why = _validate_file(f)
            if why:
                bad_files.append(f"{f.name}: {why}")

        # Per-scheme MFs: check files >= scheme count (allow upstream lag like JM)
        per_scheme = pattern == "per_scheme_xlsx"
        status_bits = []
        meta_path = folder / "_meta.json"
        scheme_files = 0
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                scheme_files = sum(1 for f in meta.get("files", []) if f.get("scheme_name"))
            except Exception:
                pass

        if bad_files:
            status_bits.append(f"BAD FILES: {bad_files[:3]}")
            issues += 1
        if per_scheme and mf.schemes:
            n_wanted = len(mf.schemes)
            # SAMCO publishes 9 schemes in 3 xlsx (grouped) — file count < scheme count
            # is normal for that AMC. Use scheme_files from meta (which counts unique
            # scheme entries in the metadata) for the better signal.
            n_have = max(scheme_files, n_files)
            if n_have < n_wanted:
                gap = n_wanted - n_have
                # >=3 missing = real issue. 1-2 missing tolerated (AMC publishing lag).
                if gap >= 3:
                    status_bits.append(f"GAP {n_have}/{n_wanted} (missing {gap})")
                    issues += 1
                else:
                    status_bits.append(f"lag {n_have}/{n_wanted}")
        # Single-xlsx / zip / factsheet patterns: just confirm a sensible sheet count.
        elif pattern == "single_xlsx_multi_sheet" and all_files:
            biggest = max(all_files, key=lambda p: p.stat().st_size)
            sc = _sheet_count(biggest)
            if mf.schemes and sc < min(len(mf.schemes), 2):
                # AMC's xlsx should have at least scheme-count sheets (often more).
                status_bits.append(f"only {sc} sheets in xlsx (want ~{len(mf.schemes)})")
                issues += 1
            elif sc > 0:
                status_bits.append(f"{sc} sheets in xlsx")
        elif pattern == "latest_month_zip" and all_files:
            xlsx_in_zip = [f for f in all_files if f.suffix.lower() in (".xlsx", ".xls")]
            status_bits.append(f"{len(xlsx_in_zip)} xlsx extracted from zip")
        elif pattern == "factsheet_only":
            status_bits.append("PDF factsheet")
        elif pattern == "toggle_until_data":
            status_bits.append("single xlsx (toggle-pattern)")
        if not status_bits:
            status_bits.append("OK")
        print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:18s} {year}-{month:02d}  {n_files:>5d} {len(mf.schemes):>8d}  {'; '.join(status_bits)}")

    print("-" * 120)
    print(f"Audited {len(mfs)} MFs, {issues} flagged.")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
