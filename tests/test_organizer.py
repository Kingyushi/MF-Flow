"""Organizer idempotency + placement tests using a tmp_path OUTPUT_ROOT."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import lib.paths as paths_mod
import lib.organizer as organizer_mod


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Redirect OUTPUT_ROOT to a tmp dir."""
    monkeypatch.setattr(paths_mod, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(organizer_mod, "OUTPUT_ROOT", tmp_path)
    return tmp_path


def test_no_existing_returns_none(tmp_output):
    assert organizer_mod.find_existing_month_for_mf("HDFC Mutual Fund") is None


def test_finds_existing_month(tmp_output):
    (tmp_output / "HDFC Mutual Fund" / "May 2026").mkdir(parents=True)
    (tmp_output / "HDFC Mutual Fund" / "May 2026" / "dummy.xlsx").write_bytes(b"PK\x03\x04")
    assert organizer_mod.find_existing_month_for_mf("HDFC Mutual Fund") == (2026, 5)


def test_returns_latest_when_multiple(tmp_output):
    base = tmp_output / "HDFC Mutual Fund"
    (base / "March 2026").mkdir(parents=True)
    (base / "May 2026").mkdir(parents=True)
    (base / "April 2026").mkdir(parents=True)
    assert organizer_mod.find_existing_month_for_mf("HDFC Mutual Fund") == (2026, 5)


def test_place_file(tmp_output, tmp_path):
    src = tmp_path / "source.xlsx"
    src.write_bytes(b"PK\x03\x04hello")
    target = organizer_mod.place_file(
        src, "HDFC Mutual Fund", 2026, 5, label="HDFC Flexi Cap Fund",
    )
    assert target.exists()
    assert target.name == "HDFC Flexi Cap Fund May 2026.xlsx"
    assert not src.exists()


def test_place_file_skips_existing_without_overwrite(tmp_output, tmp_path):
    src1 = tmp_path / "src1.xlsx"
    src1.write_bytes(b"first")
    organizer_mod.place_file(src1, "HDFC", 2026, 5, label="Flexi Cap")
    src2 = tmp_path / "src2.xlsx"
    src2.write_bytes(b"second")
    target = organizer_mod.place_file(src2, "HDFC", 2026, 5, label="Flexi Cap")
    # src2 discarded, target still holds first content
    assert target.read_bytes() == b"first"


def test_write_meta(tmp_output):
    organizer_mod.write_meta(
        "HDFC Mutual Fund", 2026, 5,
        pattern="per_scheme_xlsx",
        as_on_date="2026-05-31",
        files=[
            organizer_mod.FileMeta(
                filename="HDFC Flexi Cap Fund May 2026.xlsx",
                scheme_name="HDFC Flexi cap fund",
                source_url="https://example.com/flexi.xlsx",
            ),
        ],
    )
    meta = tmp_output / "HDFC Mutual Fund" / "May 2026" / "_meta.json"
    assert meta.exists()
    import json
    data = json.loads(meta.read_text())
    assert data["pattern"] == "per_scheme_xlsx"
    assert data["as_on_date"] == "2026-05-31"
    assert len(data["files"]) == 1
    assert data["files"][0]["scheme_name"] == "HDFC Flexi cap fund"
