"""One-shot DOM probe for new AMC URLs. NOT cron-invoked.

Opens each URL in a headless Playwright Chromium (with stealth from
lib/fetcher.py BrowserFetcher), waits for the page to settle, then captures:

  - HTTP status of the main document
  - Final URL (after redirects)
  - Outer HTML (first 200 KB)
  - All <a href> links whose target looks like a portfolio file
    (.xlsx, .xls, .zip, .pdf)
  - All XHR/fetch responses observed during page settle (URL + status +
    content-type; body up to 5 KB if JSON)
  - All visible button/link text matching /monthly|portfolio/i (to spot
    SPA-click mechanisms)

Output:
  tools/probe_out/<mf_id>.json  — full capture per AMC
  tools/probe_out/INDEX.md      — one row per AMC with mechanism classification
                                  and recommended pattern

Run:
  python tools/probe_amc.py                  # all new AMCs (mf05 + mf22-mf46)
  python tools/probe_amc.py --only mf26      # one
  python tools/probe_amc.py --headed         # visible browser
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Allow importing project lib/ when run as `python tools/probe_amc.py`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config import MF_TARGETS, _CANONICAL_NAME, load_mfs  # noqa: E402
from lib.fetcher import BrowserFetcher                         # noqa: E402
from lib.log import get_logger                                 # noqa: E402

log = get_logger("probe")

# AMCs that are already implemented (have a real, non-stub scraper).
# Probing them is wasteful; we only probe the new ones by default.
ALREADY_DONE = {
    "mf01", "mf02", "mf03", "mf04", "mf06", "mf08", "mf09", "mf10",
    "mf11", "mf12", "mf13", "mf14", "mf15", "mf16", "mf17", "mf18",
    "mf19", "mf20", "mf21",
}

OUT_DIR = ROOT / "tools" / "probe_out"

FILE_EXT_RE = re.compile(r"\.(xlsx|xls|zip|pdf|csv)(\?|$)", re.IGNORECASE)
MONTHLY_TEXT_RE = re.compile(r"monthly|portfolio|disclosure|factsheet", re.IGNORECASE)


def classify(capture: dict) -> tuple[str, str, str]:
    """Return (mechanism, pattern_recommendation, one_line_note)."""
    status = capture.get("status", 0)
    file_links = capture.get("file_links", [])
    xhrs = capture.get("xhrs", [])
    visible_text_hits = capture.get("visible_text_hits", [])
    html_size = capture.get("html_size", 0)

    if status in (403, 401, 503) and not file_links:
        return ("akamai_blocked", "custom",
                f"page returned HTTP {status}; needs curl_cffi or proxy")

    if status == 0:
        return ("error", "custom", "page failed to load")

    # XHR returning JSON that names portfolio months/files → SPA reads from API.
    interesting_xhrs = [
        x for x in xhrs
        if (("application/json" in (x.get("content_type") or ""))
            and (
                "portfolio" in (x.get("url") or "").lower()
                or "scheme" in (x.get("url") or "").lower()
                or "disclosure" in (x.get("url") or "").lower()
                or "month" in (x.get("url") or "").lower()
                or "download" in (x.get("url") or "").lower()
                or "factsheet" in (x.get("url") or "").lower()
            ))
    ]
    if interesting_xhrs and not file_links:
        return ("xhr_api", "custom",
                f"SPA reads from {len(interesting_xhrs)} JSON endpoint(s); inspect response shape")

    # Direct anchor links to xlsx/zip/pdf — easiest case.
    xlsx_zip_links = [l for l in file_links if l["ext"] in ("xlsx", "xls", "zip")]
    pdf_links = [l for l in file_links if l["ext"] == "pdf"]

    if xlsx_zip_links:
        # Heuristic: one zip → zip pattern; many xlsx → likely per-scheme; one
        # xlsx → single multi-sheet.
        zips = [l for l in xlsx_zip_links if l["ext"] == "zip"]
        if zips and len(zips) >= len(xlsx_zip_links) // 2:
            return ("static_links", "zip",
                    f"{len(zips)} zip link(s); likely latest_month_zip pattern")
        if len(xlsx_zip_links) >= 5:
            return ("static_links", "per_scheme",
                    f"{len(xlsx_zip_links)} xlsx link(s); likely per_scheme_xlsx pattern")
        return ("static_links", "single_xlsx",
                f"{len(xlsx_zip_links)} xlsx link(s); likely single_xlsx pattern")

    if pdf_links and not xlsx_zip_links:
        return ("pdf_only", "factsheet",
                f"{len(pdf_links)} pdf link(s) and no xlsx; factsheet pattern")

    if visible_text_hits and not file_links:
        return ("spa_click", "custom",
                "SPA — file URLs hidden behind clicks; needs Playwright click harness")

    if html_size < 5000:
        return ("error", "custom",
                f"page rendered only {html_size} bytes of HTML — likely JS-blocked or empty")

    return ("unknown", "custom",
            "page loaded but no file links / API / SPA buttons detected")


def probe_one(browser: BrowserFetcher, mf_id: str, name: str, url: str) -> dict:
    log.info("--- probing %s: %s", mf_id, url)
    host = urlparse(url).hostname or ""
    capture: dict = {
        "mf_id": mf_id, "name": name, "url": url, "host": host,
        "status": 0, "final_url": "", "html_size": 0, "html_head": "",
        "file_links": [], "xhrs": [], "visible_text_hits": [],
        "error": "",
    }

    ctx = browser.context(host)
    page = ctx.new_page()
    xhrs: list[dict] = []

    def on_response(resp):
        try:
            u = resp.url
            ct = (resp.headers or {}).get("content-type", "")
            entry = {"url": u, "status": resp.status, "content_type": ct}
            # Sample body for JSON responses we might want to inspect.
            if "application/json" in ct and resp.status < 400:
                try:
                    body = resp.body()
                    entry["body_sample"] = body[:5000].decode("utf-8", errors="replace")
                except Exception:
                    pass
            xhrs.append(entry)
        except Exception:
            pass

    page.on("response", on_response)

    try:
        resp = page.goto(url, timeout=60_000, wait_until="domcontentloaded")
        if resp:
            capture["status"] = resp.status
            capture["final_url"] = resp.url
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        # Give SPAs a beat to settle XHRs.
        page.wait_for_timeout(3000)

        html = page.content()
        capture["html_size"] = len(html)
        capture["html_head"] = html[:200_000]

        # File-like <a href>
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({
                    href: a.href,
                    text: (a.innerText || a.textContent || '').trim().slice(0, 200),
                }))
        """) or []
        for h in hrefs:
            m = FILE_EXT_RE.search(h["href"])
            if m:
                capture["file_links"].append({
                    "href": h["href"],
                    "text": h["text"],
                    "ext": m.group(1).lower(),
                })

        # Buttons / spans / divs whose visible text mentions monthly/portfolio.
        text_hits = page.evaluate("""
            () => {
                const out = [];
                const seen = new Set();
                const sel = 'button, a, span, div, li';
                document.querySelectorAll(sel).forEach(el => {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t && t.length < 200 && /monthly|portfolio|disclosure|factsheet/i.test(t)
                        && !seen.has(t)) {
                        seen.add(t);
                        out.push({ tag: el.tagName, text: t });
                    }
                });
                return out.slice(0, 50);
            }
        """) or []
        capture["visible_text_hits"] = text_hits

        capture["xhrs"] = xhrs

    except Exception as e:
        capture["error"] = f"{type(e).__name__}: {e}"
        log.error("probe %s failed: %s", mf_id, e)
    finally:
        try:
            page.close()
        except Exception:
            pass

    return capture


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="One mf_id (e.g. mf26)", default=None)
    ap.add_argument("--all", action="store_true",
                    help="Probe ALL MFs (default: only new ones)")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mfs = load_mfs()
    if args.only:
        mfs = [m for m in mfs if m.id == args.only]
    elif not args.all:
        mfs = [m for m in mfs if m.id not in ALREADY_DONE]
    if not mfs:
        print("No MFs to probe.")
        return 0

    browser = BrowserFetcher(headed=args.headed)
    browser.start()
    captures: list[dict] = []
    try:
        for mf in mfs:
            cap = probe_one(browser, mf.id, mf.name, mf.url)
            mechanism, pattern, note = classify(cap)
            cap["classification"] = {
                "mechanism": mechanism, "pattern": pattern, "note": note,
            }
            captures.append(cap)
            (OUT_DIR / f"{mf.id}.json").write_text(
                json.dumps(cap, indent=2, ensure_ascii=False)[:5_000_000],
                encoding="utf-8",
            )
            log.info("    => %s | %s | %s", mechanism, pattern, note)
    finally:
        browser.close()

    # INDEX.md
    lines = [
        "# Probe index — new AMC URLs",
        "",
        "Generated by tools/probe_amc.py. One row per AMC. `pattern` is the",
        "recommended scrapers/patterns/* base class. `mechanism` describes how",
        "the page surfaces its portfolio files.",
        "",
        "| mf_id | AMC | mechanism | pattern | note |",
        "|---|---|---|---|---|",
    ]
    for cap in sorted(captures, key=lambda c: c["mf_id"]):
        cls = cap.get("classification", {})
        lines.append(
            f"| {cap['mf_id']} | {cap['name']} | "
            f"{cls.get('mechanism', '?')} | {cls.get('pattern', '?')} | "
            f"{cls.get('note', '').replace('|', '\\|')} |"
        )
    lines.append("")
    (OUT_DIR / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {len(captures)} captures + INDEX.md to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
