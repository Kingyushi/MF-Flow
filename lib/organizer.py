"""Per-MF idempotency check + month-folder file placement + metadata.

Layout:
    OUTPUT_ROOT/
      <MF Name>/
        <Month YYYY>/
          <file1>.xlsx
          <file2>.xlsx
          _meta.json
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .log import get_logger
from .month_hint import ALL_MONTHS, format_month
from .paths import OUTPUT_ROOT
from .sanitize import safe_filename

log = get_logger("organizer")

_MONTH_NAMES = "|".join(sorted(ALL_MONTHS.keys(), key=len, reverse=True))
_MONTH_FOLDER_RE = re.compile(
    rf"^(?P<month>{_MONTH_NAMES})[a-z]*\s+(?P<year>20\d{{2}})$",
    re.IGNORECASE,
)


def _mf_root(mf_name: str) -> Path:
    return OUTPUT_ROOT / safe_filename(mf_name)


def find_existing_month_for_mf(mf_name: str) -> Optional[tuple[int, int]]:
    """Latest (year, month) already on disk for this MF, or None."""
    root = _mf_root(mf_name)
    if not root.exists():
        return None
    found: list[tuple[int, int]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        m = _MONTH_FOLDER_RE.match(child.name)
        if not m:
            continue
        month_word = m.group("month").lower()
        if month_word not in ALL_MONTHS:
            continue
        found.append((int(m.group("year")), ALL_MONTHS[month_word]))
    return max(found) if found else None


def month_folder(mf_name: str, year: int, month: int) -> Path:
    return _mf_root(mf_name) / format_month(year, month)


def list_existing_files(mf_name: str, year: int, month: int) -> list[Path]:
    folder = month_folder(mf_name, year, month)
    if not folder.exists():
        return []
    return [p for p in folder.iterdir() if p.is_file() and p.name != "_meta.json"]


def place_file(
    source: Path,
    mf_name: str,
    year: int,
    month: int,
    *,
    label: str,
    overwrite: bool = False,
) -> Path:
    """Move source -> <MF>/<Month YYYY>/<label> <Month YYYY><ext>."""
    if not source.exists():
        raise FileNotFoundError(f"place_file: source missing {source}")
    ext = source.suffix
    safe_label = safe_filename(label)
    month_label = format_month(year, month)
    target_dir = month_folder(mf_name, year, month)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{safe_label} {month_label}{ext}"
    if target.exists() and not overwrite:
        log.info("place_file: target exists, discarding new copy: %s", target.name)
        try:
            source.unlink(missing_ok=True)
        except OSError:
            pass
        return target
    shutil.move(str(source), str(target))
    log.info("placed %s -> %s", label, target.name)
    return target


@dataclass
class FileMeta:
    filename: str
    scheme_name: Optional[str]
    source_url: str


def write_meta(
    mf_name: str,
    year: int,
    month: int,
    *,
    pattern: str,
    as_on_date: Optional[str],
    files: list[FileMeta],
) -> Path:
    """Write _meta.json into the month folder."""
    folder = month_folder(mf_name, year, month)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "mf_name": mf_name,
        "month": format_month(year, month),
        "year": year,
        "month_num": month,
        "as_on_date": as_on_date,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "pattern": pattern,
        "files": [
            {
                "filename": f.filename,
                "scheme_name": f.scheme_name,
                "source_url": f.source_url,
            }
            for f in files
        ],
    }
    path = folder / "_meta.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
