"""BaseScraper: two-phase contract, retry decorator, common types."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

from lib.config import MFConfig
from lib.fetcher import Fetcher
from lib.log import get_logger

log = get_logger("scraper")


class NoDataYetError(Exception):
    """Raised by discover_latest_month when the site shows no months at all
    (e.g. fresh page with no disclosure history)."""


class ScraperError(Exception):
    """Generic per-scraper failure."""


@dataclass
class DiscoveryResult:
    year: int
    month: int                                                   # 1-12
    as_on_date: Optional[date] = None
    available_months: list[tuple[int, int]] = field(default_factory=list)
    notes: str = ""


@dataclass
class DownloadedFile:
    src_path: Path
    scheme_name: Optional[str]           # None for single_xlsx_multi_sheet / factsheet
    source_url: str
    label: str                           # filename label (e.g. MF name or scheme name)
    # Per-file month override (used by per-scheme MFs with rolling publication —
    # e.g. WhiteOak's Mid Cap may have a May portfolio while its Flexi Cap
    # only has April). When set, the runner places the file in `output/<MF>/
    # <year-month>/` regardless of the MF-level DiscoveryResult month.
    year: Optional[int] = None
    month: Optional[int] = None


class ScrapeOutcome(Enum):
    OK_DOWNLOADED = "ok"
    SKIPPED_ALREADY_HAVE = "skipped"
    NO_DATA_YET = "no_data_yet"
    ERROR = "error"


@dataclass
class ScrapeReport:
    mf_id: str
    mf_name: str
    outcome: ScrapeOutcome
    year: Optional[int] = None                                # site's latest after this run
    month: Optional[int] = None
    as_on_date: Optional[date] = None
    files_placed: list[Path] = field(default_factory=list)
    matched_schemes: int = 0
    total_schemes: int = 0
    unmatched_schemes: list[str] = field(default_factory=list)
    # Schemes that matched a link but whose actual file download failed
    # (e.g. AMC server 500, timeout, bad signature). Tracked separately from
    # unmatched_schemes so partial downloads don't read as "OK" in STATUS.
    download_failures: list[str] = field(default_factory=list)
    error: str = ""
    # Snapshot of (year, month) already on disk BEFORE this run started — used by
    # the incremental report to compute change_type (NEW_MONTH vs UNCHANGED vs FIRST_RUN).
    previous_year: Optional[int] = None
    previous_month: Optional[int] = None

    def status_line(self) -> str:
        if self.outcome == ScrapeOutcome.OK_DOWNLOADED:
            base = f"{self.mf_name}: OK {self.year}-{self.month:02d}"
            if self.files_placed:
                base += f" ({len(self.files_placed)} file{'s' if len(self.files_placed) != 1 else ''})"
            if self.total_schemes and self.matched_schemes < self.total_schemes:
                base += f" matched {self.matched_schemes}/{self.total_schemes}"
                if self.unmatched_schemes:
                    base += f" unmatched={self.unmatched_schemes!r}"
            if self.download_failures:
                base += (
                    f" PARTIAL: {len(self.download_failures)} download "
                    f"failure(s) {self.download_failures!r}"
                )
            return base
        if self.outcome == ScrapeOutcome.SKIPPED_ALREADY_HAVE:
            return f"{self.mf_name}: skipped, already have {self.year}-{self.month:02d}"
        if self.outcome == ScrapeOutcome.NO_DATA_YET:
            return f"{self.mf_name}: no data yet" + (f" (still on {self.year}-{self.month:02d})" if self.year else "")
        return f"{self.mf_name}: ERROR — {self.error}"


def retry(
    *,
    times: int = 2,
    backoff: tuple[float, ...] = (5.0, 15.0),
    catch: tuple[type[BaseException], ...] = (Exception,),
    skip: tuple[type[BaseException], ...] = (NoDataYetError,),
):
    """Retry decorator. Backoff sleeps applied BEFORE each retry (not after final fail).
    Exceptions in `skip` bypass retry entirely (re-raised immediately)."""
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            attempts = times + 1
            last_err: Optional[BaseException] = None
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except skip:
                    raise
                except catch as e:
                    last_err = e
                    if i + 1 < attempts:
                        delay = backoff[min(i, len(backoff) - 1)]
                        log.warning(
                            "%s: attempt %d/%d failed (%s); retrying in %.1fs",
                            fn.__qualname__, i + 1, attempts, type(e).__name__, delay,
                        )
                        time.sleep(delay)
                    else:
                        log.error(
                            "%s: all %d attempts failed (%s); raising",
                            fn.__qualname__, attempts, e,
                        )
            assert last_err is not None
            raise last_err
        return wrapper
    return decorator


class BaseScraper:
    """All per-MF scrapers extend this. Subclasses override the two methods
    AND set PATTERN. Pattern base classes (single_xlsx, per_scheme, etc.)
    typically sit between BaseScraper and the concrete per-MF subclass."""

    PATTERN: str = "unknown"

    def __init__(self, mf: MFConfig) -> None:
        self.mf = mf

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        raise NotImplementedError

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        raise NotImplementedError


def host_of(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or ""
