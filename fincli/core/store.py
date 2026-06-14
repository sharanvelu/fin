"""Persisted, system-wide toggle store (JSON at ``~/.fin/config.json``).

Currently tracks which asset plugs are enabled to auto-start with ``fin up``.
Kept deliberately tiny and dependency-free so it is safe to read/write often.
"""

from __future__ import annotations

import json
from typing import Any

from fincli.config import Config


def _read() -> dict[str, Any]:
    Config.ensure_dirs()
    if not Config.CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(Config.CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict[str, Any]) -> None:
    Config.ensure_dirs()
    Config.CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def enabled_assets() -> dict[str, bool]:
    """Return the asset enable/disable map (asset name → bool)."""
    data = _read()
    return dict(data.get("assets", {}))


def is_asset_enabled(name: str) -> bool:
    """Whether an asset is enabled. Unknown assets default to disabled."""
    return bool(enabled_assets().get(name, False))


def set_asset_enabled(name: str, value: bool) -> None:
    """Enable or disable an asset for auto-start."""
    data = _read()
    assets = data.setdefault("assets", {})
    assets[name] = bool(value)
    _write(data)
