"""Remote plug catalog — plain-HTTPS fetches against the fin-plugs repo.

The fin-plugs repository stores every plug as one file (``plugs/<name>.py``)
on its master branch, and its release workflow publishes a generated
``catalog.json`` as an asset of each release. Installing fetches the plug
file straight from ``raw.githubusercontent.com`` (the URL is fully determined
by the plug name); searching fetches the latest release's catalog. No git
binary, no GitHub API, no rate limits. URLs come from
:attr:`fincli.config.Config.PLUGS_REPO_RAW` and
:attr:`fincli.config.Config.PLUGS_CATALOG_URL` (env-overridable via
``FIN_PLUGS_REPO_RAW`` / ``FIN_PLUGS_CATALOG_URL`` for forks and tests).
"""

from __future__ import annotations

import difflib
import json
import re
import ssl
import urllib.error
import urllib.request

from fincli.app import EXIT_SYSTEM
from fincli.config import Config
from fincli.core.errors import FinError, NotFound

#: Network timeout for catalog/plug fetches, seconds.
TIMEOUT = 15


def _ssl_context() -> ssl.SSLContext:
    """TLS context using certifi's CA bundle when available.

    certifi ships transitively with the docker SDK (via requests), so it is
    present both from source and inside the PyInstaller bundle — and unlike
    the interpreter's default trust store, it works on macOS Pythons that
    were installed without system certificates.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi is a transitive dep
        return ssl.create_default_context()


#: Valid plug names — these become path segments of the raw URL.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def plug_url(name: str) -> str:
    """Raw URL of a plug's single-file source."""
    return f"{Config.PLUGS_REPO_RAW}/plugs/{name}.py"


def catalog_url() -> str:
    """URL of the catalog index (latest release asset of the plug repo)."""
    return Config.PLUGS_CATALOG_URL


def validate_name(name: str) -> str:
    """Return *name* if it is a legal plug name, else raise FinError."""
    if not _NAME_RE.match(name):
        raise FinError(
            f"'{name}' is not a valid plug name — use lowercase letters, "
            "digits, '-' and '_' (e.g. 'laravel').",
            title="Invalid Argument",
        )
    return name


def _http_get(url: str) -> bytes:
    """GET *url*, mapping network failures to friendly FinErrors.

    A 404 propagates as ``urllib.error.HTTPError`` so callers can turn it
    into a context-aware NotFound; every other failure is terminal here.
    """
    try:
        with urllib.request.urlopen(
            url, timeout=TIMEOUT, context=_ssl_context()
        ) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise
        raise FinError(
            f"Plug catalog request failed (HTTP {exc.code}): {url}",
            exit_code=EXIT_SYSTEM,
            title="Network Error",
        ) from exc
    except urllib.error.URLError as exc:
        raise FinError(
            f"Could not reach the plug catalog ({exc.reason}). "
            "Check your internet connection.",
            exit_code=EXIT_SYSTEM,
            title="Network Error",
        ) from exc


def fetch_catalog() -> list[dict]:
    """Fetch and parse catalog.json; return its list of plug entries."""
    try:
        raw = _http_get(catalog_url())
    except urllib.error.HTTPError as exc:
        raise FinError(
            f"The plug catalog was not found at {catalog_url()}.",
            exit_code=EXIT_SYSTEM,
            title="Network Error",
        ) from exc
    try:
        data = json.loads(raw)
        plugs = data["plugs"]
        if not isinstance(plugs, list):
            raise TypeError("'plugs' is not a list")
    except (ValueError, KeyError, TypeError) as exc:
        raise FinError(
            f"The plug catalog at {catalog_url()} is malformed: {exc}",
            title="Catalog Error",
        ) from exc
    return plugs


def search_catalog(query: str) -> list[dict]:
    """Return catalog entries whose name or description matches *query*."""
    needle = query.lower()
    return [
        entry
        for entry in fetch_catalog()
        if needle in str(entry.get("name", "")).lower()
        or needle in str(entry.get("description", "")).lower()
    ]


def fetch_plug_source(name: str) -> str:
    """Fetch the source of ``plugs/<name>.py`` from the catalog repo.

    Raises :class:`NotFound` on 404, including did-you-mean suggestions when
    the catalog is reachable.
    """
    validate_name(name)
    try:
        return _http_get(plug_url(name)).decode("utf-8")
    except urllib.error.HTTPError as exc:  # only 404 escapes _http_get
        hint = ""
        suggestions = _suggest(name)
        if suggestions:
            hint = " Did you mean: " + ", ".join(suggestions) + "?"
        raise NotFound(
            f"No plug named '{name}' in the catalog ({Config.PLUGS_REPO_RAW}).{hint}"
        ) from exc


def _suggest(name: str) -> list[str]:
    """Best-effort close-name suggestions from the catalog; never raises."""
    try:
        names = [str(e.get("name", "")) for e in fetch_catalog()]
    except FinError:
        return []
    return difflib.get_close_matches(name, names, n=3, cutoff=0.6)
