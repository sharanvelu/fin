"""Tests for fincli.plugs.catalog — raw-URL fetches against the plug repo."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from fincli.config import Config
from fincli.core.errors import FinError, NotFound
from fincli.plugs import catalog


# --------------------------------------------------------------------------- #
# URL building / name validation
# --------------------------------------------------------------------------- #
def test_plug_url_uses_configured_base(monkeypatch):
    monkeypatch.setattr(Config, "PLUGS_REPO_RAW", "https://example.test/repo")
    assert catalog.plug_url("laravel") == "https://example.test/repo/plugs/laravel.py"


def test_catalog_url_uses_configured_value(monkeypatch):
    monkeypatch.setattr(
        Config, "PLUGS_CATALOG_URL", "https://example.test/rel/catalog.json"
    )
    assert catalog.catalog_url() == "https://example.test/rel/catalog.json"


@pytest.mark.parametrize("name", ["laravel", "postgres", "my-plug", "my_plug2"])
def test_validate_name_accepts(name):
    assert catalog.validate_name(name) == name


@pytest.mark.parametrize("name", ["Laravel", "../etc", "a b", "", "-lead", ".hid"])
def test_validate_name_rejects(name):
    with pytest.raises(FinError):
        catalog.validate_name(name)


# --------------------------------------------------------------------------- #
# fetching (urlopen mocked)
# --------------------------------------------------------------------------- #
def _fake_urlopen(payload: bytes):
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    return lambda url, timeout=0, context=None: _Resp(payload)


def _http_404(url):
    return urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)


def test_fetch_plug_source_returns_text(monkeypatch):
    monkeypatch.setattr(
        catalog.urllib.request, "urlopen", _fake_urlopen(b"class X: pass")
    )
    assert catalog.fetch_plug_source("laravel") == "class X: pass"


def test_fetch_plug_source_404_raises_notfound_with_suggestion(monkeypatch):
    def urlopen(url, timeout=0, context=None):
        raise _http_404(url)

    monkeypatch.setattr(catalog.urllib.request, "urlopen", urlopen)
    entries = [{"name": "laravel"}, {"name": "django"}]
    monkeypatch.setattr(catalog, "fetch_catalog", lambda: entries)
    with pytest.raises(NotFound) as exc:
        catalog.fetch_plug_source("laravl")
    assert "laravel" in exc.value.message


def test_fetch_plug_source_offline_raises_network_error(monkeypatch):
    def urlopen(url, timeout=0, context=None):
        raise urllib.error.URLError("dns down")

    monkeypatch.setattr(catalog.urllib.request, "urlopen", urlopen)
    with pytest.raises(FinError) as exc:
        catalog.fetch_plug_source("laravel")
    assert exc.value.title == "Network Error"


def test_fetch_plug_source_http_500_raises_network_error(monkeypatch):
    def urlopen(url, timeout=0, context=None):
        raise urllib.error.HTTPError(url, 500, "boom", hdrs=None, fp=None)

    monkeypatch.setattr(catalog.urllib.request, "urlopen", urlopen)
    with pytest.raises(FinError) as exc:
        catalog.fetch_plug_source("laravel")
    assert exc.value.title == "Network Error"


def test_fetch_catalog_parses_plugs(monkeypatch):
    payload = json.dumps(
        {"schema_version": 1, "plugs": [{"name": "laravel", "type": "APP"}]}
    ).encode()
    monkeypatch.setattr(catalog.urllib.request, "urlopen", _fake_urlopen(payload))
    assert catalog.fetch_catalog() == [{"name": "laravel", "type": "APP"}]


@pytest.mark.parametrize("payload", [b"not json", b"{}", b'{"plugs": 5}'])
def test_fetch_catalog_malformed_raises(monkeypatch, payload):
    monkeypatch.setattr(catalog.urllib.request, "urlopen", _fake_urlopen(payload))
    with pytest.raises(FinError) as exc:
        catalog.fetch_catalog()
    assert exc.value.title == "Catalog Error"


def test_fetch_catalog_404_raises_network_error(monkeypatch):
    def urlopen(url, timeout=0, context=None):
        raise _http_404(url)

    monkeypatch.setattr(catalog.urllib.request, "urlopen", urlopen)
    with pytest.raises(FinError) as exc:
        catalog.fetch_catalog()
    assert exc.value.title == "Network Error"


# --------------------------------------------------------------------------- #
# search filtering
# --------------------------------------------------------------------------- #
def test_search_catalog_matches_name_and_description(monkeypatch):
    entries = [
        {"name": "laravel", "description": "PHP framework"},
        {"name": "django", "description": "Python web framework"},
        {"name": "redis", "description": "Cache"},
    ]
    monkeypatch.setattr(catalog, "fetch_catalog", lambda: entries)
    assert [e["name"] for e in catalog.search_catalog("FRAMEWORK")] == [
        "laravel",
        "django",
    ]
    assert [e["name"] for e in catalog.search_catalog("red")] == ["redis"]
    assert catalog.search_catalog("nomatch") == []
