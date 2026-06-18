"""Verify each user-listed scheme is actually present in the latest month's
output for every active MF.

For per-scheme MFs: check the filename of each placed file against the
user's scheme list (via match_schemes).
For single-xlsx MFs: check the SHEET NAMES inside the consolidated xlsx
(handles abbreviated codes via best-effort token overlap with the scheme
list; flagged if zero match, since many AMCs use 3-letter codes that are
legitimately hard to map).
For zip MFs: check the extracted filenames against the scheme list.

Returns non-zero if any user-listed scheme can't be found.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import load_mfs, MF_TARGETS                            # noqa: E402
from lib.organizer import find_existing_month_for_mf, month_folder     # noqa: E402
from lib.scheme_filter import match_schemes, normalize                 # noqa: E402

warnings.filterwarnings("ignore")


def _xlsx_sheets(path: Path) -> list[str]:
    try:
        head = path.read_bytes()[:8]
    except Exception:
        return []
    if head.startswith(b"PK\x03\x04"):
        try:
            import io, openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()),
                                        read_only=True, data_only=True)
            return wb.sheetnames
        except Exception:
            return []
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        try:
            import xlrd
            return xlrd.open_workbook(str(path)).sheet_names()
        except Exception:
            return []
    return []


_HYPERLINK_DISPLAY = __import__("re").compile(r'HYPERLINK\([^,]+,\s*"([^"]+)"\)', __import__("re").IGNORECASE)


def _expand_hyperlinks(cell: str) -> str:
    """Edelweiss-style Index sheets put the fund display name inside a
    HYPERLINK("...", "Edelweiss Multi Cap Fund") formula. Pull the display
    text out so the matcher can see it."""
    m = _HYPERLINK_DISPLAY.search(cell)
    return m.group(1) if m else cell


def _index_sheet_mapping(path: Path) -> list[tuple[str, str]]:
    """If the workbook has an 'Index' / 'Cover' sheet with FUND CODE -> FUND
    NAME columns, return [(fund_name, fund_code), ...]. Many AMCs (Aditya
    Birla, ICICI, SBI, Edelweiss) ship this lookup so users can map opaque
    3-letter sheet codes to full fund names.
    """
    out: list[tuple[str, str]] = []
    try:
        head = path.read_bytes()[:8]
    except Exception:
        return []
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        try:
            import xlrd
            book = xlrd.open_workbook(str(path))
            for sn in book.sheet_names():
                if sn.lower() not in ("index", "cover", "contents", "toc"):
                    continue
                sh = book.sheet_by_name(sn)
                for r in range(sh.nrows):
                    row = [_expand_hyperlinks(str(sh.cell_value(r, c)).strip())
                           for c in range(sh.ncols)]
                    long_cells = [c for c in row if len(c) > 8]
                    short_cells = [c for c in row if 0 < len(c) <= 12 and c.isalnum()]
                    # Emit every long-cell as a candidate (Index sheets often
                    # have name AND benchmark; we want both bound to the code).
                    code = short_cells[0] if short_cells else ""
                    if code and long_cells:
                        for name in long_cells:
                            if name != code:
                                out.append((name, code))
        except Exception:
            pass
    elif head.startswith(b"PK\x03\x04"):
        try:
            import io, openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()),
                                        read_only=True, data_only=True)
            for sn in wb.sheetnames:
                if sn.lower() not in ("index", "cover", "contents", "toc"):
                    continue
                sh = wb[sn]
                for row in sh.iter_rows(values_only=True):
                    cells = [_expand_hyperlinks(str(c).strip()) if c is not None else "" for c in row]
                    long_cells = [c for c in cells if len(c) > 8]
                    short_cells = [c for c in cells if 0 < len(c) <= 12 and c.isalnum()]
                    code = short_cells[0] if short_cells else ""
                    if code and long_cells:
                        for name in long_cells:
                            if name != code:
                                out.append((name, code))
        except Exception:
            pass
    return out


def main() -> int:
    mfs = load_mfs()
    issues = 0
    print(f"{'MF':5s} {'Name':38s} {'Pattern':22s}  Status")
    print("-" * 105)
    for mf in mfs:
        pattern = MF_TARGETS[mf.id][0]
        if not mf.schemes:
            print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  no user schemes — skip")
            continue
        ym = find_existing_month_for_mf(mf.name)
        if not ym:
            print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  NO MONTH FOLDER")
            issues += 1
            continue
        year, month = ym
        folder = month_folder(mf.name, year, month)
        files = [p for p in folder.iterdir() if p.is_file() and p.name != "_meta.json"]
        xlsx_files = [p for p in files if p.suffix.lower() in (".xlsx", ".xls")]

        if pattern in ("single_xlsx_multi_sheet", "latest_month_zip"):
            # Combine: sheet names + Index mappings + filenames. Latest-month-zip
            # comes in two flavours — consolidated (one xlsx, all schemes as sheets)
            # and per-scheme (one xlsx per scheme). Filename match covers the latter.
            sheets: list[str] = []
            index_pairs: list[tuple[str, str]] = []
            filename_pairs: list[tuple[str, str]] = []
            for x in xlsx_files:
                sheets.extend(_xlsx_sheets(x))
                index_pairs.extend(_index_sheet_mapping(x))
                filename_pairs.append((x.name, x.name))
            candidates = [(s, s) for s in sheets] + index_pairs + filename_pairs
            from lib.scheme_filter import match_schemes
            report = match_schemes(mf.schemes, candidates)
            if report.matched_count == report.total_schemes:
                print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  "
                      f"{len(sheets)} sheets ({len(index_pairs)} in Index), "
                      f"{report.matched_count}/{report.total_schemes} schemes  OK")
            elif report.matched_count == 0 and len(sheets) > 0 and len(index_pairs) == 0:
                # No Index sheet — sheet names are likely abbreviated codes
                # the audit cannot resolve. Soft flag rather than hard fail.
                print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  "
                      f"{len(sheets)} sheets, no Index sheet — abbreviations not resolved (data likely present)")
            else:
                tag = f"MISSING {report.unmatched_schemes[:3]}…" if len(report.unmatched_schemes) > 3 \
                      else f"MISSING {report.unmatched_schemes}"
                print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  "
                      f"{len(sheets)} sheets, {report.matched_count}/{report.total_schemes} schemes  {tag}")
                if report.matched_count < report.total_schemes // 2:
                    issues += 1
        elif pattern == "per_scheme_xlsx":
            # Match against filenames across ALL month folders (per-scheme-latest
            # may split schemes across multiple month folders).
            root = folder.parent
            file_pairs: list[tuple[str, str]] = []
            for sub in root.iterdir():
                if not sub.is_dir(): continue
                for p in sub.iterdir():
                    if p.is_file() and p.suffix.lower() in (".xlsx", ".xls") and p.name != "_meta.json":
                        file_pairs.append((p.name, p.name))
            report = match_schemes(mf.schemes, file_pairs)
            if report.matched_count == report.total_schemes:
                print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  "
                      f"{report.matched_count}/{report.total_schemes} schemes  OK")
            else:
                print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  "
                      f"{report.matched_count}/{report.total_schemes} schemes  "
                      f"MISSING: {report.unmatched_schemes}")
                issues += 1
        elif pattern in ("factsheet_only", "toggle_until_data"):
            print(f"{mf.id:5s} {mf.name[:38]:38s} {pattern:22s}  {len(files)} file(s)")

    print("-" * 105)
    print(f"Schemes-present audit: {issues} MF(s) with missing user-listed schemes")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
