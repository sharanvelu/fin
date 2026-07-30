"""Tool-wide configuration for Fin.

Everything here is *system* configuration (paths, network name, shared asset
credentials, label keys) as opposed to *project* configuration, which is read
from the project's ``.env`` file (see :mod:`fincli.core.env`).

The values are intentionally centralised so they can be changed in one place.
Plugs live under ``DATA_DIR/plugs`` (``~/.fin/plugs``) — a stable, writable,
per-user location, so a compiled binary can load user-installed plugs from the
host rather than from inside the bundle. For development, symlink your plugs
working tree there: ``ln -s <repo>/plugs ~/.fin/plugs``.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    """Read a path from the environment, falling back to *default*."""
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


class Config:
    """Singleton-style holder for Fin's system configuration.

    Access values as class attributes, e.g. ``Config.NETWORK``. Paths are
    resolved lazily from environment variables so tests can override them.
    """

    # --- Identity -----------------------------------------------------------
    #: The Docker network every Fin-managed container joins (fixed).
    NETWORK: str = "fin"

    # --- Filesystem locations ----------------------------------------------
    #: Per-user data directory for Fin (config, sqlite registry, certs, plugs).
    DATA_DIR: Path = _env_path("FIN_DATA_DIR", Path.home() / ".fin")

    #: Directory holding the plugs, one flat ``<name>.py`` file per plug.
    #: Fixed under DATA_DIR (``~/.fin/plugs``) — a stable host location so a
    #: compiled binary loads user-installed plugs from disk rather than from
    #: inside the bundle. For development, symlink the fin-plugs repo's
    #: ``plugs/`` directory here (``ln -s <fin-plugs repo>/plugs
    #: ~/.fin/plugs``).
    PLUGS_DIR: Path = DATA_DIR / "plugs"

    #: SQLite registry caching installed-plug metadata for fast lookup.
    REGISTRY_DB: Path = DATA_DIR / "registry.db"

    # --- Remote plug catalog -------------------------------------------------
    #: Raw-content base URL of the official plug repository (master branch).
    #: ``fin plugs install <name>`` fetches ``<base>/plugs/<name>.py``.
    #: Overridable for forks/mirrors and tests via ``FIN_PLUGS_REPO_RAW``.
    PLUGS_REPO_RAW: str = os.environ.get(
        "FIN_PLUGS_REPO_RAW",
        "https://raw.githubusercontent.com/sharanvelu/fin-plugs/master",
    )

    #: URL of the catalog index used by ``fin plugs search``. Published as a
    #: release asset of the plug repository (not committed to master); the
    #: ``releases/latest/download`` URL always redirects to the newest
    #: release's copy. Overridable via ``FIN_PLUGS_CATALOG_URL``.
    PLUGS_CATALOG_URL: str = os.environ.get(
        "FIN_PLUGS_CATALOG_URL",
        "https://github.com/sharanvelu/fin-plugs/releases/latest/download/catalog.json",
    )

    #: Persisted per-asset enable/disable flags (see `fin config`).
    CONFIG_FILE: Path = DATA_DIR / "config.json"

    # --- Shared asset defaults ---------------------------------------------
    #: Credentials baked into the shared asset containers (DB/redis).
    #: Fixed values (not env-overridable): these throwaway local-dev engines are
    #: shared across every project on the machine, so a project's .env points its
    #: DB_USERNAME/DB_PASSWORD at these.
    ASSET_USERNAME: str = "fin"
    ASSET_PASSWORD: str = "password"
    ASSET_DEFAULT_DATABASE: str = "fin"

    # --- Label keys ---------------------------------------------------------
    #: Every Fin container carries these labels. Values are documented in
    #: :mod:`fincli.core.containers`.
    LABEL_TYPE: str = "FIN_TYPE"  # app | asset | global | proxy
    LABEL_SERVICE: str = "FIN_SERVICE"  # web | mysql | redis | postgres ...
    LABEL_SITE: str = "FIN_SITE"  # the routed URL, or "-"
    LABEL_PROJECT: str = "FIN_PROJECT"  # project name (cwd basename)
    LABEL_MANAGED: str = "FIN_MANAGED"  # always "true" — the master filter

    # --- Proxy --------------------------------------------------------------
    #: Traefik proxy image and the container name it runs under.
    PROXY_IMAGE: str = os.environ.get("FIN_PROXY_IMAGE", "traefik:v3.6")
    PROXY_CONTAINER: str = "fin_proxy"
    #: Traefik entrypoints attached to every routed service.
    PROXY_ENTRYPOINTS: str = "web,websecure"

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create the data directory tree if it does not yet exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def certs_dir(cls) -> Path:
        """Directory of user CA certs Fin installs into opted-in containers.

        Reuses the per-user data root (``~/.fin``) that already holds
        ``config.json`` and ``registry.db``. Resolved lazily so it follows a
        re-pointed :attr:`DATA_DIR`.
        """
        return cls.DATA_DIR / "certs"

