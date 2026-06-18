# MF Flow scraper — Developer Handoff & Deployment Runbook

This document is written for the **developer wiring the scraper into a Linux /
DigitalOcean droplet**. It is self-contained: follow it top to bottom on a fresh
server and you will have a working, scheduled scraper. For internals and
per-AMC mechanics, see [`README.md`](README.md) and
[`scrapers/LEARNINGS.md`](scrapers/LEARNINGS.md).

---

## 1. What this is

A daily scraper that downloads the **latest monthly portfolio disclosure** for
**44 Indian mutual fund houses (AMCs)** into a tidy folder tree. You do **not**
tell it which month — each AMC's scraper discovers the newest published month on
that AMC's site and downloads it. The run is **idempotent**: months already on
disk are skipped, so it is safe to run daily (or re-run after a failure).

- Input: one Excel file (the client's MF + scheme list).
- Output: `output/<MF Name>/<Month YYYY>/<files>.xlsx` plus a per-run report.
- Runtime: ~5–15 min for a full pass (44 sites, headless Chromium).
- No database, no API keys, no inbound ports. It only reads the xlsx and writes files.

---

## 2. What you received / repository inventory

Ship these (everything tracked in git; the sync command in §9 of the README
lists the exact set):

| Path | What it is |
|---|---|
| `run_scraper.py` | Entry point. Iterates all AMCs, two-phase discover → download. |
| `lib/` | Config/xlsx parsing, fetcher (requests + Playwright), file organizer, reports, paths. |
| `scrapers/` | One module per AMC (`mfNN_*.py`) + shared `patterns/` + `base.py`. |
| `scrapers/LEARNINGS.md` | Per-AMC mechanism notes + "if it breaks, check…" hints. |
| `tests/` | 168 tests (wiring + per-scraper parse fixtures). |
| `tools/` | `probe_amc.py` (re-probe a site after it redesigns), `migrate_output_names.py`. |
| `bin/run.sh` | Cron-safe wrapper (absolute paths, date-stamped log). |
| `requirements.txt` | Python deps. |
| `package.json` | Node dep — **only** for Edelweiss (mf13). |
| `.env.example` | Copy to `.env` and edit. |
| `README.md` | Full reference. |

**Do NOT copy** (regenerated on the droplet; all in `.gitignore`): `.venv/`,
`output/`, `logs/`, `reports/`, `__pycache__/`, `.pytest_cache/`,
`node_modules/`, `tools/probe_out/`, and the client's real `.env`.

**The input xlsx is delivered separately** (it is the client's data, not in
git). Place it on the droplet and point `INPUT_XLSX` at it (see §5).

---

## 3. Prerequisites

- **OS**: Ubuntu/Debian droplet (tested pattern; any modern Linux works).
- **Python 3.12+** (3.13 used in dev).
- **Node.js 18+** — only needed for Edelweiss (mf13). If absent, the other 43
  AMCs run fine and Edelweiss raises a clear, named error.
- **Chromium system libraries** — Playwright installs the browser binary, but
  Chromium needs OS libs. `playwright install-deps` handles this (needs sudo).
- **Outbound HTTPS** to AMC sites. A residential **proxy is required only** if
  the droplet's IP is Cloudflare-blocked by a couple of AMCs (see §7).

---

## 4. Install (fresh droplet, from scratch)

```bash
# 0. Pick a home. The wrapper bin/run.sh assumes /opt/mf-flow — either use that
#    path or edit PROJECT_DIR at the top of bin/run.sh to match.
sudo mkdir -p /opt/mf-flow && sudo chown "$USER" /opt/mf-flow
cd /opt/mf-flow
# ...copy the repo contents here (tarball/scp/git). Then:

# 1. Python venv + deps
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

# 2. Chromium browser + its OS libraries
./.venv/bin/python -m playwright install chromium
sudo ./.venv/bin/python -m playwright install-deps    # apt installs libnss3, etc.

# 3. Node deps (Edelweiss only). Skip if you don't need mf13 today.
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install                                           # installs hybrid-crypto-js
node --version                                        # confirm >= v18

# 4. Config
cp .env.example .env
chmod 600 .env
#    edit .env: set INPUT_XLSX and OUTPUT_ROOT (see §5)

# 5. Put the client's xlsx where INPUT_XLSX points, e.g.:
#    /opt/mf-flow/input.xlsx
```

---

## 5. Configure `.env`

The runner loads `.env` automatically at startup (via `python-dotenv` in
`lib/paths.py`), so it works under cron's empty environment. Minimum on a
droplet:

```ini
INPUT_XLSX=/opt/mf-flow/input.xlsx
OUTPUT_ROOT=/opt/mf-flow/output
```

Proxy vars are optional — see §7. Full reference: `.env.example`.

---

## 6. Verify before scheduling (do all three)

```bash
cd /opt/mf-flow

# (a) Unit tests — must be 168 passed.
./.venv/bin/python -m pytest tests/ -q

# (b) Live discovery, no downloads — confirms all 44 sites reachable from this IP.
./.venv/bin/python run_scraper.py --dry-run
#     Expect: "44 MFs — OK=… skipped=… error=0". Investigate any error=N>0
#     (usually a Cloudflare 403 → see §7, or a site redesign → see §8).

# (c) CRON-EMPTY-ENVIRONMENT test — the single most important pre-flight.
#     Cron runs with NO environment. This proves .env loading works there.
env -i /opt/mf-flow/.venv/bin/python /opt/mf-flow/run_scraper.py --dry-run
#     If (b) passes but (c) fails, your .env is not being read — fix before cron.

# (d) One real end-to-end download as a final smoke test:
./.venv/bin/python run_scraper.py --only mf16     # HDFC, multi-file
ls "output/HDFC Mutual Fund/"                      # should show the latest month
```

> Why (c) matters: in past projects jobs passed in an interactive shell and then
> failed silently under cron because the environment was empty. Always test the
> production invocation path, not your login shell.

---

## 7. Proxy (only if the droplet IP is blocked)

Most AMCs work direct from a DO droplet. A few return Cloudflare **403** from
data-center ASNs. If `--dry-run` reports errors for **DSP** or **HDFC**, route
just those hosts through a residential proxy:

```ini
MF_FLOW_PROXY=http://user:pass@residential-proxy.example.com:7777
MF_FLOW_PROXY_HOSTS=dspim.com,hdfcfund.com,files.hdfcfund.com
```

Only the listed hosts use the proxy; everything else stays direct. (When a
proxy injects its own TLS CA, the fetcher already sets `verify=False` /
`ignore_https_errors=True` for proxied hosts only.) Leave both unset if you are
not blocked.

---

## 8. Schedule the daily run

The droplet hardware clock is **UTC**; Indian AMCs operate IST. Put `TZ=` at the
**top** of the crontab or every schedule drifts 5.5 hours.

```bash
crontab -e
```
```cron
TZ=Asia/Kolkata
# 20:00 IST daily. bin/run.sh cd's to the project, loads .env, logs to
# logs/cron-<date>.log. Edit PROJECT_DIR in bin/run.sh if not /opt/mf-flow.
0 20 * * * /opt/mf-flow/bin/run.sh
```

Confirm the wrapper is executable: `chmod +x /opt/mf-flow/bin/run.sh`.

---

## 9. Operate — how to know a run worked

Every run writes, under the project:

- `logs/cron-YYYY-MM-DD.log` — full stdout/stderr of the cron run.
- `reports/run-YYYY-MM-DD.xlsx` — one row per AMC: outcome, files placed, error.
- `reports/master-log.csv` — **append-only** across all runs. This is your
  monitoring surface.

Quick health checks:

```bash
# Did today's run finish cleanly? Look for the summary line:
grep "run finished" logs/cron-$(date +%F).log
#   -> "44 MFs — OK=… skipped=… no_data_yet=… error=0"   (error=0 is the goal)

# What changed in the last run (one row per AMC)?
tail -n 50 reports/master-log.csv
```

Process exit code: `0` = no errors, `1` = at least one AMC errored. `change_type`
values in the CSVs: `FIRST_RUN`, `NEW_MONTH`, `UNCHANGED`, `REFRESH`, `NO_DATA`,
`ERROR` (see README "Incremental tracking").

Useful flags (all forwarded through `bin/run.sh`):

```bash
/opt/mf-flow/bin/run.sh --dry-run        # discover only
/opt/mf-flow/bin/run.sh --only mf23      # single AMC by id
/opt/mf-flow/bin/run.sh --skip mf13      # skip an AMC
/opt/mf-flow/bin/run.sh --force          # re-download even if on disk
```

---

## 10. Maintenance — when one AMC breaks

Scraping 44 independent websites means **the expected failure mode is: one AMC
redesigns its page or renames its files, and that one scraper mispicks or
errors.** The other 43 keep working. This is normal operations, not a defect.

When the report shows `ERROR` (or a stale month) for `mfNN`:

1. **Re-probe the live site** to see what changed:
   ```bash
   ./.venv/bin/python tools/probe_amc.py --only mfNN
   ```
2. Open `scrapers/mfNN_*.py` and `scrapers/LEARNINGS.md` (it lists each AMC's
   mechanism + selectors + "if it breaks, check" hints).
3. Adjust the scraper, **update/add a fixture test** under `tests/fixtures/mfNN/`
   so the regression can't return silently, and run `pytest tests/`.

Design note for whoever maintains this: the scrapers deliberately key on the
**most stable signal** (the human-readable date/title shown on the page), not on
fragile filename tokens, because AMCs change file-naming without notice. Keep
that principle when editing — match on dates/titles, normalize separators, and
never hard-code a month.

---

## 11. Known limitations / out of scope

- **Source-side data changes are not failures of this code.** Example seen on
  2026-06-15: Motilal Oswal *removed* a May file it had published days earlier
  (the old URL began 404-ing) and re-published it later at a new URL. The
  scraper reflects whatever the AMC currently serves. If an AMC pulls or delays
  a month, the run reports `NO_DATA`/older month until the AMC re-posts it.
- **Out of scope by design (not scraped):**
  - **Bandhan (mf07)** — portfolio behind an authenticated WordPress CMS.
  - **Angel One (mf04)** — publishes only a factsheet PDF, no monthly portfolio.
  Both are dropped from the registry (`lib/config.MF_TARGETS`); their xlsx rows
  are skipped harmlessly.
- **No locking.** Don't schedule overlapping runs of the full pass; a daily cron
  with a ~15 min runtime is well clear.
- **Input xlsx must be readable** at run time. On Windows dev boxes, OneDrive/Excel
  can briefly lock it (`PermissionError`); on the droplet keep a static copy.

---

## 12. Acceptance checklist (sign-off)

- [ ] `pytest tests/` → **168 passed**
- [ ] `--dry-run` → **44 MFs, error=0** from the droplet IP (proxy configured if needed)
- [ ] `env -i … run_scraper.py --dry-run` succeeds (cron-empty-env proven)
- [ ] One real `--only mfNN` download lands a file under `output/`
- [ ] Cron line installed with `TZ=Asia/Kolkata`; `bin/run.sh` executable and `PROJECT_DIR` correct
- [ ] `.env` present, `chmod 600`, `INPUT_XLSX`/`OUTPUT_ROOT` set; input xlsx in place
- [ ] After first scheduled run: `reports/master-log.csv` populated, `error=0`
