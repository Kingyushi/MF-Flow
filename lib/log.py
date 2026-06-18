"""Structured logging: file + console."""
from __future__ import annotations

import logging
import sys
from datetime import date

from .paths import LOGS_DIR, ensure_runtime_dirs

_CONFIGURED = False


def get_logger(name: str = "mfflow") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        ensure_runtime_dirs()
        root = logging.getLogger("mfflow")
        root.setLevel(logging.INFO)
        fmt = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        fh = logging.FileHandler(
            LOGS_DIR / f"run-{date.today().isoformat()}.log",
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)

        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)

        _CONFIGURED = True

    return logging.getLogger(f"mfflow.{name}") if name != "mfflow" else logging.getLogger("mfflow")
