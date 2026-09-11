# MF Flow scraper learnings

Per-AMC notes on site mechanics, anti-bot tricks, and "if it breaks, check"
hints. Update this file alongside any scraper change.

## Pattern recipes

| Recipe | When to use | Canonical example |
|---|---|---|
| `SingleXlsxScraper` | One multi-sheet xlsx per month, all schemes inside | [mf20_iti.py](mf20_iti.py) |
| `PerSchemeXlsxScraper` | One xlsx per scheme per month | [mf22_jm_financial.py](mf22_jm_financial.py) |
| `LatestMonthZipScraper` | Monthly archive zipped, expand to per-scheme files | [mf18_icici_pru.py](mf18_icici_pru.py) |
| `FactsheetOnlyScraper` | No portfolio xlsx, just monthly factsheet PDF | [mf04_angel_one.py](mf04_angel_one.py) |
| `ToggleUntilDataScraper` | Month dropdown where the most recent month may be empty | [mf21_jio_blackrock.py](mf21_jio_blackrock.py) |
| `static_links_filter` helper | Any site that renders all portfolios as flat `<a href>` list | [patterns/static_links_filter.py](patterns/static_links_filter.py) |

### Akamai / Cloudflare bypass recipe

Sites that fail Playwright with 403 but render in real Chrome use
fingerprint-sensitive bot detection. Use `curl_cffi` with `chrome131`
impersonation — see [mf13_edelweiss.py](mf13_edelweiss.py).

If the SPA hits an encrypted JS API, derive keys from `main.js`:
grep for `defaultAesKey` and `encryption:{secreat:...}`.
If the SPA uses hybrid-crypto-js for POST body encryption (VAPT mode),
shell out to Node.js with `npm:hybrid-crypto-js` rather than porting
node-forge RSA-OAEP to Python (fingerprint computation differs).

### IP-block recipe

Several CDNs (DSP, HDFC `files.hdfcfund.com`) IP-block DigitalOcean ASN.
Set `MF_FLOW_PROXY` env var (Bright Data residential works) and route only
the blocked hosts via `MF_FLOW_PROXY_HOSTS=files.hdfcfund.com,dspim.com`.

---

## Per-AMC notes

Template:

```
## mfNN — <Canonical Name>

- **URL**: ...
- **Mechanism**: static_links | spa_click | xhr_api | akamai | pdf_only | custom
- **Pattern**: single_xlsx | per_scheme | zip | factsheet | toggle | custom
- **Key DOM hooks**: ...
- **Anti-bot tricks**: none | playwright_stealth | curl_cffi(chrome131) | proxy
- **As-of date**: YYYY-MM-DD (last verified)
- **If it breaks, check**: one-line hint
```

### mf01 — 360 ONE Mutual Fund
- **URL**: https://www.360.one/asset/mutual-funds/downloads/
- **Mechanism**: spa_click
- **Pattern**: single_xlsx_multi_sheet
- **As-of date**: 2026-06-03
- **If it breaks, check**: Disclosures tab → Monthly Portfolio toggle, then the "Download" anchor on the latest row.

### mf02 — Abakkus Mutual Fund
- **URL**: https://www.abakkusmf.com/statutory-disclosures.html
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **As-of date**: 2026-06-03

### mf03 — Aditya Birla Sun Life Mutual Fund
- **URL**: https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio
- **Mechanism**: static_links
- **Pattern**: latest_month_zip
- **As-of date**: 2026-06-03

### mf04 — Angel One Mutual Fund
- **URL**: https://www.angelonemf.com/downloads
- **Mechanism**: static_links (CDN URL construction works direct from droplet)
- **Pattern**: factsheet_only (NIL schemes in xlsx)
- **Anti-bot tricks**: page is IP-blocked from droplet, but
  `cms.angelonemf.com/.../Factsheet-Angel-One-Mutual-Fund-Schemes-<Mon3>-<YYYY>.pdf`
  is open. Hardcode URL construction in scraper.
- **As-of date**: 2026-06-03
- **If it breaks, check**: filename format on `cms.angelonemf.com` — they sometimes
  add `-1` / `-Final` suffixes.

### mf05 — Axis Mutual Fund
- **URL**: https://transact.axismf.com/statutory-disclosures
- **Mechanism**: cms_api (direct JSON endpoint; see detailed entry below)
- **Pattern**: single_xlsx_multi_sheet
- **Anti-bot tricks**: previously hosted at `www.axismf.com`; route moved
  2026-06 to `transact.axismf.com`. No captcha on the CMS API.
- **As-of date**: 2026-06-08
- **If it breaks, check**: the route is now a separate transact host; old
  scrapers pointed at `www.axismf.com` will 404.

### mf06 — Bajaj Finserv Mutual Fund
- **URL**: https://www.bajajamc.com/downloads?portfolio=
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **Anti-bot tricks**: page blocked from droplet; CDN URL
  `media.bajajamc.com/.../Bajaj-Finserv-Mutual-Fund_Monthly-Portfolio-as-on-<DD>-<Mon3>-<YYYY>.xlsx`
  is open — construct URL.
- **As-of date**: 2026-06-03

### mf08 — Bank of India Mutual Fund
- **URL**: https://www.boimf.in/investor-corner#t2
- **Mechanism**: spa_click
- **Pattern**: single_xlsx_multi_sheet
- **As-of date**: 2026-06-03

### mf09 — Baroda BNP Paribas Mutual Fund
- **URL**: https://www.barodabnpparibasmf.in/downloads/monthly-portfolio-scheme
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **As-of date**: 2026-06-03

### mf10 — Canara Robeco Mutual Fund
- **URL**: https://www.canararobeco.com/documents/statutory-disclosures/scheme-dashboard/scheme-monthly-portfolio/
- **Mechanism**: static_links + URL construction fallback (works from droplet)
- **Pattern**: per_scheme_xlsx
- **As-of date**: 2026-06-03
- **If it breaks, check**: URL template
  `www.canararobeco.com/wp-content/uploads/<yyyy>/<mm>/<CODE>-%E2%80%93-Canara-Robeco-<Scheme-Name>-%E2%80%93-<Month>-<Year>.xlsx`
  uses URL-encoded em-dashes (%E2%80%93).

### mf11 — Capital Mind Mutual Fund
- **URL**: https://capitalmindmf.com/statutory-disclosures.html
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet (1 scheme — treated as single file)
- **As-of date**: 2026-06-03

### mf12 — DSP Mutual Fund
- **URL**: https://www.dspim.com/mandatory-disclosures/portfolio-disclosures
- **Mechanism**: spa_click
- **Pattern**: latest_month_zip
- **Anti-bot tricks**: page + CDN both Cloudflare 403 from DO ASN.
  Random-ID in URL = no construction fallback. Needs `MF_FLOW_PROXY` on droplet.
- **As-of date**: 2026-06-03
- **If it breaks, check**: residential proxy still valid; CF rules change quarterly.

### mf13 — Edelweiss Mutual Fund
- **URL**: https://www.edelweissmf.com/statutory/portfolio-of-schemes
- **Mechanism**: xhr_api (encrypted POST via hybrid-crypto-js + AES response decrypt)
- **Pattern**: single_xlsx_multi_sheet
- **Anti-bot tricks**: Akamai blocks both `requests` and Playwright. Uses
  `curl_cffi` with `chrome131` impersonation. POST request bodies encrypted
  with hybrid-crypto-js (RSA-OAEP 4096-bit + AES-256-CBC), delegated to
  Node.js subprocess. Response `body` is CryptoJS AES envelope decrypted with
  `HmacSHA256(secreat + ip + ts, hashKey).hex()`.
- **Status**: FIXED
- **As-of date**: 2026-06-09
- **Dependencies**: `curl_cffi`, `pycryptodome`, Node.js + `npm:hybrid-crypto-js`
- **How it works**: Edelweiss enabled VAPT mode (`vapt:!0` in main.js),
  requiring POST bodies to be encrypted with hybrid-crypto-js. Porting
  node-forge's RSA-OAEP to Python failed (fingerprint mismatch), so the
  scraper shells out to Node.js with the actual `hybrid-crypto-js` npm
  package to produce the encrypted envelope. The RSA public key is extracted
  from main.js at runtime.
  Flow: curl_cffi warms Akamai cookies -> extract PEM from main.js ->
  POST third-party/getSingleStatutory (body encrypted via Node.js) ->
  decrypt AES response -> parse CommonDetails -> download xlsx.
- **Keys**: SECREAT and HASHKEY unchanged as of 2026-06-09
  (`encryption:{secreat:"5b6714...",hashKey:"r4vcos..."}` still in main.js).
- **If it breaks, check**:
  1. SECREAT/HASHKEY rotated: grep main.js for `encryption:{secreat:`.
  2. RSA key rotated: auto-handled (extracted at runtime from main.js).
  3. hybrid-crypto-js removed/replaced: check main.js for new encryption lib.
  4. Node.js not available: install Node.js + `npm install hybrid-crypto-js`.
- **main.js hash**: `main.8299cb7033e9e3e9.js` (as of 2026-06-09)

### mf16 — HDFC Mutual Fund
- **URL**: https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio
- **Mechanism**: static_links + URL construction fallback
- **Pattern**: per_scheme_xlsx
- **Anti-bot tricks**: `files.hdfcfund.com` IP-blocks DO ASN. Construct URL
  pattern `s3fs-public/<yyyy>-<mm_pub>/Monthly%20<Scheme>%20-%20<DD>%20<Month>%20<yyyy>.xlsx`
  with HEAD-probe backwards in time. Needs proxy on droplet.
- **As-of date**: 2026-06-03
- **If it breaks, check**: scheme canonical casing — HDFC uses "Mid Cap" not
  "Midcap" in URLs (scheme_filter handles this).

### mf18 — ICICI Prudential Mutual Fund
- **URL**: https://www.icicipruamc.com/media-center/downloads?currentTabFilter=Disclosures&...
- **Mechanism**: static_links + URL construction fallback
- **Pattern**: latest_month_zip
- **As-of date**: 2026-06-03

---

The mf22..mf46 sections below are seeded from the 2026-06-08 probe; update
each as you verify against a live run.

### mf22 — JM Financial Mutual Fund (paginated — 2026-06-09)
**Pagination**: JM's disclosures page renders 5 entries per page via
`rc-pagination`. The scraper walks pages (`li.rc-pagination-next a`) until
every user-listed scheme has been seen at least once (capped at 15 pages
for safety). Combined with per-scheme-latest, each user scheme ends up at
its individual latest available month, placed in the corresponding month
folder.

If the scraper ever stops finding all your schemes, increase `max_pages`
in `_collect_paginated_hrefs` or sweep pages by financial year via the
year selector `select.data-selector`.


- **URL**: https://www.jmfinancialmf.com/downloads/Portfolio-Disclosure/Monthly-Portfolio-of-Schemes
- **Mechanism**: static_links
- **Pattern**: per_scheme_xlsx (via `static_links_filter`)
- **Key DOM hooks**: anchor href contains `/CMS/downloads/Portfolio%20Disclosure/Monthly%20Portfolio%20of%20Schemes/`; visible text is "View" so we promote the URL filename to label.
- **As-of date**: 2026-06-08
- **If it breaks, check**: CMS folder name unchanged; filename pattern `Monthly Portfolio - JM <Scheme> - <DD> <Month> <YYYY>.xlsx`.

### mf25 — Mahindra Manulife Mutual Fund
- **URL**: https://www.mahindramanulife.com/downloads
- **Mechanism**: static_links (4500+ xlsx; aggressive filter required)
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: filter to text containing both "monthly" + "portfolio" (include_either=False), exclude fortnightly/factsheet/commission/SID/KIM.
- **As-of date**: 2026-06-08

### mf27 — Motilal Oswal Mutual Fund
- **URL**: https://www.motilaloswalmf.com/downloads/scheme-portfolio-details
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: link text is empty — filter on href. Accept URLs containing `portfolioholding` or `scheme-portfolio-details`. Exclude `forthnightly` / `fortnightly` / `factsheet`.
- **As-of date**: 2026-06-08
- **If it breaks, check**: filename pattern `PortfolioHolding_<Month>%20<DD>,%20<YYYY>.xlsx`.

### mf33 — Parag Parikh Mutual Fund
- **URL**: https://amc.ppfas.com/downloads/portfolio-disclosure/
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: custom_filter requires link text `== "Consolidated"`. Files are `.xls` (CFB), not `.xlsx`. The base scraper detects .xls extension and skips signature check.
- **As-of date**: 2026-06-08

### mf35 — Quantum Mutual Fund
- **URL**: https://www.quantumamc.com/portfolio/combined/-1/1/0/0
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: include_terms=("all funds",). All listed xlsx are "All Funds" consolidated.
- **As-of date**: 2026-06-08

### mf37 — SBI Mutual Fund
- **URL**: https://www.sbimf.com/portfolios
- **Mechanism**: static_links (132 xlsx; per-scheme files plus consolidated)
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: include_terms=("all schemes", "monthly") with include_either=False. Exclude fortnightly/factsheet/commission/addendum/SID/KIM.
- **As-of date**: 2026-06-08

### mf05 — Axis Mutual Fund
- **URL**: https://transact.axismf.com/statutory-disclosures
- **Mechanism**: cms_api (direct JSON endpoint, no form interaction needed)
- **Pattern**: single_xlsx_multi_sheet
- **Confidence**: HIGH — live-verified 2026-06-08 (dry-run OK 2026-04).
- **API endpoint**: `GET /cms/api/statutory-disclosures-scheme?cat=Monthly%20Scheme%20Portfolios`
  Returns JSON array. Filter: `field_aboutus_scheme_code == "Consolidated"`,
  exclude weekly/daily/adhoc in `field_pdf_name_statutory`.
  Download URL: `https://transact.axismf.com{field_related_file}` (URL-decoded).
- **Anti-bot**: Angular SPA; browser engine fetches page so JS executes and JSON is available. No captcha.
- **As-of date**: 2026-06-08
- **If it breaks, check**: API path may change if CMS is upgraded. Verify
  `transact.axismf.com/cms/api/` still returns JSON. The old SPA click approach
  (year/month/consolidated dropdowns) is unreliable due to spinner overlays.

### mf23 — Kotak Mutual Fund
- **URL**: https://www.kotakmf.com/Information/forms-and-downloads
- **Mechanism**: xhr_api (direct API call via stealth browser context)
- **Pattern**: single_xlsx_multi_sheet
- **Confidence**: HIGH — live-verified 2026-06-09 (download OK 2026-04, as_on=2026-04-30).
- **API endpoint**: `GET /api/kotakapi/forms/user/getsubheaderList/417?option=51&pagination=1&pageSize=100&pageNumber=1`
  headerId 417 = Portfolios, optionId 51 = Consolidated & Fortnightly Portfolio.
  Returns JSON with `subHeaderList[]` items having `subHeaderTitle` and `content` (relative path).
  Filter: exclude "fortnightly" in title, keep "consolidated", parse month via regex.
- **Download**: Files are hosted on S3 at `vatseelabs-s3.kotakmf.com`, NOT on
  `www.kotakmf.com`. The SPA's Angular download handler fetches from the S3 host.
  Download URL: `https://vatseelabs-s3.kotakmf.com/{content}`.
  Plain `requests.get` works (no cookies/auth needed for S3). Using static fetcher.
- **Anti-bot**: Radware Bot Manager + hCaptcha on the API. Stealth browser context
  bypasses (disable webdriver, fake plugins/languages, chrome.runtime stub).
  S3 download has no bot protection.
- **As-of date**: 2026-06-09
- **If it breaks, check**: (1) S3 bucket hostname `vatseelabs-s3.kotakmf.com` may
  change — look for the download URL in browser DevTools Network tab when clicking
  a "Download" span on the SPA. (2) Radware may tighten fingerprinting on the API.
  (3) API param IDs (417, 51) may change if site restructures.

### mf24 — LIC Mutual Fund
- **URL**: https://www.licmf.com/downloads/monthly-portfolio
- **Mechanism**: spa_click + xhr_api (4-step cascading form for discovery, AJAX POST for download)
- **Pattern**: per_scheme_xlsx
- **Confidence**: HIGH — live-verified 2026-06-09 (download OK 2026-04, 7/9 schemes).
- **Key DOM hooks**: `select[name="fund_category"]`, `select[name="fund_name"]`,
  `select[name="year"]`, `select[name="month"]`, `button.monthly-submit-btn`.
  NOTE: selects have NO id= attributes, only name=. Do NOT use `#fund_category` etc.
- **Discovery AJAX**: `POST /downloads/portfolio-filter-options` with form params
  (`scheme_code=X&filter=fund_name&type=monthly_portfolio` for year cascade,
  `year=Y&filter=year&type=monthly_portfolio&scheme_code=X` for month cascade).
- **Download**: The submit button does NOT trigger a browser download event.
  jQuery posts to `POST /downloads/portfolio-files` with params
  `scheme_code=X&fund_name=&type=monthly_portfolio&month=M&year=Y`.
  Response is an HTML fragment containing
  `<a href="/assets/downloads/portfolio/monthly/YYYY/M/CODE-DD-MM-YYYY-HH:MM:SS.xlsx">`.
  We call this endpoint via `page.evaluate(fetch(...))` per scheme, extract the
  xlsx URL with regex, then download via browser engine (SSL cert requires
  Playwright; plain requests fails with CERTIFICATE_VERIFY_FAILED).
- **Cascade order**: category populates fund_name; fund_name populates year;
  year populates month. Year/month are EMPTY until a specific fund is selected.
- **As-of date**: 2026-06-09
- **If it breaks, check**: (1) the `/downloads/portfolio-files` endpoint or its
  response format may change. (2) Cascade order — year won't populate without
  fund selected first. (3) SSL cert chain — if their cert changes, the browser
  engine fallback may also fail.

### mf26 — Mirae Asset Mutual Fund
- **URL**: https://www.miraeassetmf.co.in/downloads/portfolio
- **Mechanism**: static_links with Bootstrap pagination (~40 pages, ~10 schemes each)
- **Pattern**: per_scheme_xlsx
- **Key DOM hooks**: `a.page-link` numbered + `aria-label*="Next"` for navigation; `li.page-item.active a.page-link` for current page. Scraper walks pages by clicking next until active page stops advancing. Link text format: "Portfolio Details as on 30th April 2026 for Mirae Asset Flexi Cap Fund". Exclude ETF/fortnightly/half-year.
- **As-of date**: 2026-06-09
- **If it breaks, check**: pagination structure (Bootstrap windowed numbers) — initial scan of `.page-link` only shows a slice. Must click-and-rescan until `active` page stops moving. Hard cap is 40 pages.

### mf28 — Navi Mutual Fund
- **URL**: https://navi.com/mutual-fund/downloads/portfolio
- **Mechanism**: xhr_api (WordPress REST API via Playwright page context)
- **Pattern**: per_scheme_xlsx
- **Confidence**: HIGH — live-verified 2026-06-08 (dry-run OK 2026-04, 17 items).
- **API endpoint**: `POST /wp-json/nv/v1/documents` with WP-NONCE header.
  Params: `category=884` (Monthly portfolio), `type=Monthly`, `order=DESC`,
  `financial_year=YYYY-YYYY` (Indian FY format, e.g. "2025-2026").
  Returns array of `{title, url}` objects. URLs on `public-assets.prod.navi-tech.in`.
- **Auth**: WP-NONCE from `window.navi_property.nonce` global. Must call API
  from within Playwright page context (direct requests get 403).
- **Title encoding**: HTML entities (`&#038;` for `&`) — use `html.unescape()`.
- **FY iteration**: Walk FYs backward, then months backward within each FY.
  April=start of FY. FY "2025-2026" covers Apr 2025 - Mar 2026.
- **As-of date**: 2026-06-08
- **If it breaks, check**: WP-NONCE auth; category ID 884 may change if site
  restructures. DOM `<select>` elements are CSS-hidden — do NOT try to interact
  with them via Playwright clicks.

### mf29 — Nippon India Mutual Fund
- **URL**: https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures
- **Mechanism**: static_links
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: link text is "Download"; filter on `MONTHLY-PORTFOLIO` in href. NOTE: default exclude_terms include "factsheet" but the URL path is `/FactsheetsDocuments/` — clear exclude_terms when constructing the filter for this AMC.
- **As-of date**: 2026-06-08

### mf30 — NJ Mutual Fund
- **URL**: https://downloads.njmutualfund.com/njmf_download.php?nme=127
- **Mechanism**: static_links
- **Pattern**: per_scheme_xlsx
- **Key DOM hooks**: link text "Monthly Portfolio - March 31, 2026 - NJ Flexi Cap Fund". User's scheme names use shortcodes (NJFCP, NJELSTCH) so `_entry_text()` extracts the shortcode from the href.
- **As-of date**: 2026-06-08

### mf31 — Old Bridge Mutual Fund
- **URL**: https://oldbridgemf.com/statutory-disclosures.html
- **Mechanism**: static_links (951 xlsx total; aggressive per-scheme filter)
- **Pattern**: per_scheme_xlsx
- **Key DOM hooks**: link text is "Download"; scheme name comes from URL filename (URL-decode then replace underscores with spaces). Custom filter requires "portfolio" in href.
- **As-of date**: 2026-06-08

### mf32 — PGIM India Mutual Fund
- **URL**: https://www.pgimindia.com/mutual-funds/disclosures/Portfolios/Monthly-Portfolio
- **Mechanism**: xhr_api (Equity tab = TabId 12)
- **Pattern**: per_scheme_xlsx (API-driven; no Playwright)
- **Confidence**: HIGH — live-verified 2026-06-08.
- **API endpoint**: `POST /api/v1/brochure/published/disclosure` with JSON body
  `{"sectionId": "SECTION_747960037"}`. NOTE: GET returns HTTP 405 — must use POST.
  The section endpoint (`/api/v1/brochure/disclosure/section`) still works with GET.
- **As-of date**: 2026-06-08
- **If it breaks, check**: API method — the disclosure endpoint requires POST, not GET.

### mf34 — Quant Mutual Fund
- **URL**: https://quantmutual.com/statutory-disclosures
- **Mechanism**: spa_click (ASP.NET jQuery AJAX — `submit_event1(year, cat)` loads months, `submit_event2(monthNum, cat, year)` loads scheme xlsx links)
- **Pattern**: per_scheme_xlsx
- **Confidence**: HIGH — live-verified 2026-06-09, 11/11 schemes matched, all xlsx downloaded.
- **Key DOM hooks**: Section heading `div.statutory.disclouser` with text "MONTHLY PORTFOLIO - FUND - WISE". Year tabs are `li.yearurl` in sibling `div.accord-opns.innerclss`. Month tabs loaded via AJAX into `div#"MONTHLY PORTFOLIO - FUND - WISE"` (id has spaces). File links loaded into `div#files`. AJAX endpoints: POST `/statutorydisclosures.aspx/displaydisclouser1` (years→months) and `/statutorydisclosures.aspx/displaydisclouser2` (months→files).
- **Anti-bot tricks**: none (standard Playwright stealth sufficient)
- **As-of date**: 2026-06-09
- **If it breaks, check**: (1) Verify `submit_event1`/`submit_event2` JS functions still exist (view page source). (2) Check if the AJAX endpoint paths changed. (3) The section category string "MONTHLY PORTFOLIO - FUND - WISE" is used as both a CSS selector target and a DOM element id — if the AMC renames it, update `SECTION_CAT` in the scraper. (4) URL path uses `/Admin/disclouser/` (AMC typo) — if they fix the typo, downloads will 404.

### mf36 — SAMCO Mutual Fund (2026-06-09 update: typo-fix bug)
**Bug fixed 2026-06-09**: `_fix_samco_typos` was rewriting the URL
`Apirl_2026` → `April_2026` BEFORE download. SAMCO uploaded the files under
the typo'd name; the "corrected" URL returned HTTP 500. Result was that
6 of 9 schemes silently failed download (no error in `STATUS`, just
`(3 files)` instead of `(9 files)`). The fix keeps the original href intact
for downloads — the typo normalization is only applied to a SEPARATE label
string used for month inference.


- **URL**: https://www.samcomf.com/StatutoryDisclosure
- **Mechanism**: static_links (5842 links; per-scheme + media1 mirror duplicates)
- **Pattern**: per_scheme_xlsx
- **Key DOM hooks**: filter to `MONTHLY_PORTFOLIO` URLs, dedupe `media1.samco.in` mirrors. Note SAMCO has typo handling (`Apirl` → `April`) and CamelCase URL names (`SamcoLargeCapFund`).
- **As-of date**: 2026-06-08

### mf38 — Shriram Mutual Fund
- **URL**: https://www.shriramamc.in/investor-statutory-disclosures
- **Mechanism**: static_links (19 xlsx; single per month)
- **Pattern**: single_xlsx (custom_filter on filename, NOT full URL — parent path contains "fortnightly"/"weekly" as category names)
- **As-of date**: 2026-06-08

### mf39 — Sundaram Mutual Fund
- **URL**: https://www.sundarammutual.com/Monthly-Fortnightly-Adhoc-Portfolios
- **Mechanism**: spa_click (AJAX-loaded Bootstrap accordion with form interaction)
- **Pattern**: single_xlsx_multi_sheet
- **Confidence**: HIGH — live-verified 2026-06-08 (dry-run OK 2026-04).
- **Steps**: (1) `select_option('#Cbx_Category', 'Monthly')`, (2) click View
  button via JS evaluate, (3) wait 8s for AJAX, (4) expand first accordion item
  via JS evaluate, (5) wait 3s, (6) collect links from `#MonthAdhoc` active tab-pane.
- **Link format**: `/uploaddir/MonthlyPortfolio/monthlyportfolio_DDMMYYHHMMSS.xlsx`
- **Filter**: `static_links_filter` with include=["monthly portfolio"], then
  equity/FoF filter (exclude Debt, Fortnightly).
- **As-of date**: 2026-06-08
- **If it breaks, check**: AJAX timeouts — the page is very slow. If accordion
  content is empty, increase the wait after clicking View (currently 8s).
  The `#Cbx_Category` select and View button IDs may change.

### mf40 — Tata Mutual Fund
- **URL**: https://www.advisorkhoj.com/form-download-centre/Mutual/Tata-Mutual-Fund/Monthly-Portfolio-Disclosures
- **Mechanism**: static_links (third-party advisorkhoj.com)
- **Pattern**: single_xlsx_multi_sheet
- **Key DOM hooks**: link text matches `Monthly Portfolio Disclosure - <Month> <Year>`. URL path contains publication-month (data-month+1) — parse from text only, not href.
- **As-of date**: 2026-06-08

### mf41 — Taurus Mutual Fund
- **URL**: https://taurusmutualfund.com/monthly-portfolio
- **Mechanism**: spa_click (Drupal "Better Exposed Filters" with AJAX reload)
- **Pattern**: per_scheme_xlsx
- **Confidence**: HIGH — live-verified 2026-06-08 (dry-run OK 2026-05, 8 xlsx links).
- **Key DOM hooks**: `select[name="field_monthly_portfolio_target_id"]` (year),
  `select[name="field_month_target_id"]` (month). MUST use name-based selectors
  because element IDs change after each Drupal AJAX reload. Select by label text
  (`select_option(label="2026")`), NOT by value (values are taxonomy IDs like 567, not years).
- **Iteration**: Select latest year, iterate months Dec->Jan, first with xlsx links wins.
- **Link text**: Scheme name only (no month); month inferred from URL by try_infer.
- **As-of date**: 2026-06-08
- **If it breaks, check**: Drupal taxonomy IDs for years/months may change. The
  `select_option(label=...)` approach is resilient to ID changes. If AJAX stops
  firing, check that the Drupal views module is still active.

### mf42 — Trust Mutual Fund
- **URL**: https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures
- **Mechanism**: xhr_api (React SPA with POST API via Playwright page context)
- **Pattern**: single_xlsx_multi_sheet
- **Confidence**: HIGH — live-verified 2026-06-08 (dry-run OK 2026-04).
- **API endpoint**: `POST /api/api/Trust/GetData` with JSON body:
  `{systemQueryFileName: "disclosuresweb.xml", tagName: "GetDisclosureByType",
  sortField: "uploaddate", sortDirection: "DESC",
  replaceField: "_slug_", replaceValue: "portfolio-fortnightly-disclosure,portfolio-monthly-disclosure,..."}`.
  NOTE: GET returns empty body — must use POST with correct JSON body.
- **Response**: `{resultSetArray: [{title, fileurl, matching_slugs, uploaddate, ...}]}`.
  Filter: `matching_slugs` contains "portfolio-monthly-disclosure".
  182 total items, ~63 monthly. Date in title as "DD.MM.YYYY" (e.g. "30.04.2026").
- **As-of date**: 2026-06-08
- **If it breaks, check**: API method must be POST not GET. The `replaceValue`
  slug list may change if Trust adds new disclosure types. The `resultSetArray`
  key in the response must contain the items array.

### mf43 — Unifi Mutual Fund
- **URL**: https://unifimf.com/statutorydocuments/
- **Mechanism**: static_links (158 xlsx; one scheme)
- **Pattern**: per_scheme_xlsx (single scheme: Unifi Flexi Cap Fund)
- **Key DOM hooks**: filter on "flexi" + "cap" in href; page text is just "April 2026" so scheme name extracted from URL filename.
- **As-of date**: 2026-06-08

### mf44 — UTI Mutual Fund
- **URL**: https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure
- **Mechanism**: xhr_api (direct REST API via Playwright page context)
- **Pattern**: latest_month_zip
- **Confidence**: HIGH — live-verified 2026-06-08 (dry-run OK 2026-05).
- **API endpoint**: `GET /api/get-consolidate-portfolio-disclosure?year=YYYY&month=MonthName`
  (e.g. `?year=2026&month=May`). Returns `{rows: [{url, name, type, month, year}]}`.
  Zip files hosted on CloudFront CDN (`d3ce1o48hc5oli.cloudfront.net`).
- **Month iteration**: Walk months backward from current to find latest with data.
  Angular SPA's custom dropdown components are unnecessary — API is called directly.
- **URL format**: `https://d3ce1o48hc5oli.cloudfront.net/s3fs-public/YYYY-MM/fw_uti_mf_scheme_portfolios_DD.MM.YYYY_N.zip`
- **As-of date**: 2026-06-08
- **If it breaks, check**: API path or parameter names. The Angular SPA may
  change the API contract. Month names are English full names (January, February, etc.).

### mf45 — The Wealth Company Mutual Fund
- **URL**: https://www.wealthcompanyamc.in/literature-forms/portfolio-documents/monthly/
- **Mechanism**: spa_click (Next.js + MUI; `/monthly/` pre-selected)
- **Pattern**: per_scheme_xlsx
- **Confidence**: MEDIUM — visible text patterns confirmed, download button selectors best-guess.
- **As-of date**: 2026-06-08

### mf46 — WhiteOak Capital Mutual Fund (per-scheme-latest — 2026-06-09)
**Per-scheme-latest**: WhiteOak publishes per-scheme portfolios on a rolling
basis (e.g. May 2026 for Mid Cap ships a week before May 2026 for Flexi
Cap). The scraper picks each user scheme's individual latest available month
via `parse_api_entries` (groups by normalized scheme key, takes latest
month per scheme). Each file is placed in its OWN month folder via
`DownloadedFile.year/month` overrides. Result: May folder has only schemes
with May data; April folder still holds the rest.


- **URL**: https://mf.whiteoakamc.com/regulatory-disclosures/scheme-portfolios
- **Mechanism**: static_api (Strapi REST API at `cms.whiteoakamc.com/api/scheme-portfolios`)
- **Pattern**: per_scheme_xlsx
- **Confidence**: HIGH — live-tested against real API, 8/8 schemes matched, April 2026.
- **Note**: The SPA front-end uses a Strapi CMS backend. API supports `filters[period][$eq]=Monthly`,
  `sort[0]=published_date:desc`, and `populate=*` to get direct S3 xlsx URLs on `content.whiteoakamc.com`.
  No Playwright needed. File URL hashes (e.g. `_09eb8c14a2.xlsx`) can trick `try_infer` into false
  month matches, so month inference uses `doc_name` only (not file URLs).
- **As-of date**: 2026-06-09

---

## Maintenance log — fixes applied 2026-09-12 (originally built July/August 2026)

- **mf06 Bajaj Finserv** — from June 2026 the consolidated file is uploaded as
  `.xls` (still OOXML) at the same constructed CDN URL. Scraper now probes
  `.xlsx` then `.xls` per month. Diagnostic: WP media REST
  `bajajamc.com/wp-json/wp/v2/media?search=...` via curl_cffi shows the exact
  latest upload URL.
- **mf18 ICICI Prudential** — from June 2026 the blob month folder uses the full
  month name (`/2026/June/`), earlier months use 3 letters (`/2026/May/`).
  Scraper now probes both spellings per month.
- **mf31 Old Bridge** — from June 2026 monthly files have opaque names
  (`OBFE_*.xlsx` Focused, `OBFX_*` Flexi Cap, `OBAF_*` Arbitrage). Scraper now
  reads month + scheme from the row `aria-label` inside the "Monthly Portfolio"
  tab pane. Arbitrage Fund is not in the scope xlsx.
- **mf13 Edelweiss** — the encrypted POST `third-party/getSingleStatutory` froze
  ~2026-07-07. Live site now calls
  `GET mf/statutory-menus/single?type=Statutory&fundType=MF&menuName=Portfolio of scheme(s)`
  (plain query params, no RSA / Node). Response is the same CryptoJS AES envelope
  (`{"body": ...}`) decrypted with the HMAC passphrase from the
  `x-timestamp`/`x-ip-address` headers; decrypted JSON is
  `{"submenus": [...], "files": [{month, year, fileTitle, filePath, subMenuName}]}`
  (lowercase keys). Filter `subMenuName == "Monthly Portfolio and Risk-o-Meter"`,
  download `FILES_BASE + quoted filePath`. Old POST path kept as fallback only.
- **Runner / lib** — universal month-plausibility guard (`lib/month_guard.py`,
  applied in `run_scraper.py`), mf02 Abakkus scoped to `div#mpdOutput`, and
  `lib/month_hint.py` letter-boundary fix (Capital Mind upload-hash misparse).
  `tools/audit_month_folders.py` finds/fixes phantom month folders.

Still open (no fix yet): **mf05 Axis** (CMS feed has no monthly consolidated
file after May 2026 — monthly portfolio moved elsewhere), **mf25 Mahindra
Manulife** (downloads page redesigned, no xlsx links), **mf22 JM** (Flexicap,
Focused, Large & Midcap never match a link — 3/6), **mf21 Jio BlackRock** (only
the Arbitrage workbook is fetched; Large Cap / Sector Rotation / Flexi Cap are
not), **mf40 Tata** (advisorkhoj page lags the AMC by weeks).
