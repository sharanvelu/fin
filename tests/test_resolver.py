"""Tests for fincli.resolver — command resolution precedence.

reserved > FIN_APP > FIN_PLUGS > GLOBAL; unknown -> None.
"""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.core.env import ProjectEnv
from fincli.resolver import resolve
from fincli.commands import load_reserved


@pytest.fixture
def plugs_dir(tmp_path, monkeypatch):
    d = tmp_path / "plugs"
    for sub in ("App", "Asset", "Global"):
        (d / sub).mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", d)
    return d


def _make_env(cwd, **values):
    return ProjectEnv(cwd=cwd, values=dict(values))


def test_resolve_reserved_command(plugs_dir, tmp_path):
    load_reserved()
    res = resolve("up", [], _make_env(tmp_path))
    assert res is not None
    assert res.kind == "reserved"
    assert res.source == "system"


def test_resolve_unknown_returns_none(plugs_dir, tmp_path):
    res = resolve("definitely-not-a-command", [], _make_env(tmp_path))
    assert res is None


def test_resolve_plug_command(plugs_dir, plug_factory, tmp_path):
    body = """
    def commands(self):
        return {"hello": PlugCommand("hello", lambda ctx, args: 42)}
"""
    plug_factory(
        plugs_dir,
        type_sub="App",
        name="myapp",
        class_name="MyApp",
        plug_type="APP",
        body_extra=body,
    )
    env = _make_env(tmp_path, FIN_APP="myapp")
    res = resolve("hello", [], env)
    assert res is not None
    assert res.kind == "plug"
    assert res.source == "myapp"
    assert res.run() == 42


def test_reserved_beats_plug_of_same_name(plugs_dir, plug_factory, tmp_path):
    # Plug also defines an "up" command, but reserved must win.
    body = """
    def commands(self):
        return {"up": PlugCommand("up", lambda ctx, args: 999)}
"""
    plug_factory(
        plugs_dir,
        type_sub="App",
        name="myapp",
        class_name="MyApp",
        plug_type="APP",
        body_extra=body,
    )
    env = _make_env(tmp_path, FIN_APP="myapp")
    res = resolve("up", [], env)
    assert res.kind == "reserved"
    assert res.source == "system"


def test_resolve_plug_alias(plugs_dir, plug_factory, tmp_path):
    body = """
    def commands(self):
        return {"hello": PlugCommand("hello", lambda ctx, args: 7, aliases=("hi",))}
"""
    plug_factory(
        plugs_dir,
        type_sub="App",
        name="myapp",
        class_name="MyApp",
        plug_type="APP",
        body_extra=body,
    )
    env = _make_env(tmp_path, FIN_APP="myapp")
    res = resolve("hi", [], env)
    assert res is not None
    assert res.run() == 7


def test_resolve_global_plug(plugs_dir, plug_factory, tmp_path):
    body = """
    def commands(self):
        return {"gcmd": PlugCommand("gcmd", lambda ctx, args: 5)}
"""
    plug_factory(
        plugs_dir,
        type_sub="Global",
        name="gtool",
        class_name="GTool",
        plug_type="GLOBAL",
        body_extra=body,
    )
    env = _make_env(tmp_path)  # no FIN_APP
    res = resolve("gcmd", [], env)
    assert res is not None
    assert res.source == "gtool"
    assert res.run() == 5


def test_resolve_passes_args_to_handler(plugs_dir, plug_factory, tmp_path):
    body = """
    def commands(self):
        return {"echo": PlugCommand("echo", lambda ctx, args: len(args))}
"""
    plug_factory(
        plugs_dir,
        type_sub="App",
        name="myapp",
        class_name="MyApp",
        plug_type="APP",
        body_extra=body,
    )
    env = _make_env(tmp_path, FIN_APP="myapp")
    res = resolve("echo", ["a", "b", "c"], env)
    assert res.run() == 3


def test_fin_plugs_aux_resolution(plugs_dir, plug_factory, tmp_path):
    body = """
    def commands(self):
        return {"auxcmd": PlugCommand("auxcmd", lambda ctx, args: 11)}
"""
    plug_factory(
        plugs_dir,
        type_sub="Asset",
        name="auxplug",
        class_name="Aux",
        plug_type="ASSET",
        body_extra=body,
    )
    env = _make_env(tmp_path, FIN_PLUGS="auxplug")
    res = resolve("auxcmd", [], env)
    assert res is not None
    assert res.source == "auxplug"
