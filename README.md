# MF Flow scraper

Daily scraper for Indian mutual fund monthly portfolio disclosures. Reads the
MF list from `C:\Users\aayus\OneDrive\Desktop\MF Flow (08062026).xlsx` (or
`INPUT_XLSX` env var) and downloads each AMC's latest available monthly
portfolio into `output/<MF Name>/<Month YYYY>/`.

**Current coverage**: 44 active AMCs (mf01–mf46 minus mf07 Bandhan and mf04
Angel One). Verified end-to-end on 2026-06-15 via a clean-disk cold run: all 44
discover + download the latest month cleanly with 0 errors, all user-listed
schemes match (no name-matching gaps). See
[`scrapers/LEARNINGS.md`](scrapers/LEARNINGS.md) for per-AMC notes on
mechanics, anti-bot tricks, and "if it breaks, check" hints.

Folder names on disk come from [`lib.config._CANONICAL_NAME`](lib/config.py),
NOT verbatim from the xlsx. After updating canonical names, run
`tools/migrate_output_names.py` to rename existing folders. To re-probe new
AMC URLs (e.g. when an AMC redesigns its site), run
`tools/probe_amc.py --only mfNN`.

## Setup

Python deps (requires Python 3.12+):

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

Node.js deps (required ONLY for mf13 Edelweiss — see `package.json`):

```powershell
# Install Node.js 18+ from nodejs.org, then:
cd "C:\DEV\MF Flow"
npm install
```

If Node is missing, all other 44 scrapers still work; only Edelweiss raises a
clear `ScraperError` naming the missing dependency. Verify with:

```powershell
node --version    # >= 18
.venv\Scripts\python.exe -m pytest tests/
```

## Run

```
.venv\Scripts\python.exe run_scraper.py             # full run, all 44 MFs
.venv\Scripts\python.exe run_scraper.py --only mf16 # single MF
.venv\Scripts\python.exe run_scraper.py --dry-run   # discover only, no downloads
.venv\Scripts\python.exe run_scraper.py --force     # redownload even if on disk
.venv\Scripts\python.exe run_scraper.py --skip mf13 # skip specific MFs
```

The runner is idempotent — anything already on disk with the latest month
reports `skipped, already have` and is left alone.

## Environment

Optional `.env` (or shell env vars):

| Var | Default | Purpose |
|---|---|---|
| `INPUT_XLSX` | `C:\Users\aayus\OneDrive\Desktop\MF Flow (08062026).xlsx` | Source MF list |
| `OUTPUT_ROOT` | `<project>\output` | Where files land |
| `MF_FLOW_PROXY` | (unset) | HTTP/HTTPS/SOCKS5 proxy URL for IP-blocked sites |
| `MF_FLOW_PROXY_HOSTS` | (unset = all hosts) | Comma-separated host suffixes that route through proxy |

**Cron-time safety**: `lib/paths.py` loads `.env` at module-import via
`python-dotenv` so the scraper works under an empty cron environment. Verified
with `env -i .venv/Scripts/python.exe run_scraper.py --dry-run`.

## Tools

| Tool | Purpose |
|---|---|
| `tools/probe_amc.py` | One-shot live DOM probe per AMC. Classifies mechanism + recommends pattern. Run when adding a new AMC or when an existing one redesigns. `--only mfNN` for single, `--all` for all 44. |
| `tools/migrate_output_names.py` | One-shot rename of existing `output/<old-name>/` folders to current `_CANONICAL_NAME`. Run after editing the canonical map. Idempotent. |

Probe outputs land in `tools/probe_out/<mf_id>.json` plus an INDEX.md.

## Site coverage

All 44 active MFs work end-to-end as of 2026-06-15. Patterns vary by AMC —
see `scrapers/LEARNINGS.md` and `memory/amc_spa_patterns.md` (Bootstrap
pagination walk, Strapi REST, WP REST, ASP.NET `submit_event` AJAX, Akamai
+ Node-subprocess crypto).

**Works direct from both Windows and DigitalOcean droplet** (~38 AMCs).

**Works from droplet via URL construction** (page is IP-blocked but CDN is open):
- Bajaj — `media.bajajamc.com/.../Bajaj-Finserv-Mutual-Fund_Monthly-Portfolio-as-on-<DD>-<Mon3>-<YYYY>.xlsx`
- Canara Robeco — `www.canararobeco.com/wp-content/uploads/<yyyy>/<mm>/<CODE>-%E2%80%93-Canara-Robeco-<Scheme-Name>-%E2%80%93-<Month>-<Year>.xlsx`
- HDFC — `files.hdfcfund.com/s3fs-public/<yyyy>-<mm_pub>/Monthly%20<Scheme>%20-%20<DD>%20<Month>%20<yyyy>.xlsx`
- ICICI Prudential — `www.icicipruamc.com/blob/downloads/Files/Monthly%20Portfolio%20Disclosures/<yyyy>/<MonShort>/Monthly-Portfolio-Disclosure-<Month>-<yyyy>.zip`

**Needs `MF_FLOW_PROXY` on droplet** (Cloudflare 403 on DO ASN):
- **DSP** — page + CDN both blocked, no URL-construction fallback (random IDs).
- **HDFC** — file CDN blocks DO IPs; URLs construct fine but the GET needs a non-blocked IP.

**Special-mechanism AMCs**:
- **Edelweiss (mf13)** — SPA hits an Akamai-protected encrypted POST endpoint. Uses `curl_cffi` (TLS fingerprint bypass) + Node.js subprocess running `hybrid-crypto-js` for RSA-OAEP envelope. See `memory/edelweiss_encrypted_api.md`.
- **Kotak (mf23)** — site delivers JSON via `getsubheaderList/417`; file CDN is `vatseelabs-s3.kotakmf.com` (NOT `www.kotakmf.com`).
- **Quant (mf34)** — ASP.NET page where xlsx links only render after invoking inline JS `submit_event1` + `submit_event2`. Scraper calls these via `page.evaluate`.
- **WhiteOak (mf46)** — Next.js frontend backed by Strapi CMS at `cms.whiteoakamc.com/api/scheme-portfolios`. Pure REST, no Playwright.
- **Mirae (mf26)** — Bootstrap pagination over ~40 pages; scraper walks them all via repeated "Next" clicks.

**Dropped from registry**:
- **Bandhan** (mf07) — the portfolio listing comes from a WordPress CMS
  (`cmsnew.bandhanmutual.com`) whose REST API requires authentication. Headless
  scraping won't work without credentials.
- **Angel One** (mf04) — publishes only a factsheet PDF, no monthly scheme
  portfolio disclosure, so it is out of scope for this scraper.

Both scraper files (`scrapers/mf07_bandhan.py`, `scrapers/mf04_angel_one.py`)
are left on disk for reference; their registry entries in
`lib/config.MF_TARGETS` / `_CANONICAL_NAME` are removed so the runner skips
them (logged as "in xlsx but excluded from MF_TARGETS"). The source xlsx may
still list them — that is harmless.

### Proxy examples

```
# Route only blocked-site requests through a residential proxy (recommended)
set MF_FLOW_PROXY=http://user:pass@residential-proxy.example.com:7777
set MF_FLOW_PROXY_HOSTS=dspim.com,hdfcfund.com,files.hdfcfund.com

# Route everything through the proxy (debugging only)
set MF_FLOW_PROXY=http://localhost:8888
```

## Tests

```
.venv\Scripts\python.exe -m pytest tests/        # 168 tests, ~1s
```

Two layers:
- **Wiring tests** (`test_config_load.py`, `test_scraper_modules_import.py`) — confirm all 44 modules import and the config is consistent.
- **Per-scraper parse fixtures** (`test_mf<NN>_parse.py` + `tests/fixtures/mf<NN>/`) — feed captured live data through each scraper's pure parser. Catches DOM regressions before a live run burns Playwright minutes.

## Output layout

```
output/
  <Canonical MF Name>/
    <Month YYYY>/
      <Scheme or MF>.xlsx
      ...
      _meta.json                       # {as_on_date, downloaded_at_utc, source_url, ...}

logs/
  run-YYYY-MM-DD.log
  cron-YYYY-MM-DD.log                  # only on droplet, written by bin/run.sh

reports/
  run-YYYY-MM-DD.xlsx                  # one row per MF: status, files placed, errors
  run-YYYY-MM-DD-incremental.csv       # per-run change snapshot (NEW_MONTH / UNCHANGED / etc.)
  master-log.csv                       # APPEND-ONLY across all runs, same columns
```

### Incremental tracking

Every run writes two CSVs in addition to the run xlsx. The `change_type` column
captures what happened to each MF compared to its previous state on disk:

| change_type   | Meaning |
|---|---|
| `FIRST_RUN`   | No month was on disk; downloaded for the first time |
| `NEW_MONTH`   | Site has a newer month than on-disk; the new one was downloaded |
| `UNCHANGED`   | On-disk already had the latest available month; nothing fetched |
| `REFRESH`     | `--force` re-downloaded the same month |
| `NO_DATA`     | Site shows no portfolio data at all |
| `ERROR`       | Scrape failed (see `error` column for the message) |

To answer "what changed since last time?" — `tail -n 50 reports/master-log.csv`
on the droplet (one row per MF, 44 active MFs).

## Droplet deployment

Already deployed at `/opt/mf-flow/` on `equity@168.144.118.98`:

| Path | Purpose |
|---|---|
| `/opt/mf-flow/.venv` | Python 3.12 venv, isolated from equity-engine |
| `/opt/mf-flow/.env` | Droplet config — proxy URL + host filter (file mode 600) |
| `/opt/mf-flow/input.xlsx` | Canonical MF list (scp from `OneDrive\Desktop\MF Flow (08062026).xlsx`) |
| `/opt/mf-flow/bin/run.sh` | Cron-safe wrapper (loads .env, writes `logs/cron-<date>.log`) |
| `/opt/mf-flow/node_modules/` | Node deps for Edelweiss (`npm install` once) |
| `/opt/mf-flow/output/` | Downloaded portfolios |
| `/opt/mf-flow/reports/` | Per-run xlsx + incremental.csv + master-log.csv |

The droplet `.env` routes ONLY `dspim.com` and `hdfcfund.com` traffic through
the Bright Data residential proxy (shared with `equity-engine`). The remaining
AMCs go direct, so most of the run doesn't touch the proxy. Bright Data
injects its own CA into the TLS chain (SSL inspection), so requests through
the proxy have `verify=False` (Playwright: `ignore_https_errors=True`) — only
applied for hosts in `MF_FLOW_PROXY_HOSTS`.

### One-time droplet setup (for Edelweiss)

```
ssh equity@168.144.118.98
# Install Node.js 18+ if not present
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
cd /opt/mf-flow
npm install                          # installs hybrid-crypto-js into ./node_modules
node --version                       # confirm >= v18
```

### Enabling the cron (NOT auto-installed)

When you want the daily run, append to `equity@168.144.118.98`'s crontab:

```
TZ=Asia/Kolkata
0 20 * * * /opt/mf-flow/bin/run.sh
```

`TZ=Asia/Kolkata` must be at the top of the crontab — the droplet hardware is
UTC. Without it, `0 20` = 20:00 UTC = 01:30 IST.

### Manual droplet runs

```
ssh equity@168.144.118.98
/opt/mf-flow/bin/run.sh --only mf16          # one MF
/opt/mf-flow/bin/run.sh                      # full pass
/opt/mf-flow/bin/run.sh --dry-run            # discover only
```

### Sync code changes Windows → droplet

```
cd "C:\DEV\MF Flow"
tar -czf $env:TEMP\mf-flow.tar.gz --exclude='.venv' --exclude='output' `
    --exclude='logs' --exclude='reports' --exclude='__pycache__' `
    --exclude='.pytest_cache' --exclude='node_modules' --exclude='tools/probe_out' `
    lib scrapers tests tools run_scraper.py requirements.txt package.json `
    package-lock.json README.md bin
scp -i $env:USERPROFILE\.ssh\id_ed25519 $env:TEMP\mf-flow.tar.gz `
    equity@168.144.118.98:/tmp/
ssh -i $env:USERPROFILE\.ssh\id_ed25519 equity@168.144.118.98 `
    "cd /opt/mf-flow && tar -xzf /tmp/mf-flow.tar.gz && find . -name __pycache__ -exec rm -rf {} +"
# If you changed package.json, also: ssh ... 'cd /opt/mf-flow && npm install'
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Edelweiss: Node.js not found on PATH` | Node missing on droplet | `apt-get install -y nodejs` |
| `Edelweiss: hybrid-crypto-js npm package not installed` | npm install never ran | `cd /opt/mf-flow && npm install` |
| `HTTP 403` from DSP/HDFC on droplet | Cloudflare blocking DO ASN | set `MF_FLOW_PROXY` |
| `Page.select_option: Timeout` | AMC SPA changed selectors | re-run `tools/probe_amc.py --only mfNN`, update scraper |
| `0/N schemes matched` | xlsx scheme names drifted from AMC site labels | check `lib/scheme_filter.py` compound rules, or override in the per-MF scraper |
| `no data yet` for an AMC | site genuinely hasn't published this month | wait, runner will auto-pick it up next run |

## Architecture

```
run_scraper.py                # iterates load_mfs(), two-phase discover+download
  └─ lib/config.py            # parses xlsx → MFConfig; canonical names; registry
  └─ lib/fetcher.py           # Static (requests) + Browser (Playwright+stealth) engines, proxy plumbing
  └─ lib/organizer.py         # idempotent place_file + _meta.json
  └─ lib/incremental_report.py # per-run CSV + master-log append
  └─ scrapers/base.py         # BaseScraper contract + retry decorator
  └─ scrapers/patterns/       # SingleXlsxScraper / PerSchemeXlsxScraper / LatestMonthZipScraper / etc + static_links_filter helper
  └─ scrapers/mfNN_*.py       # one per AMC; subclass a pattern + override 2-3 hooks
```

See `scrapers/LEARNINGS.md` for a per-AMC index of mechanism + selectors +
recovery hints.
