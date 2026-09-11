"""Edelweiss Mutual Fund — curl_cffi + Node.js hybrid-crypto-js.

Akamai blocks both plain requests and Playwright from this network. The site's
own SPA solves this with a real-browser TLS+JA3 fingerprint, so we replicate it
via `curl_cffi` with `impersonate="chrome131"`.

=== VAPT mode (active since ~June 2026) ===

The SPA's Angular HTTP interceptor encrypts POST request bodies with
hybrid-crypto-js (RSA-OAEP 4096-bit + AES-256-CBC hybrid envelope). The RSA
public key is embedded in main.js. Rather than porting node-forge's RSA
implementation to Python, we shell out to Node.js with the actual
`hybrid-crypto-js` npm package to produce the encrypted envelope.

Flow:
  1. curl_cffi warms cookies via SPA page load (Akamai bypass via JA3).
  2. Extract the RSA public key from main.js.
  3. POST to third-party/getStatutoryMenu — body encrypted via Node.js.
  4. Decrypt the AES-encrypted response to get menu IDs.
  5. POST to third-party/getSingleStatutory to get file listings.
  6. Download the xlsx file directly.

Response decryption uses CryptoJS AES-256-CBC with EVP_BytesToKey(MD5) KDF.
The passphrase is HmacSHA256(secreat + client_ip + timestamp_ms, hashKey).hex()
where secreat/hashKey are constants from main.js.

=== Key rotation ===

To regenerate constants if Edelweiss rotates them:
  1. `grep -E 'defaultAesKey|encryption:\\{secreat' main.*.js`
  2. Extract SECREAT and HASHKEY values.
  3. The RSA public key is auto-extracted from main.js at runtime.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from lib.fetcher import Fetcher, fresh_dest
from lib.log import get_logger
from lib.month_hint import MONTH_FULL, MONTH_SHORT, parse_as_on

from .base import (
    BaseScraper,
    DiscoveryResult,
    DownloadedFile,
    NoDataYetError,
    ScraperError,
    retry,
)

log = get_logger("mf13")

SECREAT = "5b6714126d3149fbab994747b2633287"
HASHKEY = "r4vcos0ejvndsow95n"
STATIC_IP = "103.0.123.175"
API_BASE = "https://api.edelweissmf.com/edelweissmf/api/v1"
FILES_BASE = "https://www.edelweissmf.com"
SPA_URL = f"{FILES_BASE}/statutory/portfolio-of-schemes"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_ALL_MONTHS = {**MONTH_FULL, **MONTH_SHORT}


def _hmac_key(ip: str, ts: str) -> str:
    return hmac.new(
        HASHKEY.encode(),
        (SECREAT + ip + ts).encode(),
        hashlib.sha256,
    ).hexdigest()


def _evp_bytes_to_key(passphrase: bytes, salt: bytes,
                      key_len: int = 32, iv_len: int = 16) -> tuple[bytes, bytes]:
    """OpenSSL EVP_BytesToKey with MD5 — CryptoJS's default KDF."""
    d, out = b"", b""
    while len(out) < key_len + iv_len:
        d = hashlib.md5(d + passphrase + salt).digest()
        out += d
    return out[:key_len], out[key_len:key_len + iv_len]


def _cryptojs_decrypt(b64: str, passphrase: str) -> bytes:
    from Crypto.Cipher import AES
    raw = base64.b64decode(b64)
    if raw[:8] != b"Salted__":
        raise ScraperError("Edelweiss: unexpected encryption envelope")
    salt, ct = raw[8:16], raw[16:]
    key, iv = _evp_bytes_to_key(passphrase.encode(), salt)
    pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
    if not pt:
        raise ScraperError("Edelweiss: AES decrypt produced empty plaintext")
    return pt[:-pt[-1]]


def _extract_pem_from_js(js: str) -> str:
    """Extract the RSA public key PEM from the SPA's main.js bundle."""
    pem_match = re.search(
        r'(-----BEGIN (?:RSA )?PUBLIC KEY-----'
        r'[A-Za-z0-9+/=\s\\n]+'
        r'-----END (?:RSA )?PUBLIC KEY-----)',
        js,
    )
    if not pem_match:
        raise ScraperError("Edelweiss: RSA public key not found in main.js")
    pem = pem_match.group(1).replace('\\n', '\n')
    return '\n'.join(line.strip() for line in pem.split('\n'))


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _node_encrypt(pem_key: str, plaintext: str) -> str:
    """Encrypt plaintext using Node.js hybrid-crypto-js package.

    Returns the JSON envelope string ready for POST body {data: ...}.
    Runs Node with cwd=project root so `require('hybrid-crypto-js')` finds
    the local node_modules regardless of where the runner was invoked from.
    """
    node_script = (
        "const{Crypt}=require('hybrid-crypto-js');"
        "const c=new Crypt();"
        f"const k=`{pem_key}`;"
        f"const p={json.dumps(plaintext)};"
        "process.stdout.write(c.encrypt(k,p));"
    )
    if not (_PROJECT_ROOT / "node_modules" / "hybrid-crypto-js").exists():
        raise ScraperError(
            "Edelweiss: hybrid-crypto-js npm package not installed. "
            f"Run: cd {_PROJECT_ROOT} && npm install"
        )
    try:
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True, text=True,
            timeout=15,
            cwd=str(_PROJECT_ROOT),
        )
    except FileNotFoundError:
        raise ScraperError(
            "Edelweiss: Node.js not found on PATH. Required for "
            "hybrid-crypto-js encryption. Install Node.js >=18 and run: "
            f"cd {_PROJECT_ROOT} && npm install"
        )
    except subprocess.TimeoutExpired:
        raise ScraperError("Edelweiss: Node.js encryption timed out (>15s)")

    if result.returncode != 0:
        raise ScraperError(
            f"Edelweiss: Node.js encryption failed: {result.stderr[:300]}"
        )
    return result.stdout.strip()


def _open_session():
    try:
        from curl_cffi import requests as creq
    except ImportError as e:
        raise ScraperError(
            "Edelweiss requires curl_cffi (Akamai bypass). "
            "Run: pip install curl_cffi"
        ) from e
    s = creq.Session(impersonate="chrome131")
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": FILES_BASE,
        "Referer": SPA_URL,
    })
    try:
        s.get(SPA_URL, timeout=30)            # warm cookies
    except Exception as e:
        raise ScraperError(f"Edelweiss SPA warmup failed: {e}")
    return s


def _fetch_pem(session) -> str:
    """Fetch the SPA homepage, find main.js, extract the RSA PEM key."""
    r = session.get(FILES_BASE, timeout=15)
    if r.status_code != 200:
        raise ScraperError(f"Edelweiss homepage HTTP {r.status_code}")
    m = re.search(r'src="(main\.[a-f0-9]+\.js)"', r.text)
    if not m:
        raise ScraperError("Edelweiss: main.js not found in homepage HTML")
    main_js_url = f"{FILES_BASE}/{m.group(1)}"
    log.info("Fetching main.js: %s", main_js_url)
    r2 = session.get(main_js_url, timeout=30)
    if r2.status_code != 200:
        raise ScraperError(f"Edelweiss main.js HTTP {r2.status_code}")
    return _extract_pem_from_js(r2.text)


def _api_post(session, endpoint: str, body: dict, pem: str) -> dict:
    """Encrypt body with hybrid-crypto-js, POST, decrypt response."""
    ts = str(int(time.time() * 1000))
    ip = STATIC_IP
    key = _hmac_key(ip, ts)
    hdrs = {
        "x-timestamp": ts,
        "x-ip-address": ip,
        "Content-Type": "application/json",
    }

    encrypted = _node_encrypt(pem, json.dumps(body))
    url = f"{API_BASE}/{endpoint}"
    r = session.post(url, headers=hdrs, json={"data": encrypted}, timeout=30)
    log.info("POST %s -> %d", endpoint, r.status_code)

    if r.status_code not in (200, 201):
        raise ScraperError(
            f"Edelweiss API POST {endpoint} HTTP {r.status_code}: "
            f"{r.text[:200]}"
        )

    resp = r.json()
    envelope = resp.get("body")
    if not envelope or not isinstance(envelope, str):
        raise ScraperError(
            f"Edelweiss API: missing or non-string 'body' in response from {endpoint}"
        )

    try:
        data = json.loads(_cryptojs_decrypt(envelope, key).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ScraperError(
            f"Edelweiss decrypt/parse for {endpoint}: {type(e).__name__}: {e}"
        )
    return data


def _api_get_statutory_menu(session, menu_name: str = "Portfolio of scheme(s)") -> dict:
    """=== 2026-07 MAINTENANCE FIX (API migration) ===

    The SPA moved from the encrypted POST `third-party/getSingleStatutory`
    (whose data froze around 2026-07-07) to a plain GET:

        GET /mf/statutory-menus/single?type=Statutory&fundType=MF&menuName=Portfolio of scheme(s)

    No RSA / hybrid-crypto-js / Node.js is needed for the request. The response
    is the same CryptoJS AES envelope ({"body": "U2FsdGVk..."}), decrypted with
    the HMAC passphrase derived from the x-timestamp / x-ip-address headers we
    send. Decrypted shape: {"submenus": [...], "files": [{month, year,
    fileTitle, filePath, subMenuName, ...}]} — note the lowercase keys.
    """
    ts = str(int(time.time() * 1000))
    ip = STATIC_IP
    key = _hmac_key(ip, ts)
    url = f"{API_BASE}/mf/statutory-menus/single"
    params = {"type": "Statutory", "fundType": "MF", "menuName": menu_name}
    r = session.get(url, params=params, headers={"x-timestamp": ts, "x-ip-address": ip}, timeout=30)
    log.info("GET statutory-menus/single -> %d", r.status_code)
    if r.status_code != 200:
        raise ScraperError(f"Edelweiss statutory-menus GET HTTP {r.status_code}: {r.text[:200]}")
    envelope = r.json().get("body")
    if not envelope or not isinstance(envelope, str):
        raise ScraperError("Edelweiss statutory-menus: missing 'body' envelope")
    try:
        return json.loads(_cryptojs_decrypt(envelope, key).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ScraperError(f"Edelweiss statutory-menus decrypt/parse: {type(e).__name__}: {e}")


def _pick_latest_monthly(files: list[dict]) -> dict:
    """Newest 'Monthly Portfolio and Risk-o-Meter' entry by (year, month)."""
    monthly = [
        f for f in files
        if "monthly portfolio" in str(f.get("subMenuName") or f.get("SubMenuName") or "").lower()
    ]
    if not monthly:
        raise NoDataYetError("Edelweiss: no Monthly Portfolio entries in API response")

    def _ym(item):
        try:
            y = int(item.get("year") or item.get("Year"))
            m = _ALL_MONTHS[str(item.get("month") or item.get("Month")).strip().lower()]
        except (KeyError, ValueError, AttributeError, TypeError):
            return (0, 0, "")
        return (y, m, str(item.get("createdOn") or item.get("Created_On") or ""))

    return max(monthly, key=_ym)


class Scraper(BaseScraper):
    PATTERN = "single_xlsx_multi_sheet"

    @retry(times=2, backoff=(5.0, 15.0))
    def discover_latest_month(self, fetcher: Fetcher) -> DiscoveryResult:
        s = _open_session()

        # Preferred path (2026-07+): plain GET, no Node.js. Fall back to the
        # legacy encrypted POST only if the GET path breaks.
        try:
            data = _api_get_statutory_menu(s)
            files = data.get("files") or []
            latest = _pick_latest_monthly(files)
        except NoDataYetError:
            raise
        except Exception as e:
            log.warning("Edelweiss GET path failed (%s); falling back to encrypted POST", e)
            pem = _fetch_pem(s)
            data = _api_post(
                s, "third-party/getSingleStatutory",
                {"category": "portfolio-of-schemes"},
                pem,
            )
            items = [i for i in (data.get("CommonDetails") or []) if str(i.get("MenuID")) == "2"]
            latest = _pick_latest_monthly(items)

        try:
            year = int(latest.get("year") or latest.get("Year"))
            month = _ALL_MONTHS[str(latest.get("month") or latest.get("Month")).strip().lower()]
        except (KeyError, ValueError, AttributeError, TypeError) as e:
            raise ScraperError(f"Edelweiss: cannot parse year/month from {latest}: {e}")

        # Construct download URL (path segments may contain spaces)
        path = latest.get("filePath") or latest.get("FilePath") or ""
        if not path:
            raise ScraperError(f"Edelweiss: entry has no filePath: {latest}")
        url = FILES_BASE + "/".join(quote(seg) for seg in path.split("/"))

        as_on: Optional[date] = parse_as_on(
            str(latest.get("fileTitle") or latest.get("FileTitle") or ""),
            str(latest.get("systemFileName") or latest.get("SystemFileName") or ""),
        )

        self._session_obj = s
        self._download_url = url
        self._label = latest.get("fileTitle") or latest.get("FileTitle") or "Monthly Portfolio"
        return DiscoveryResult(year=year, month=month, as_on_date=as_on)

    @retry(times=2, backoff=(5.0, 15.0))
    def download(self, fetcher: Fetcher, target: DiscoveryResult) -> list[DownloadedFile]:
        url = getattr(self, "_download_url", None)
        s = getattr(self, "_session_obj", None)
        if url is None or s is None:
            self.discover_latest_month(fetcher)
            url = self._download_url
            s = self._session_obj

        dest = fresh_dest(self.mf.id, "xlsx")
        try:
            r = s.get(url, timeout=120, stream=True)
        except Exception as e:
            raise ScraperError(f"Edelweiss download exception: {e}")
        if r.status_code != 200:
            raise ScraperError(f"Edelweiss file HTTP {r.status_code}: {url[:140]}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        head = dest.read_bytes()[:4]
        if head != b"PK\x03\x04":
            raise ScraperError(
                f"Edelweiss: downloaded file has bad signature {head!r}, expected xlsx"
            )
        return [DownloadedFile(
            src_path=dest,
            scheme_name=None,
            source_url=url,
            label=self.mf.name,
        )]
