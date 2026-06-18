"""Resolve project paths from env or defaults. Loaded once at startup.

To override (e.g. point the input xlsx elsewhere) set env vars:
    INPUT_XLSX    = path to the MF scope xlsx
    OUTPUT_ROOT   = parent folder for <MF Name>\\<Month YYYY>\\ subtrees
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

CODE_ROOT: Path = Path(__file__).resolve().parent.parent

# Load .env from project root early so subsequent _env_path() calls see them.
load_dotenv(CODE_ROOT / ".env")


def _env_path(key: str, default: Path) -> Path:
    v = os.environ.get(key)
    return Path(v) if v else default


INPUT_XLSX: Path = _env_path(
    "INPUT_XLSX",
    Path(r"C:\Users\aayus\OneDrive\Desktop\MF Flow (08062026).xlsx"),
)
OUTPUT_ROOT: Path = _env_path(
    "OUTPUT_ROOT",
    CODE_ROOT / "output",
)

# Runtime artifacts under %LOCALAPPDATA% so they don't pollute the project tree.
_runtime_base = (
    Path(os.environ.get("LOCALAPPDATA")) if os.environ.get("LOCALAPPDATA")
    else Path.home() / ".cache"
) / "MF Flow"
DOWNLOADS_DIR: Path = _runtime_base / "downloads"
LOGS_DIR: Path = CODE_ROOT / "logs"
REPORTS_DIR: Path = CODE_ROOT / "reports"


def ensure_runtime_dirs() -> None:
    for d in (DOWNLOADS_DIR, LOGS_DIR, REPORTS_DIR, OUTPUT_ROOT):
        d.mkdir(parents=True, exist_ok=True)
