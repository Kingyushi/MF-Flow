"""Two-engine fetcher: requests (static) + Playwright (browser).

Designed for the MF Flow scraper. Per-host BrowserContext for cookie/auth
isolation. Polite 2-5s random delay between requests to the same host.
Stealth init script applied to every browser context.

Download surfaces:
- `static.download_file(url, dest, host, ...)` — straight requests GET.
- `browser.download_file(url, dest, host, ...)` — Playwright APIRequestContext,
  falls back to real navigation with expect_download (handles JS-triggered
  downloads).
- `browser.click_to_download(page, selector, dest, ...)` — for buttons that
  trigger a download via JS without a clean URL.

## Proxy support (for sites that IP-block the runtime)

Two env vars, both optional, both used by static + browser engines:
- `MF_FLOW_PROXY`            — global proxy applied to every host.
- `MF_FLOW_PROXY_HOSTS`      — comma-separated host suffixes that route through
                                the proxy; everything else stays direct.
                                Example: `hdfcfund.com,dspim.com,files.hdfcfund.com`

Proxy URL format is the standard `http://[user:pass@]host:port`. SOCKS5 also
works via the same syntax if PySocks is installed.

When MF_FLOW_PROXY is set without MF_FLOW_PROXY_HOSTS, ALL requests proxy.
When MF_FLOW_PROXY_HOSTS is set, only requests to those hosts proxy.
"""
from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .log import get_logger
from .paths import DOWNLOADS_DIR, ensure_runtime_dirs

log = get_logger("fetcher")


# ============================================================ PROXY CONFIG

_PROXY_URL = os.environ.get("MF_FLOW_PROXY", "").strip()
_PROXY_HOSTS = tuple(
    h.strip().lower()
    for h in os.environ.get("MF_FLOW_PROXY_HOSTS", "").split(",")
    if h.strip()
)


def _should_proxy(host: str) -> bool:
    """True iff requests to `host` should be routed through MF_FLOW_PROXY."""
    if not _PROXY_URL:
        return False
    if not _PROXY_HOSTS:
        return True  # global proxy
    host_l = (host or "").lower()
    return any(host_l == h or host_l.endswith("." + h) for h in _PROXY_HOSTS)


def proxy_available() -> bool:
    """True iff MF_FLOW_PROXY is configured (a scraper may retry a blocked host through it)."""
    return bool(_PROXY_URL)


def _proxy_dict_for(host: str, *, force: bool = False) -> dict | None:
    """Return a requests-style proxy dict for `host`, or None for direct.

    `force=True` routes through MF_FLOW_PROXY even when `host` is not listed
    in MF_FLOW_PROXY_HOSTS (scrapers use it to retry a host that blocks the
    server's own IP). It is a no-op when no proxy is configured.
    """
    if not _should_proxy(host) and not (force and _PROXY_URL):
        return None
    return {"http": _PROXY_URL, "https": _PROXY_URL}


def _proxy_settings_for(host: str) -> dict | None:
    """Return Playwright `proxy=` kwargs for `host`, or None for direct."""
    if not _should_proxy(host):
        return None
    from urllib.parse import urlparse
    parsed = urlparse(_PROXY_URL)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    out = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

_BASE_HEADERS = {
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def _pick_ua() -> str:
    return random.choice(_UA_POOL)


try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


# File signatures we accept (first few bytes). For sites that mis-serve
# xlsx as octet-stream we sniff to confirm.
SIG_XLSX = b"PK\x03\x04"      # zip header — xlsx and zip both start with this
SIG_PDF = b"%PDF"


@dataclass
class FetchResult:
    ok: bool
    url: str
    final_url: str = ""
    html: str = ""
    status_code: int = 0
    engine: str = ""
    error: str = ""
    network_file_urls: list[str] = field(default_factory=list)


# ============================================================ STATIC ENGINE

class StaticFetcher:
    def __init__(self) -> None:
        self._sessions: dict[str, requests.Session] = {}
        self._last_request_at: dict[str, float] = {}

    def _session(self, host: str) -> requests.Session:
        if host not in self._sessions:
            s = requests.Session()
            s.headers.update(_BASE_HEADERS)
            s.headers["User-Agent"] = _pick_ua()
            self._sessions[host] = s
        return self._sessions[host]

    def _polite(self, host: str) -> None:
        prev = self._last_request_at.get(host)
        if prev is not None:
            delay = random.uniform(2.0, 5.0)
            elapsed = time.monotonic() - prev
            if elapsed < delay:
                time.sleep(delay - elapsed)
        self._last_request_at[host] = time.monotonic()

    def fetch_html(self, url: str, host: str, *, force_proxy: bool = False) -> FetchResult:
        self._polite(host)
        s = self._session(host)
        try:
            # When proxied via Bright Data, the proxy injects its own CA into
            # the TLS chain (SSL inspection), so verify must be off.
            proxies = _proxy_dict_for(host, force=force_proxy)
            r = s.get(url, timeout=30, allow_redirects=True,
                      proxies=proxies,
                      verify=proxies is None)
            return FetchResult(
                ok=r.ok,
                url=url,
                final_url=r.url,
                html=r.text,
                status_code=r.status_code,
                engine="static",
                error="" if r.ok else f"HTTP {r.status_code}",
            )
        except Exception as e:
            return FetchResult(ok=False, url=url, engine="static", error=f"{type(e).__name__}: {e}")

    def download_file(
        self,
        url: str,
        dest: Path,
        host: str,
        *,
        referer: str = "",
        expected_signatures: tuple[bytes, ...] = (),
        force_proxy: bool = False,
    ) -> bool:
        """Download to dest. Return True on success. Optionally verify magic bytes.

        `force_proxy=True` routes through MF_FLOW_PROXY regardless of
        MF_FLOW_PROXY_HOSTS (no-op when no proxy is configured).
        """
        self._polite(host)
        s = self._session(host)
        try:
            extra = {"Referer": referer or f"https://{host}/", "Accept": "*/*"}
            proxies = _proxy_dict_for(host, force=force_proxy)
            r = s.get(url, timeout=120, allow_redirects=True, stream=True, headers=extra,
                      proxies=proxies,
                      verify=proxies is None)
            if not r.ok:
                log.warning("download_file %s -> HTTP %s", url, r.status_code)
                return False
            it = r.iter_content(chunk_size=8192)
            try:
                first = next(it)
            except StopIteration:
                first = b""
            if expected_signatures and not any(first.startswith(sig) for sig in expected_signatures):
                log.warning("download_file %s -> bad signature (first8=%r)", url, first[:8])
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                f.write(first)
                for chunk in it:
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            log.error("download_file %s failed: %s", url, e)
            return False

    def close(self) -> None:
        for s in self._sessions.values():
            s.close()
        self._sessions.clear()


# ============================================================ BROWSER ENGINE

class BrowserFetcher:
    """Playwright headless Chromium with per-host context isolation + stealth."""

    def __init__(self, *, headed: bool = False) -> None:
        self._headed = headed
        self._playwright = None
        self._browser = None
        self._contexts: dict[str, object] = {}
        self._last_request_at: dict[str, float] = {}

    def start(self) -> None:
        if self._playwright is not None and self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright not installed. Run pip install -r requirements.txt."
            ) from e
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=not self._headed,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as e:
            msg = str(e)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                raise RuntimeError(
                    "Chromium not installed. Run from venv: python -m playwright install chromium"
                ) from e
            raise

    def _polite(self, host: str) -> None:
        prev = self._last_request_at.get(host)
        if prev is not None:
            delay = random.uniform(2.0, 5.0)
            elapsed = time.monotonic() - prev
            if elapsed < delay:
                time.sleep(delay - elapsed)
        self._last_request_at[host] = time.monotonic()

    def context(self, host: str):
        """Get-or-create a BrowserContext per host. Public so scrapers can reuse it."""
        if host in self._contexts:
            return self._contexts[host]
        self.start()
        kwargs: dict = {
            "user_agent": _pick_ua(),
            "locale": "en-IN",
            "viewport": {"width": 1366, "height": 768},
            "extra_http_headers": {"Accept-Language": "en-IN,en;q=0.9"},
            "accept_downloads": True,
        }
        proxy_kwargs = _proxy_settings_for(host)
        if proxy_kwargs:
            kwargs["proxy"] = proxy_kwargs
            # Bright Data residential injects its own CA into the chain — Chromium
            # rejects the TLS handshake without this flag.
            kwargs["ignore_https_errors"] = True
            log.info("Routing host=%s through MF_FLOW_PROXY=%s", host, proxy_kwargs["server"])
        ctx = self._browser.new_context(**kwargs)
        # Apply playwright-stealth (covers webdriver, plugins, languages,
        # webgl vendor, chrome.runtime, perm query, etc).
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(ctx)
        except Exception as e:
            log.info("stealth not applied (%s); falling back to manual JS scrub", type(e).__name__)
            ctx.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en-US', 'en']});
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
                if (originalQuery) {
                  window.navigator.permissions.query = (p) =>
                    p.name === 'notifications' ? Promise.resolve({state: Notification.permission}) : originalQuery(p);
                }
                """
            )
        self._contexts[host] = ctx
        return ctx

    def open_page(self, url: str, host: str, *, wait_for_idle: bool = True):
        """Open url in a new page in the per-host context. Returns the page.
        Caller is responsible for page.close()."""
        self._polite(host)
        ctx = self.context(host)
        page = ctx.new_page()
        try:
            page.goto(url, timeout=60_000, wait_until="domcontentloaded")
            if wait_for_idle:
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
        except Exception:
            # Caller can still query partial DOM if useful, or close + retry.
            pass
        return page

    def download_file(
        self,
        url: str,
        dest: Path,
        host: str,
        *,
        referer: str = "",
        expected_signatures: tuple[bytes, ...] = (),
    ) -> bool:
        """APIRequestContext first; nav-with-expect_download fallback."""
        self._polite(host)
        ctx = self.context(host)
        hdrs = {"Accept-Encoding": "identity", "Accept": "*/*"}
        hdrs["Referer"] = referer or f"https://{host}/"

        try:
            resp = ctx.request.get(url, timeout=120_000, headers=hdrs)
            if resp.ok:
                body = resp.body()
                if expected_signatures and not any(body.startswith(sig) for sig in expected_signatures):
                    log.info("browser API got bad signature for %s (first8=%r), trying nav", url, body[:8])
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    return True
            else:
                log.info("browser API got HTTP %s for %s, trying nav", resp.status, url)
        except Exception as e:
            log.info("browser API raised %s for %s, trying nav", type(e).__name__, url)

        try:
            page = ctx.new_page()
            try:
                with page.expect_download(timeout=30_000) as dlinfo:
                    try:
                        page.goto(url, wait_until="commit", timeout=30_000)
                    except Exception:
                        pass
                dl = dlinfo.value
                dest.parent.mkdir(parents=True, exist_ok=True)
                dl.save_as(str(dest))
                if expected_signatures:
                    head = dest.read_bytes()[:8]
                    if not any(head.startswith(sig) for sig in expected_signatures):
                        log.warning("nav download %s -> bad sig (first8=%r)", url, head)
                        return False
                return True
            finally:
                try:
                    page.close()
                except Exception:
                    pass
        except Exception as e:
            log.error("browser download_file %s failed: %s", url, e)
            return False

    def click_to_download(
        self,
        page,
        click_action,
        dest: Path,
        *,
        timeout_ms: int = 60_000,
        expected_signatures: tuple[bytes, ...] = (),
    ) -> bool:
        """Perform `click_action()` (a no-arg callable that triggers the download
        on the given page) and save the resulting download to dest."""
        try:
            with page.expect_download(timeout=timeout_ms) as dlinfo:
                click_action()
            dl = dlinfo.value
            dest.parent.mkdir(parents=True, exist_ok=True)
            dl.save_as(str(dest))
            if expected_signatures:
                head = dest.read_bytes()[:8]
                if not any(head.startswith(sig) for sig in expected_signatures):
                    log.warning("click download -> bad sig (first8=%r) at %s", head, dest)
                    return False
            return True
        except Exception as e:
            log.error("click_to_download failed: %s", e)
            return False

    def close(self) -> None:
        for ctx in self._contexts.values():
            try:
                ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._playwright = None


# ============================================================ HOLDER

class Fetcher:
    def __init__(self, *, headed: bool = False) -> None:
        ensure_runtime_dirs()
        self.static = StaticFetcher()
        self.browser = BrowserFetcher(headed=headed)

    def close(self) -> None:
        self.static.close()
        self.browser.close()


@contextmanager
def fetcher(*, headed: bool = False):
    f = Fetcher(headed=headed)
    try:
        yield f
    finally:
        f.close()


def fresh_dest(name: str, ext: str) -> Path:
    """Path inside DOWNLOADS_DIR with a stable but unique name."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOADS_DIR / f"{name}-{int(time.time()*1000)}.{ext.lstrip('.')}"
