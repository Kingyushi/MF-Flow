"""Parse the user's xlsx into a list of MFConfig + scheme rosters.

The xlsx layout is repeating 4-row blocks separated by blank rows:
    Row 1: col0 = "MF N" (or "MF N " with trailing space), col1 = MF name
    Row 2: col0 = "Schemes",         col1..colN = scheme names
    Row 3: col0 = "URL " (trailing space), col1 = url
    Row 4: col0 = "Instructions for URL", col1 = instructions

This module is the single source of truth for:
  - Which mf_id each AMC maps to (`_NAME_TO_ID`)
  - Which scraper module / pattern handles each mf_id (`MF_TARGETS`)
  - The canonical, user-facing AMC name used for output/<MF Name>/ folders
    (`_CANONICAL_NAME`) — protects on-disk layout from xlsx typos drifting
    over time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import openpyxl

from .log import get_logger
from .paths import INPUT_XLSX

log = get_logger("config")


@dataclass
class MFConfig:
    id: str                          # "mf01"
    name: str                        # canonical name (NOT the xlsx string)
    url: str
    schemes: list[str]               # [] when the xlsx lists NIL schemes
    instructions: str
    pattern: str                     # "single_xlsx_multi_sheet" | ...
    module: str                      # "scrapers.mf01_360one"


# Pattern + module mapping by MF id. Source of truth for which scraper handles
# which target.
#
# Initial pattern guesses for mf22..mf46 are taken from the xlsx instruction
# column. Each scraper subclass picks the correct pattern base for its site;
# the registry pattern label here is for reporting/_meta.json only.
#
# mf07 Bandhan and mf04 Angel One are intentionally absent — registry-only
# removals per user. Their scraper files (scrapers/mf07_bandhan.py,
# scrapers/mf04_angel_one.py) are left on disk for reference. Angel One was
# dropped because it publishes no monthly portfolio disclosure (factsheet only).
MF_TARGETS: dict[str, tuple[str, str]] = {
    "mf01": ("single_xlsx_multi_sheet", "scrapers.mf01_360one"),
    "mf02": ("single_xlsx_multi_sheet", "scrapers.mf02_abakkus"),
    "mf03": ("latest_month_zip",        "scrapers.mf03_aditya_birla"),
    # mf04 Angel One — dropped from registry; factsheet-only, no monthly portfolio.
    "mf05": ("single_xlsx_multi_sheet", "scrapers.mf05_axis"),
    "mf06": ("single_xlsx_multi_sheet", "scrapers.mf06_bajaj_finserv"),
    # mf07 Bandhan — dropped from registry; no public scraping path.
    "mf08": ("single_xlsx_multi_sheet", "scrapers.mf08_bank_of_india"),
    "mf09": ("single_xlsx_multi_sheet", "scrapers.mf09_baroda_bnp"),
    "mf10": ("per_scheme_xlsx",         "scrapers.mf10_canara_robeco"),
    "mf11": ("single_xlsx_multi_sheet", "scrapers.mf11_capital_mind"),
    "mf12": ("latest_month_zip",        "scrapers.mf12_dsp"),
    "mf13": ("single_xlsx_multi_sheet", "scrapers.mf13_edelweiss"),
    "mf14": ("single_xlsx_multi_sheet", "scrapers.mf14_franklin"),
    "mf15": ("single_xlsx_multi_sheet", "scrapers.mf15_groww"),
    "mf16": ("per_scheme_xlsx",         "scrapers.mf16_hdfc"),
    "mf17": ("per_scheme_xlsx",         "scrapers.mf17_helios"),
    "mf18": ("latest_month_zip",        "scrapers.mf18_icici_pru"),
    "mf19": ("per_scheme_xlsx",         "scrapers.mf19_invesco"),
    "mf20": ("single_xlsx_multi_sheet", "scrapers.mf20_iti"),
    "mf21": ("toggle_until_data",       "scrapers.mf21_jio_blackrock"),
    "mf22": ("per_scheme_xlsx",         "scrapers.mf22_jm_financial"),
    "mf23": ("single_xlsx_multi_sheet", "scrapers.mf23_kotak"),
    "mf24": ("per_scheme_xlsx",         "scrapers.mf24_lic"),
    "mf25": ("single_xlsx_multi_sheet", "scrapers.mf25_mahindra_manulife"),
    "mf26": ("per_scheme_xlsx",         "scrapers.mf26_mirae_asset"),
    "mf27": ("single_xlsx_multi_sheet", "scrapers.mf27_motilal_oswal"),
    "mf28": ("per_scheme_xlsx",         "scrapers.mf28_navi"),
    "mf29": ("single_xlsx_multi_sheet", "scrapers.mf29_nippon"),
    "mf30": ("per_scheme_xlsx",         "scrapers.mf30_nj"),
    "mf31": ("per_scheme_xlsx",         "scrapers.mf31_old_bridge"),
    "mf32": ("per_scheme_xlsx",         "scrapers.mf32_pgim"),
    "mf33": ("single_xlsx_multi_sheet", "scrapers.mf33_parag_parikh"),
    "mf34": ("per_scheme_xlsx",         "scrapers.mf34_quant"),
    "mf35": ("single_xlsx_multi_sheet", "scrapers.mf35_quantum"),
    "mf36": ("per_scheme_xlsx",         "scrapers.mf36_samco"),
    "mf37": ("single_xlsx_multi_sheet", "scrapers.mf37_sbi"),
    "mf38": ("single_xlsx_multi_sheet", "scrapers.mf38_shriram"),
    "mf39": ("single_xlsx_multi_sheet", "scrapers.mf39_sundaram"),
    "mf40": ("single_xlsx_multi_sheet", "scrapers.mf40_tata"),
    "mf41": ("per_scheme_xlsx",         "scrapers.mf41_taurus"),
    "mf42": ("single_xlsx_multi_sheet", "scrapers.mf42_trust"),
    "mf43": ("single_xlsx_multi_sheet", "scrapers.mf43_unifi"),
    "mf44": ("latest_month_zip",        "scrapers.mf44_uti"),
    "mf45": ("per_scheme_xlsx",         "scrapers.mf45_wealth_company"),
    "mf46": ("per_scheme_xlsx",         "scrapers.mf46_whiteoak"),
}


# Canonical, user-facing AMC name used for output/<MF Name>/ subfolders and
# reports. Decoupled from the xlsx string so future typo fixes in the xlsx
# don't fragment on-disk output. If you rename one of these, run
# tools/migrate_output_names.py to relocate existing month folders.
_CANONICAL_NAME: dict[str, str] = {
    "mf01": "360 ONE Mutual Fund",
    "mf02": "Abakkus Mutual Fund",
    "mf03": "Aditya Birla Sun Life Mutual Fund",
    # mf04 Angel One — dropped from registry (factsheet-only, no monthly portfolio).
    "mf05": "Axis Mutual Fund",
    "mf06": "Bajaj Finserv Mutual Fund",
    "mf08": "Bank of India Mutual Fund",
    "mf09": "Baroda BNP Paribas Mutual Fund",
    "mf10": "Canara Robeco Mutual Fund",
    "mf11": "Capital Mind Mutual Fund",
    "mf12": "DSP Mutual Fund",
    "mf13": "Edelweiss Mutual Fund",
    "mf14": "Franklin Templeton Mutual Fund",
    "mf15": "Groww Mutual Fund",
    "mf16": "HDFC Mutual Fund",
    "mf17": "Helios Mutual Fund",
    "mf18": "ICICI Prudential Mutual Fund",
    "mf19": "Invesco Mutual Fund",
    "mf20": "ITI Mutual Fund",
    "mf21": "Jio BlackRock Mutual Fund",
    "mf22": "JM Financial Mutual Fund",
    "mf23": "Kotak Mutual Fund",
    "mf24": "LIC Mutual Fund",
    "mf25": "Mahindra Manulife Mutual Fund",
    "mf26": "Mirae Asset Mutual Fund",
    "mf27": "Motilal Oswal Mutual Fund",
    "mf28": "Navi Mutual Fund",
    "mf29": "Nippon India Mutual Fund",
    "mf30": "NJ Mutual Fund",
    "mf31": "Old Bridge Mutual Fund",
    "mf32": "PGIM India Mutual Fund",
    "mf33": "Parag Parikh Mutual Fund",
    "mf34": "Quant Mutual Fund",
    "mf35": "Quantum Mutual Fund",
    "mf36": "SAMCO Mutual Fund",
    "mf37": "SBI Mutual Fund",
    "mf38": "Shriram Mutual Fund",
    "mf39": "Sundaram Mutual Fund",
    "mf40": "Tata Mutual Fund",
    "mf41": "Taurus Mutual Fund",
    "mf42": "Trust Mutual Fund",
    "mf43": "Unifi Mutual Fund",
    "mf44": "UTI Mutual Fund",
    "mf45": "The Wealth Company Mutual Fund",
    "mf46": "WhiteOak Capital Mutual Fund",
}


def canonical_name(mf_id: str) -> str:
    """Public lookup: canonical AMC name for an mf_id, or KeyError."""
    return _CANONICAL_NAME[mf_id]


# AMC name -> MF id used to label each block by canonical id. We normalize
# the AMC name from the spreadsheet (lowercase, strip "mutual fund(s)"/"mf"/"amc").
# Known xlsx typos are mapped to the same id as the canonical spelling.
_NAME_TO_ID: dict[str, str] = {
    "360 one": "mf01",
    "abbakus": "mf02",                  # xlsx typo
    "abakkus": "mf02",
    "aditya birla sun life": "mf03",
    "angel one": "mf04",                # mapped but excluded by MF_TARGETS lookup
    "axis": "mf05",
    "bajaj finserv": "mf06",
    "bandhan": "mf07",                  # mapped but excluded by MF_TARGETS lookup
    "bank of india": "mf08",
    "baroda bnp paribas": "mf09",
    "canara robeco": "mf10",
    "capital mind": "mf11",
    "capitalmind": "mf11",
    "dsp": "mf12",
    "edelweiss": "mf13",
    "franklin templeton": "mf14",
    "groww": "mf15",
    "hdfc": "mf16",
    "helios": "mf17",
    "icici prudential": "mf18",
    "invesco": "mf19",
    "iti": "mf20",
    "jio blackrock": "mf21",
    "jm financial": "mf22",
    "jm finanical": "mf22",             # xlsx typo
    "kotak": "mf23",
    "lic": "mf24",
    "mahindra manulife": "mf25",
    "mirae asset": "mf26",
    "motilal oswal": "mf27",
    "navi": "mf28",
    "nippon india": "mf29",
    "nj": "mf30",
    "old bridge": "mf31",
    "pgim india": "mf32",
    "parag parikh": "mf33",
    "paragh parikh": "mf33",            # xlsx typo
    "quant": "mf34",
    "quantum": "mf35",
    "samco": "mf36",
    "sbi": "mf37",
    "shriram": "mf38",
    "sundaram": "mf39",
    "tata": "mf40",
    "taurus": "mf41",
    "trust": "mf42",
    "unifi": "mf43",
    "uti": "mf44",
    "wealth company": "mf45",
    "the wealth company": "mf45",
    "whiteoak capital": "mf46",
}


def _canonical_id(amc_name: str) -> Optional[str]:
    s = amc_name.lower().strip()
    # Strip "mutual fund(s)" / "amc" / "mf" suffixes/words. Note: xlsx has
    # "Sundaram Mutual Funds" (plural) and "Paragh Parikh Mutual Fund "
    # (trailing space).
    s = re.sub(r"\bmutual\s+funds?\b", "", s).strip()
    s = re.sub(r"\bamc\b", "", s).strip()
    s = re.sub(r"\bmf\b", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return _NAME_TO_ID.get(s)


def load_mfs(xlsx_path: Optional[Path] = None) -> list[MFConfig]:
    path = Path(xlsx_path) if xlsx_path else INPUT_XLSX
    if not path.exists():
        raise FileNotFoundError(f"Input xlsx not found: {path}")
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    out: list[MFConfig] = []
    skip_for_now: list[str] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        c0 = (row[0] or "").strip() if row[0] else ""
        c1 = (row[1] or "").strip() if row[1] else ""
        # Block header: col0 starts with "MF" and col1 is a non-empty AMC name.
        if re.match(r"^MF\s*\d", c0) and c1:
            amc_name = c1
            schemes: list[str] = []
            url = ""
            instructions = ""
            # Look ahead for schemes / url / instructions in the next ~5 rows.
            j = i + 1
            while j < len(rows) and j < i + 6:
                r = rows[j]
                if not r:
                    j += 1
                    continue
                tag = (r[0] or "").strip() if r[0] else ""
                tag_l = tag.lower().rstrip()
                if tag_l == "schemes":
                    schemes = [
                        (v or "").strip()
                        for v in r[1:]
                        if v and (v or "").strip() and (v or "").strip().upper() != "NIL"
                    ]
                elif tag_l == "url":
                    url = ((r[1] or "").strip() if r[1] else "")
                elif tag_l.startswith("instructions"):
                    instructions = ((r[1] or "").strip() if r[1] else "")
                elif re.match(r"^MF\s*\d", tag):
                    break
                j += 1
            mf_id = _canonical_id(amc_name)
            if mf_id is None:
                log.warning("Unknown AMC %r — skipping. Add to _NAME_TO_ID in lib/config.py.", amc_name)
                skip_for_now.append(amc_name)
            else:
                target = MF_TARGETS.get(mf_id)
                if target is None:
                    log.info("AMC %r (%s) is in xlsx but excluded from MF_TARGETS — skipping.", amc_name, mf_id)
                    skip_for_now.append(amc_name)
                else:
                    pattern, module = target
                    # De-dupe schemes while preserving order. Surface duplicates
                    # as a warning (Bandhan source-data oddity case).
                    deduped: list[str] = []
                    seen: set[str] = set()
                    for s in schemes:
                        key = s.lower().strip()
                        if key in seen:
                            log.warning(
                                "Duplicate scheme in %s xlsx row: %r — dropping second copy",
                                amc_name, s,
                            )
                            continue
                        seen.add(key)
                        deduped.append(s)
                    out.append(MFConfig(
                        id=mf_id,
                        name=_CANONICAL_NAME.get(mf_id, amc_name),
                        url=url,
                        schemes=deduped,
                        instructions=instructions,
                        pattern=pattern,
                        module=module,
                    ))
            i = j
            continue
        i += 1

    log.info(
        "Loaded %d MFs from %s (skipped: %s)",
        len(out), path.name, skip_for_now or "none",
    )
    return out
