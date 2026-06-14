"""Tests for fincli.core.store — asset enable/disable persistence."""

from __future__ import annotations

import json

from fincli.config import Config
from fincli.core import store


# isolate_config (autouse) already points Config.CONFIG_FILE at a tmp dir.


def test_enabled_assets_empty_when_no_file():
    assert not Config.CONFIG_FILE.exists()
    assert store.enabled_assets() == {}


def test_is_asset_enabled_defaults_false():
    assert store.is_asset_enabled("mysql") is False


def test_set_and_get_enabled():
    store.set_asset_enabled("mysql", True)
    assert store.is_asset_enabled("mysql") is True
    assert store.enabled_assets() == {"mysql": True}


def test_disable_after_enable():
    store.set_asset_enabled("redis", True)
    store.set_asset_enabled("redis", False)
    assert store.is_asset_enabled("redis") is False


def test_persists_to_disk():
    store.set_asset_enabled("postgres", True)
    assert Config.CONFIG_FILE.exists()
    data = json.loads(Config.CONFIG_FILE.read_text())
    assert data["assets"]["postgres"] is True


def test_multiple_assets_coexist():
    store.set_asset_enabled("mysql", True)
    store.set_asset_enabled("redis", False)
    store.set_asset_enabled("postgres", True)
    assert store.enabled_assets() == {"mysql": True, "redis": False, "postgres": True}


def test_corrupt_file_returns_empty():
    Config.ensure_dirs()
    Config.CONFIG_FILE.write_text("{ not valid json")
    assert store.enabled_assets() == {}


def test_set_creates_data_dir():
    # DATA_DIR does not exist yet under the tmp isolation.
    assert not Config.DATA_DIR.exists()
    store.set_asset_enabled("mysql", True)
    assert Config.DATA_DIR.exists()


def test_set_value_coerced_to_bool():
    store.set_asset_enabled("mysql", 1)  # truthy non-bool
    data = json.loads(Config.CONFIG_FILE.read_text())
    assert data["assets"]["mysql"] is True
