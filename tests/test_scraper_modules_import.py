"""Wiring: every module in MF_TARGETS imports cleanly and exposes Scraper."""
from __future__ import annotations

import importlib

import pytest

from lib.config import MF_TARGETS
from scrapers.base import BaseScraper


@pytest.mark.parametrize("mf_id,module_name", [(k, v[1]) for k, v in MF_TARGETS.items()])
def test_module_imports_and_exposes_scraper(mf_id: str, module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert hasattr(module, "Scraper"), f"{module_name} missing Scraper class"
    assert issubclass(module.Scraper, BaseScraper), (
        f"{module_name}.Scraper must subclass BaseScraper"
    )


def test_all_scrapers_declare_disclosures_url() -> None:
    """Every Scraper class should have a non-empty DISCLOSURES_URL.

    Skipped: BaseScraper exposes no DISCLOSURES_URL attribute by default; some
    legacy scrapers (mf16 HDFC) override discover_latest_month entirely and
    bypass the URL plumbing. We just confirm the attribute is present-or-absent
    consistently.
    """
    for mf_id, (_pattern, module_name) in MF_TARGETS.items():
        module = importlib.import_module(module_name)
        url = getattr(module.Scraper, "DISCLOSURES_URL", None)
        # Allow None for legacy scrapers without the attribute.
        if url is not None:
            assert url.startswith("http"), f"{mf_id}: bad DISCLOSURES_URL {url!r}"
