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
    for sub in ("App", "Asset", "Global"):
        (plugs / sub).mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs)
    monkeypatch.setattr(Config, "REGISTRY_DB", tmp_path / "registry.db")
    plug_factory(plugs, type_sub="App", name="laravel", class_name="Laravel",
                 plug_type="APP", description="Laravel app")
    plug_factory(plugs, type_sub="Asset", name="mysql", class_name="MySQL",
                 plug_type="ASSET", description="MySQL")
    return plugs


def test_plugs_list_empty(tmp_path, monkeypatch):
    plugs = tmp_path / "plugs"
    for sub in ("App", "Asset", "Global"):
        (plugs / sub).mkdir(parents=True)
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


def test_plugs_search_raises_not_implemented(populated_plugs):
    with pytest.raises(FinError) as exc:
        pc.plugs(["search", "anything"])
    assert exc.value.title == "Not Implemented"


def test_plugs_install_requires_name(populated_plugs):
    assert pc.plugs(["install"]) == EXIT_USER


def test_plugs_install_unknown_raises(populated_plugs):
    with pytest.raises(FinError):
        pc.plugs(["install", "plainname"])  # no git url, no catalog


def test_plugs_uninstall_requires_name(populated_plugs):
    assert pc.plugs(["uninstall"]) == EXIT_USER


def test_plugs_uninstall_removes(populated_plugs):
    assert pc.plugs(["uninstall", "mysql"]) == EXIT_OK
    # The mysql plug dir should be gone now.
    assert not (populated_plugs / "Asset" / "mysql").exists()


def test_plugs_unknown_subcommand(populated_plugs):
    assert pc.plugs(["frobnicate"]) == EXIT_USER
