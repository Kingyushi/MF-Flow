"""One-shot: rename existing output/<old name>/ folders to canonical names.

The canonical name map (lib/config._CANONICAL_NAME) is the new source of truth
for on-disk folder names. This script scans the current OUTPUT_ROOT for any
folder whose name is a known alias of a canonical and renames it.

Idempotent — running twice is a no-op. Bandhan output is left alone since the
AMC is dropped from the registry but its historical data stays valid.

Run:
    python tools/migrate_output_names.py            # show plan, then prompt
    python tools/migrate_output_names.py --yes      # apply without prompt
    python tools/migrate_output_names.py --dry-run  # just print what would change
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import _CANONICAL_NAME           # noqa: E402
from lib.paths import OUTPUT_ROOT                # noqa: E402
from lib.sanitize import safe_filename           # noqa: E402

# Map of legacy on-disk names (from older xlsx versions) → new canonical name.
# Any folder whose name matches a key here gets renamed.
LEGACY_ALIASES: dict[str, str] = {
    "Abbakus mutual fund": _CANONICAL_NAME["mf02"],
    "Abbakus Mutual Fund": _CANONICAL_NAME["mf02"],
    "Capital Mind Mutual Fund": _CANONICAL_NAME["mf11"],
    "Capitalmind Mutual Fund": _CANONICAL_NAME["mf11"],
    "Kotak mutual fund": _CANONICAL_NAME["mf23"],
    "JM Finanical Mutual Fund": _CANONICAL_NAME["mf22"],
    "Paragh Parikh Mutual Fund": _CANONICAL_NAME["mf33"],
    "Sundaram Mutual Funds": _CANONICAL_NAME["mf39"],
    "WhiteOak Capital MutuAL Fund": _CANONICAL_NAME["mf46"],
    "WhiteOak Capital MutuAL Fund ": _CANONICAL_NAME["mf46"],
}


def plan_renames(root: Path) -> list[tuple[Path, Path]]:
    if not root.exists():
        return []
    canonical_set = set(_CANONICAL_NAME.values())
    canonical_safe = {safe_filename(n): n for n in canonical_set}
    plan: list[tuple[Path, Path]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        # Already canonical → nothing to do.
        if child.name in canonical_set:
            continue
        if child.name in canonical_safe:
            continue
        # Direct alias lookup.
        target_name = LEGACY_ALIASES.get(child.name)
        if not target_name:
            # Try the sanitized form too.
            target_name = LEGACY_ALIASES.get(child.name.strip())
        if not target_name:
            continue
        target = root / safe_filename(target_name)
        plan.append((child, target))
    return plan


def apply_renames(plan: list[tuple[Path, Path]]) -> int:
    moved = 0
    for src, dst in plan:
        if dst.exists():
            # Merge: move each subfolder/file individually.
            print(f"MERGE {src.name} -> {dst.name}/ (target exists)")
            for item in src.iterdir():
                target_item = dst / item.name
                if target_item.exists():
                    print(f"  skip (exists): {item.name}")
                    continue
                shutil.move(str(item), str(target_item))
            try:
                src.rmdir()
            except OSError:
                print(f"  could not remove {src.name} (non-empty)")
        else:
            print(f"RENAME {src.name} -> {dst.name}")
            shutil.move(str(src), str(dst))
        moved += 1
    return moved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="Apply without prompting")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"Output root: {OUTPUT_ROOT}")
    plan = plan_renames(OUTPUT_ROOT)
    if not plan:
        print("No legacy folder names found — nothing to migrate.")
        return 0
    print(f"\n{len(plan)} folder(s) to rename:")
    for src, dst in plan:
        print(f"  {src.name}  ->  {dst.name}")
    if args.dry_run:
        return 0
    if not args.yes:
        ans = input("\nProceed? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 1
    moved = apply_renames(plan)
    print(f"\nRenamed {moved} folder(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
