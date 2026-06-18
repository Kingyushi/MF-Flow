"""Probe Edelweiss disclosures URL with different fetchers to identify a
working bypass for Akamai's bot block. Run from a venv shell:
    .venv\\Scripts\\python.exe tests\\probe_edelweiss.py
"""
from __future__ import annotations

import sys

URL = "https://www.edelweissmf.com/statutory/portfolio-of-schemes"
H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


def _label(html: str) -> str:
    low = html.lower()
    if "access denied" in low:
        return "BLOCKED (access denied)"
    if "you don't have permission" in low:
        return "BLOCKED (akamai forbidden)"
    if "<title>" in low:
        i = low.index("<title>") + 7
        j = low.index("</title>", i)
        return f"OK title={html[i:j].strip()!r}"
    return f"UNKNOWN ({len(html)} bytes)"


def probe_requests() -> None:
    import requests
    print(">>> requests (plain)")
    try:
        r = requests.get(URL, headers=H, timeout=20)
        print(f"  status={r.status_code}  bytes={len(r.text)}  {_label(r.text)}")
    except Exception as e:
        print(f"  ERR {type(e).__name__}: {e}")


def probe_curl_cffi() -> None:
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print(">>> curl_cffi: NOT INSTALLED — pip install curl_cffi")
        return
    print(">>> curl_cffi impersonate=chrome131")
    try:
        r = creq.get(URL, headers=H, timeout=20, impersonate="chrome131")
        print(f"  status={r.status_code}  bytes={len(r.text)}  {_label(r.text)}")
        # If success, sniff for monthly portfolio anchors.
        if r.status_code == 200 and "access denied" not in r.text.lower():
            import re
            anchors = re.findall(
                r'<a[^>]+href="([^"]*\.xlsx)"[^>]*>([^<]*)</a>',
                r.text, re.IGNORECASE,
            )
            print(f"  found {len(anchors)} .xlsx anchors")
            for href, text in anchors[:5]:
                print(f"    {text.strip()[:60]} -> {href[:120]}")
    except Exception as e:
        print(f"  ERR {type(e).__name__}: {e}")


def probe_playwright() -> None:
    print(">>> Playwright (current scraper path)")
    try:
        from playwright.sync_api import sync_playwright
        try:
            from playwright_stealth import Stealth
            has_stealth = True
        except ImportError:
            has_stealth = False
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=H["User-Agent"],
                locale="en-IN",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            )
            if has_stealth:
                Stealth().apply_stealth_sync(ctx)
            page = ctx.new_page()
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
            except Exception as e:
                print(f"  goto raised {type(e).__name__}: {e}")
            page.wait_for_timeout(4000)
            title = page.title()
            html = page.content()
            print(f"  title={title!r}  bytes={len(html)}  {_label(html)}")
            anchors = page.evaluate(r"""
                () => [...document.querySelectorAll('a')]
                    .filter(a => (a.href||'').toLowerCase().endsWith('.xlsx'))
                    .slice(0, 5)
                    .map(a => ({text: (a.innerText||'').trim().slice(0,60), href: a.href}))
            """)
            print(f"  visible .xlsx anchors: {len(anchors)}")
            for a in anchors:
                print(f"    {a['text']} -> {a['href'][:120]}")
            browser.close()
    except Exception as e:
        print(f"  ERR {type(e).__name__}: {e}")


if __name__ == "__main__":
    probe_requests()
    print()
    probe_curl_cffi()
    print()
    probe_playwright()
