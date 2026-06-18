"""Audit single-xlsx MFs: open the latest xlsx and confirm it has sheets
covering the user's listed schemes (fuzzy match on sheet name vs scheme name).

Catches "we downloaded a file but it's the wrong file / wrong AMC's data".
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import load_mfs, MF_TARGETS                              # noqa: E402
from lib.organizer import find_existing_month_for_mf, month_folder       # noqa: E402
from lib.scheme_filter import normalize                                  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)  # openpyxl style warnings


def _sheets_of(path: Path) -> list[str]:
    """Return sheet names of an xlsx OR legacy .xls. [] for unreadable."""
    # Sniff signature, not extension — AMCs sometimes serve xlsx with .xls name.
    try:
        head = path.read_bytes()[:8]
    except Exception:
        return []
    if head.startswith(b"PK\x03\x04"):
        # ZIP-based xlsx
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            return wb.sheetnames
        except Exception:
            return []
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        # Legacy CFB .xls — needs xlrd
        try:
            import xlrd
            book = xlrd.open_workbook(str(path))
            return book.sheet_names()
        except ImportError:
            print(f"WARN: .xls reader (xlrd) not installed — cannot read {path.name}")
            return []
        except Exception:
            return []
    return []


def _scheme_present_in_sheets(scheme: str, sheets: list[str]) -> bool:
    sn = normalize(scheme)
    sn_tokens = set(sn.split())
    if not sn_tokens:
        return True
    for sheet in sheets:
        st = normalize(sheet)
        st_tokens = set(st.split())
        # Need at least 2 distinct content tokens to overlap (AMC name + cap-type).
        # Skip generic tokens that bloat every sheet.
        if len(sn_tokens & st_tokens) >= max(2, min(3, len(sn_tokens) - 1)):
            return True
    return False


def main() -> int:
    mfs = load_mfs()
    # Only single-xlsx pattern MFs (one file with sheets per scheme).
    targets = {m.id for m in mfs if MF_TARGETS[m.id][0] == "single_xlsx_multi_sheet"}
    issues = 0
    for mf in mfs:
        if mf.id not in targets:
            continue
        if not mf.schemes:
            continue  # nothing to check
        ym = find_existing_month_for_mf(mf.name)
        if not ym:
            print(f"{mf.id:5s}  {mf.name[:40]:40s}  NO DATA ON DISK")
            issues += 1
            continue
        year, month = ym
        folder = month_folder(mf.name, year, month)
        xlsx_files = [p for p in folder.iterdir() if p.suffix.lower() in (".xlsx", ".xls") and p.name != "_meta.json"]
        if not xlsx_files:
            print(f"{mf.id:5s}  {mf.name[:40]:40s}  NO XLSX")
            issues += 1
            continue
        # Aggregate sheet names across all xlsx files in the folder
        all_sheets: list[str] = []
        for x in xlsx_files:
            all_sheets.extend(_sheets_of(x))
        present = sum(1 for s in mf.schemes if _scheme_present_in_sheets(s, all_sheets))
        missing = [s for s in mf.schemes if not _scheme_present_in_sheets(s, all_sheets)]
        gap = len(mf.schemes) - present
        flag = "OK" if gap == 0 else (
            f"GAP {present}/{len(mf.schemes)}, missing: {missing[:5]}{'…' if len(missing) > 5 else ''}"
        )
        if gap > 0:
            issues += 1
        print(f"{mf.id:5s}  {mf.name[:40]:40s}  sheets={len(all_sheets):>3d}  schemes={present}/{len(mf.schemes)}  {flag}")
    print(f"\nIssues: {issues}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
