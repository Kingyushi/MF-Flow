"""lib.fetcher proxy plumbing: host-list routing and the `force_proxy` override
used by scrapers to retry a host that blocks the server's IP (PGIM, Tata)."""
from __future__ import annotations

import lib.fetcher as F

PROXY = "http://user:secret@proxy.example:22225"
PROXY_DICT = {"http": PROXY, "https": PROXY}


def test_no_proxy_configured(monkeypatch):
    monkeypatch.setattr(F, "_PROXY_URL", "")
    monkeypatch.setattr(F, "_PROXY_HOSTS", ())
    assert F.proxy_available() is False
    assert F._proxy_dict_for("www.pgimindia.com") is None
    assert F._proxy_dict_for("www.pgimindia.com", force=True) is None  # force is a no-op


def test_host_list_routing_and_force(monkeypatch):
    monkeypatch.setattr(F, "_PROXY_URL", PROXY)
    monkeypatch.setattr(F, "_PROXY_HOSTS", ("dspim.com", "hdfcfund.com"))
    assert F.proxy_available() is True
    assert F._proxy_dict_for("www.dspim.com") == PROXY_DICT
    assert F._proxy_dict_for("files.hdfcfund.com") == PROXY_DICT
    assert F._proxy_dict_for("www.pgimindia.com") is None
    assert F._proxy_dict_for("www.pgimindia.com", force=True) == PROXY_DICT


def test_global_proxy_when_host_list_empty(monkeypatch):
    monkeypatch.setattr(F, "_PROXY_URL", PROXY)
    monkeypatch.setattr(F, "_PROXY_HOSTS", ())
    assert F._proxy_dict_for("anything.example") == PROXY_DICT


class _Resp:
    def __init__(self, url: str) -> None:
        self.url = url
        self.ok = True
        self.status_code = 200
        self.text = "<html>ok</html>"

    def iter_content(self, chunk_size=8192):
        yield b"PK\x03\x04payload"


def test_static_fetcher_passes_proxy_and_verify(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_PROXY_URL", PROXY)
    monkeypatch.setattr(F, "_PROXY_HOSTS", ("dspim.com",))
    calls: list[dict] = []

    def fake_get(self, url, **kw):
        calls.append(kw)
        return _Resp(url)

    monkeypatch.setattr(F.requests.Session, "get", fake_get)
    sf = F.StaticFetcher()
    monkeypatch.setattr(sf, "_polite", lambda host: None)

    # direct host, no force -> no proxy, TLS verified
    r = sf.fetch_html("https://www.pgimindia.com/x", "www.pgimindia.com")
    assert r.ok and calls[-1]["proxies"] is None and calls[-1]["verify"] is True
    # direct host, forced -> proxy, verification off (Bright Data SSL inspection)
    r = sf.fetch_html("https://www.pgimindia.com/x", "www.pgimindia.com", force_proxy=True)
    assert r.ok and calls[-1]["proxies"] == PROXY_DICT and calls[-1]["verify"] is False
    # listed host -> proxy without force
    r = sf.fetch_html("https://www.dspim.com/x", "www.dspim.com")
    assert r.ok and calls[-1]["proxies"] == PROXY_DICT and calls[-1]["verify"] is False

    dest = tmp_path / "f.xlsx"
    ok = sf.download_file(
        "https://www.pgimindia.com/f.xlsx", dest, "www.pgimindia.com",
        expected_signatures=(b"PK",), force_proxy=True,
    )
    assert ok and dest.read_bytes().startswith(b"PK\x03\x04")
    assert calls[-1]["proxies"] == PROXY_DICT and calls[-1]["verify"] is False
    ok = sf.download_file("https://www.pgimindia.com/f.xlsx", dest, "www.pgimindia.com")
    assert ok and calls[-1]["proxies"] is None and calls[-1]["verify"] is True
