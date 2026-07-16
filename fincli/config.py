"""Tool-wide configuration for Fin.

Everything here is *system* configuration (paths, network name, shared asset
credentials, label keys) as opposed to *project* configuration, which is read
from the project's ``.env`` file (see :mod:`fincli.core.env`).

The values are intentionally centralised so they can be changed in one place.
In particular ``PLUGS_DIR`` is expected to be re-pointed after development —
set the ``FIN_PLUGS_DIR`` environment variable, or edit the default below.
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
    #: The Docker network every Fin-managed container joins.
    NETWORK: str = os.environ.get("FIN_NETWORK", "fin")

    # --- Filesystem locations ----------------------------------------------
    #: Root of the installed Fin source tree (set by the `fin` launcher).
    ROOT_DIR: Path = _env_path(
        "FIN_ROOT", Path(__file__).resolve().parent.parent
    )

    #: Per-user data directory for Fin (config, sqlite registry, certs).
    DATA_DIR: Path = _env_path("FIN_DATA_DIR", Path.home() / ".fin")

    #: Directory holding installed plugs, grouped by type:
    #: ``plugs/App``, ``plugs/Asset``, ``plugs/Global``.
    #:
    #: NOTE: This defaults to the bundled ``plugs/`` dir inside the repo for
    #: development. Re-point it later via the ``FIN_PLUGS_DIR`` env var or by
    #: editing this default.
    PLUGS_DIR: Path = _env_path("FIN_PLUGS_DIR", ROOT_DIR / "plugs")

    #: Sub-directories of :attr:`PLUGS_DIR`, one per plug type.
    PLUG_TYPE_DIRS: dict[str, str] = {
        "APP": "App",
        "ASSET": "Asset",
        "GLOBAL": "Global",
    }

    #: SQLite registry caching installed-plug metadata for fast lookup.
    REGISTRY_DB: Path = _env_path("FIN_REGISTRY_DB", DATA_DIR / "registry.db")

    #: Persisted per-asset enable/disable flags (see `fin config`).
    CONFIG_FILE: Path = _env_path("FIN_CONFIG_FILE", DATA_DIR / "config.json")

    # --- Shared asset defaults ---------------------------------------------
    #: Credentials baked into the shared asset containers (DB/redis).
    ASSET_USERNAME: str = os.environ.get("FIN_ASSET_USERNAME", "fin")
    ASSET_PASSWORD: str = os.environ.get("FIN_ASSET_PASSWORD", "password")
    ASSET_DEFAULT_DATABASE: str = os.environ.get(
        "FIN_ASSET_DEFAULT_DATABASE", "fin"
    )

    # --- Label keys ---------------------------------------------------------
    #: Every Fin container carries these labels. Values are documented in
    #: :mod:`fincli.core.containers`.
    LABEL_TYPE: str = "FIN_TYPE"          # app | asset | global | proxy
    LABEL_SERVICE: str = "FIN_SERVICE"    # web | mysql | redis | postgres ...
    LABEL_SITE: str = "FIN_SITE"          # the routed URL, or "-"
    LABEL_PROJECT: str = "FIN_PROJECT"    # project name (cwd basename)
    LABEL_MANAGED: str = "FIN_MANAGED"    # always "true" — the master filter

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
        ``config.json`` and ``registry.db``. Resolved lazily (and honouring
        ``FIN_CERTS_DIR``) so it follows a re-pointed :attr:`DATA_DIR`.
        """
        return _env_path("FIN_CERTS_DIR", cls.DATA_DIR / "certs")

    @classmethod
    def plug_type_dir(cls, plug_type: str) -> Path:
        """Return the directory for a given plug type (APP/ASSET/GLOBAL)."""
        sub = cls.PLUG_TYPE_DIRS.get(plug_type.upper(), plug_type)
        return cls.PLUGS_DIR / sub
