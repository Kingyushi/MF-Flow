"""Report stale on-disk files (the runner does not auto-delete them).

A file is considered stale when its month folder's `_meta.json` doesn't
mention the file. This happens when:
  - A per-scheme MF used to fetch ALL schemes for month N, then on a later
    run AMC published only some schemes for month N — the old files remain
    untouched on disk while _meta.json was rewritten with fewer entries.
  - A scheme was renamed in the registry and the old filename lingers.

Prints a list of stale files per MF / month. Does NOT delete anything —
review and rm by hand.

Run:
    python tools/report_stale.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import load_mfs       # noqa: E402
from lib.organizer import month_folder  # noqa: E402


def main() -> int:
    mfs = load_mfs()
    stale_total = 0
    for mf in mfs:
        mf_root = (month_folder(mf.name, 1, 1)).parent.parent / Path(mf.name)
        # Better: re-derive root via month_folder for a known year/month then go up.
        sample = month_folder(mf.name, 2000, 1)
        mf_root = sample.parent
        if not mf_root.exists():
            continue
        for sub in sorted(mf_root.iterdir()):
            if not sub.is_dir():
                continue
            meta_path = sub / "_meta.json"
            if not meta_path.exists():
                print(f"  {mf.id} {mf.name} / {sub.name}: no _meta.json (cannot judge)")
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta_files = {f["filename"] for f in meta.get("files", [])}
            except Exception as e:
                print(f"  {mf.id} {mf.name} / {sub.name}: meta read error {e}")
                continue
            on_disk = {p.name for p in sub.iterdir() if p.is_file() and p.name != "_meta.json"}
            stale = sorted(on_disk - meta_files)
            if stale:
                print(f"\n[{mf.id}] {mf.name} / {sub.name}: {len(stale)} stale")
                for s in stale:
                    print(f"    {s}")
                stale_total += len(stale)
    print()
    print(f"Total stale files across all MFs: {stale_total}")
    print("(no files deleted — review and `Remove-Item` manually as needed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
