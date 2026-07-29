"""Tests for fincli.commands.config_cmd — enable / disable / get / list."""

from __future__ import annotations


from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import config_cmd as cfg
from fincli.plugs.base import FinPlug, PlugType


class FakeAssetPlug(FinPlug):
    name = "mysql"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared MySQL"


class FakeLP:
    def __init__(self, instance, plug_type=PlugType.ASSET):
        self.instance = instance
        self.plug_type = plug_type


def test_config_list_empty(monkeypatch):
    monkeypatch.setattr(cfg, "load_all", lambda: [])
    assert cfg.config(["list"]) == EXIT_OK
    assert cfg.config([]) == EXIT_OK  # default subcommand


def test_config_list_with_assets(monkeypatch):
    monkeypatch.setattr(cfg, "load_all", lambda: [FakeLP(FakeAssetPlug())])
    monkeypatch.setattr(cfg, "is_asset_enabled", lambda n: True)
    assert cfg.config(["list"]) == EXIT_OK


def test_config_enable_requires_target(monkeypatch):
    assert cfg.config(["enable"]) == EXIT_USER


def test_config_enable_unknown_asset(monkeypatch):
    monkeypatch.setattr(cfg, "load_by_name", lambda n: None)
    assert cfg.config(["enable", "ghost"]) == EXIT_USER


def test_config_enable(monkeypatch):
    captured = {}
    monkeypatch.setattr(cfg, "load_by_name", lambda n: FakeLP(FakeAssetPlug()))
    monkeypatch.setattr(
        cfg, "set_asset_enabled", lambda name, val: captured.update(name=name, val=val)
    )
    assert cfg.config(["enable", "mysql"]) == EXIT_OK
    assert captured == {"name": "mysql", "val": True}


def test_config_disable(monkeypatch):
    captured = {}
    monkeypatch.setattr(cfg, "load_by_name", lambda n: FakeLP(FakeAssetPlug()))
    monkeypatch.setattr(
        cfg, "set_asset_enabled", lambda name, val: captured.update(name=name, val=val)
    )
    assert cfg.config(["disable", "mysql"]) == EXIT_OK
    assert captured["val"] is False


def test_config_rejects_non_asset_plug(monkeypatch):
    monkeypatch.setattr(
        cfg, "load_by_name", lambda n: FakeLP(FakeAssetPlug(), plug_type=PlugType.APP)
    )
    assert cfg.config(["enable", "laravel"]) == EXIT_USER


def test_config_get(monkeypatch):
    monkeypatch.setattr(cfg, "load_by_name", lambda n: FakeLP(FakeAssetPlug()))
    monkeypatch.setattr(cfg, "is_asset_enabled", lambda n: True)
    assert cfg.config(["get", "mysql"]) == EXIT_OK


def test_config_get_unknown(monkeypatch):
    monkeypatch.setattr(cfg, "load_by_name", lambda n: None)
    assert cfg.config(["get", "ghost"]) == EXIT_USER


def test_config_unknown_subcommand(monkeypatch):
    assert cfg.config(["frobnicate"]) == EXIT_USER
