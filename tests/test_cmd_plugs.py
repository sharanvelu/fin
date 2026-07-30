"""Tests for fincli.commands.plugs_cmd — list / info / search / install / uninstall."""

from __future__ import annotations

import pytest

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import plugs_cmd as pc
from fincli.config import Config
from fincli.core.errors import FinError, NotFound


@pytest.fixture
def populated_plugs(tmp_path, monkeypatch, plug_factory):
    plugs = tmp_path / "plugs"
    plugs.mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs)
    monkeypatch.setattr(Config, "REGISTRY_DB", tmp_path / "registry.db")
    plug_factory(
        plugs,
        name="laravel",
        class_name="Laravel",
        plug_type="APP",
        description="Laravel app",
    )
    plug_factory(
        plugs,
        name="mysql",
        class_name="MySQL",
        plug_type="ASSET",
        description="MySQL",
    )
    return plugs


def test_plugs_list_empty(tmp_path, monkeypatch):
    plugs = tmp_path / "plugs"
    plugs.mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs)
    monkeypatch.setattr(Config, "REGISTRY_DB", tmp_path / "registry.db")
    assert pc.plugs(["list"]) == EXIT_OK
    assert pc.plugs([]) == EXIT_OK  # default subcommand


def test_plugs_list_populated(populated_plugs):
    assert pc.plugs(["list"]) == EXIT_OK
    assert pc.plugs(["ls"]) == EXIT_OK


def test_plugs_info(populated_plugs):
    assert pc.plugs(["info", "laravel"]) == EXIT_OK


def test_plugs_info_requires_name(populated_plugs):
    assert pc.plugs(["info"]) == EXIT_USER


def test_plugs_info_unknown_raises_notfound(populated_plugs):
    with pytest.raises(NotFound):
        pc.plugs(["info", "ghost"])


def test_plugs_search_requires_query(populated_plugs):
    assert pc.plugs(["search"]) == EXIT_USER


def test_plugs_search_renders_catalog_results(populated_plugs, monkeypatch):
    from fincli.plugs import catalog

    entries = [
        {"name": "laravel", "type": "APP", "version": "1.0.0", "description": "PHP"},
        {"name": "postgres", "type": "ASSET", "version": "1.0.0", "description": "DB"},
    ]
    monkeypatch.setattr(catalog, "fetch_catalog", lambda: entries)
    assert pc.plugs(["search", "a"]) == EXIT_OK


def test_plugs_search_no_matches_is_ok(populated_plugs, monkeypatch):
    from fincli.plugs import catalog

    monkeypatch.setattr(catalog, "fetch_catalog", lambda: [])
    assert pc.plugs(["search", "ghost"]) == EXIT_OK


def test_plugs_search_offline_raises_network_error(populated_plugs, monkeypatch):
    from fincli.plugs import catalog

    def boom():
        raise FinError("offline", title="Network Error")

    monkeypatch.setattr(catalog, "fetch_catalog", boom)
    with pytest.raises(FinError) as exc:
        pc.plugs(["search", "anything"])
    assert exc.value.title == "Network Error"


def test_plugs_install_requires_name(populated_plugs):
    assert pc.plugs(["install"]) == EXIT_USER


def test_plugs_install_from_catalog(populated_plugs, monkeypatch):
    from conftest import plug_source

    from fincli.plugs import catalog

    monkeypatch.setattr(
        catalog,
        "fetch_plug_source",
        lambda name: plug_source(name=name, class_name="Redis", plug_type="ASSET"),
    )
    assert pc.plugs(["install", "redis"]) == EXIT_OK
    assert (populated_plugs / "redis.py").is_file()


def test_plugs_install_unknown_raises(populated_plugs, monkeypatch):
    from fincli.plugs import catalog

    def raise_not_found(name):
        raise NotFound(f"No plug named '{name}' in the catalog.")

    monkeypatch.setattr(catalog, "fetch_plug_source", raise_not_found)
    with pytest.raises(NotFound):
        pc.plugs(["install", "plainname"])


def test_plugs_uninstall_requires_name(populated_plugs):
    assert pc.plugs(["uninstall"]) == EXIT_USER


def test_plugs_uninstall_removes(populated_plugs):
    assert pc.plugs(["uninstall", "mysql"]) == EXIT_OK
    # The mysql plug file should be gone now.
    assert not (populated_plugs / "mysql.py").exists()


def test_plugs_unknown_subcommand(populated_plugs):
    assert pc.plugs(["frobnicate"]) == EXIT_USER
