# Resume snapshot — 2026-06-08 20:30 IST

You went offline mid-live-run. Run was stopped cleanly. Everything is safe; no
partial files. Pick up from here when you're back online.

## What's complete and verified

- **Foundation**: 45 MFs loaded (mf01–mf46 minus mf07 Bandhan). Canonical
  name map in `lib/config._CANONICAL_NAME`. `INPUT_XLSX` points at
  `MF Flow (08062026).xlsx`.
- **Tests**: `pytest tests/` → 163/163 green.
- **Dry-run discovery**: 44/45 MFs successfully discover the latest month.
  The 1 known failure is Edelweiss (mf13) — site moved to encrypted-POST
  VAPT mode; documented in `scrapers/LEARNINGS.md` with 3 recovery paths.

## What partially ran

Live-download run was at mf24 LIC when stopped. Successful downloads landed
in `output/<MF Name>/<Month YYYY>/`. Verify with:

```powershell
cd "C:\DEV\MF Flow"
Get-ChildItem output -Directory | ForEach-Object {
  $newest = Get-ChildItem $_.FullName -Directory | Sort-Object Name -Descending | Select-Object -First 1
  if ($newest) { "{0,-45}  {1}" -f $_.Name, $newest.Name }
}
```

Confirmed downloaded fresh in this run (visible in `logs/run-2026-06-08.log`):
HDFC (12 files), Helios (5), JM Financial (3 of 6 schemes matched). The other
~16 fresh-download MFs from earlier dry-run iterations also have data.

## Known issues to fix when you're back

1. **mf22 JM Financial — scheme matching 3/6.** User's xlsx scheme list is
   prefixed with `"Monthly Portfolio - "` which trips the matcher. Easiest
   fix: strip that prefix in `_NAME_TO_ID` normalization, or pre-process
   scheme strings before scheme_filter runs. ~10 min.

2. **mf23 Kotak — download URL bad.** Discovery returns
   `https://www.kotakmf.com/FormsDownloads/Portfolios/Consolidated-Portfolio-as-on-April-30,-2026/ConsolidatedSEBIPortfolioApril2026.xlsx`
   but the server rejects the GET. Likely needs Playwright click-to-download
   instead of direct URL fetch. ~15-30 min.

3. **mf24 LIC — click_to_download timeout on every scheme.** The Playwright
   click triggers but no download event fires within 60s. Probably the form
   submit returns an xlsx in a new window/tab, or expects different click
   timing. Needs targeted debug. ~30 min.

4. **mf13 Edelweiss — broken upstream.** Site enabled hybrid-crypto-js VAPT
   mode requiring RSA-encrypted POST bodies. Documented in
   `scrapers/LEARNINGS.md` and
   `memory/edelweiss_encrypted_api.md`. Three recovery paths listed;
   easiest is waiting for Edelweiss to add monthly portfolio to the
   `mf/statutory-menus` GET tier (scraper has forward-compatible fallback).

## How to resume

```powershell
cd "C:\DEV\MF Flow"

# Pick up where the run stopped — only the MFs not yet downloaded this cycle
.\.venv\Scripts\python.exe run_scraper.py

# Or a single MF iteration during fixing
.\.venv\Scripts\python.exe run_scraper.py --only mf23
.\.venv\Scripts\python.exe run_scraper.py --only mf24 --headed   # visible browser
```

The runner is idempotent: anything already on disk gets `skipped, already have`.

## Files of interest

- `scrapers/LEARNINGS.md` — per-AMC mechanism notes and "if it breaks, check" hints
- `tools/probe_out/INDEX.md` — original DOM probe summary
- `tools/probe_out/<mf_id>_postclick.json` — live-DOM probes from the fix pass
- `reports/run-2026-06-08.xlsx` — last full dry-run report
- `reports/master-log.csv` — append-only cross-run change log
- `logs/run-2026-06-08.log` — full run log with stack traces

## Final score (as of when you went offline)

- 45 MFs registered (44 active + 1 broken)
- 27 new scrapers built and tested
- 163 unit tests green
- 44 / 45 discover OK live
- Estimated 41 / 45 will fully download once Kotak + LIC + JM-matching fixes land
  (Edelweiss stays broken without RSA encryption work)
