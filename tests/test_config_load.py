"""Wiring: load_mfs() returns the expected set; canonical names cover all ids."""
from __future__ import annotations

import re

from lib.config import MF_TARGETS, _CANONICAL_NAME, load_mfs


def test_load_mfs_count() -> None:
    """44 active MFs (xlsx has 46 AMCs; Bandhan mf07 and Angel One mf04 are
    dropped from the registry)."""
    mfs = load_mfs()
    assert len(mfs) == 44, f"expected 44 MFs, got {len(mfs)}"


def test_no_bandhan() -> None:
    mfs = load_mfs()
    assert not any(m.id == "mf07" for m in mfs), "mf07 Bandhan must be dropped"
    assert not any("bandhan" in m.name.lower() for m in mfs)


def test_no_angel_one() -> None:
    mfs = load_mfs()
    assert not any(m.id == "mf04" for m in mfs), "mf04 Angel One must be dropped"
    assert not any("angel" in m.name.lower() for m in mfs)


def test_every_loaded_mf_has_canonical_name() -> None:
    mfs = load_mfs()
    for m in mfs:
        assert m.id in _CANONICAL_NAME, f"{m.id} missing from _CANONICAL_NAME"
        assert m.name == _CANONICAL_NAME[m.id], (
            f"{m.id} name {m.name!r} != canonical {_CANONICAL_NAME[m.id]!r}"
        )


def test_canonical_names_match_targets_keys() -> None:
    assert set(MF_TARGETS) == set(_CANONICAL_NAME), (
        f"MF_TARGETS keys {set(MF_TARGETS) - set(_CANONICAL_NAME)} vs "
        f"_CANONICAL_NAME keys {set(_CANONICAL_NAME) - set(MF_TARGETS)}"
    )


def test_ids_are_well_formed() -> None:
    for mf_id in MF_TARGETS:
        assert re.fullmatch(r"mf\d{2}", mf_id), f"bad mf_id format: {mf_id}"


def test_modules_paths_resolve_to_scrapers_pkg() -> None:
    for mf_id, (pattern, module) in MF_TARGETS.items():
        assert module.startswith("scrapers."), f"{mf_id}: module {module} not under scrapers."
        assert pattern in {
            "single_xlsx_multi_sheet", "per_scheme_xlsx",
            "latest_month_zip", "factsheet_only", "toggle_until_data",
        }, f"{mf_id}: unknown pattern label {pattern}"


def test_canonical_names_unique() -> None:
    names = list(_CANONICAL_NAME.values())
    assert len(names) == len(set(names)), "Canonical names must be unique"
