"""Tests for fincli.commands.asset — up / stop / down for shared assets."""

from __future__ import annotations


from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import asset as ac
from fincli.core.env import ProjectEnv

from conftest import make_fake_container


def _patch_env(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ac.ProjectEnv,
        "load",
        classmethod(lambda cls: ProjectEnv(cwd=tmp_path, values={})),
    )


def test_asset_up_default(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path)
    calls = {}
    monkeypatch.setattr(ac, "ensure_proxy", lambda: calls.setdefault("proxy", True))
    monkeypatch.setattr(ac, "start_assets_for", lambda env: [make_fake_container()])
    assert ac.asset([]) == EXIT_OK  # default subcommand is "up"
    assert calls["proxy"] is True


def test_asset_up_none_enabled(monkeypatch, tmp_path):
    _patch_env(monkeypatch, tmp_path)
    monkeypatch.setattr(ac, "ensure_proxy", lambda: None)
    monkeypatch.setattr(ac, "start_assets_for", lambda env: [])
    assert ac.asset(["up"]) == EXIT_OK


def test_asset_stop_no_containers(monkeypatch):
    monkeypatch.setattr(ac, "list_containers", lambda **kw: [])
    assert ac.asset(["stop"]) == EXIT_OK


def test_asset_stop_running(monkeypatch):
    c = make_fake_container(name="fin_mysql", status="running")
    monkeypatch.setattr(ac, "list_containers", lambda **kw: [c])
    assert ac.asset(["stop"]) == EXIT_OK
    c.stop.assert_called_once()
    c.remove.assert_not_called()


def test_asset_down_removes(monkeypatch):
    c = make_fake_container(name="fin_mysql", status="running")
    monkeypatch.setattr(ac, "list_containers", lambda **kw: [c])
    assert ac.asset(["down"]) == EXIT_OK
    c.remove.assert_called_once()


def test_asset_down_filters_asset_type(monkeypatch):
    captured = {}
    monkeypatch.setattr(ac, "list_containers", lambda **kw: captured.update(kw) or [])
    ac.asset(["down"])
    assert captured["FIN_TYPE"] == "asset"
    assert captured["all_"] is True


def test_asset_unknown_subcommand(monkeypatch):
    assert ac.asset(["frobnicate"]) == EXIT_USER


def test_asset_stop_continues_on_error(monkeypatch):
    bad = make_fake_container(name="fin_bad", status="running")
    bad.stop.side_effect = Exception("nope")
    good = make_fake_container(name="fin_good", status="running")
    monkeypatch.setattr(ac, "list_containers", lambda **kw: [bad, good])
    assert ac.asset(["stop"]) == EXIT_OK
    good.stop.assert_called_once()
