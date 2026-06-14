"""Tests for fincli.plugs.loader — discovery via importlib of temp plug trees."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.plugs.base import PlugType
from fincli.plugs.loader import (
    LoadedPlug,
    load_all,
    load_by_name,
    load_plug_dir,
)


@pytest.fixture
def plugs_dir(tmp_path, monkeypatch):
    """A fresh PLUGS_DIR pointed at a tmp tree, with App/Asset/Global subdirs."""
    d = tmp_path / "plugs"
    for sub in ("App", "Asset", "Global"):
        (d / sub).mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", d)
    return d


def test_load_all_finds_dummy_app_plug(plugs_dir, plug_factory):
    plug_factory(
        plugs_dir,
        type_sub="App",
        name="dummy",
        class_name="DummyPlug",
        plug_type="APP",
        description="a dummy app",
    )
    loaded = load_all()
    assert len(loaded) == 1
    lp = loaded[0]
    assert isinstance(lp, LoadedPlug)
    assert lp.name == "dummy"
    assert lp.instance.name == "dummy"
    assert lp.plug_type is PlugType.APP
    assert lp.instance.description == "a dummy app"


def test_load_all_explicit_dir_argument(plugs_dir, plug_factory):
    plug_factory(plugs_dir, type_sub="Asset", name="cache", class_name="CachePlug", plug_type="ASSET")
    loaded = load_all(plugs_dir)
    assert [lp.name for lp in loaded] == ["cache"]
    assert loaded[0].plug_type is PlugType.ASSET


def test_load_all_multiple_types(plugs_dir, plug_factory):
    plug_factory(plugs_dir, type_sub="App", name="webapp", class_name="WebApp", plug_type="APP")
    plug_factory(plugs_dir, type_sub="Asset", name="db", class_name="Db", plug_type="ASSET")
    plug_factory(plugs_dir, type_sub="Global", name="tool", class_name="Tool", plug_type="GLOBAL")
    loaded = load_all()
    names = {lp.name: lp.plug_type for lp in loaded}
    assert names == {
        "webapp": PlugType.APP,
        "db": PlugType.ASSET,
        "tool": PlugType.GLOBAL,
    }


def test_load_all_skips_underscore_and_dot_dirs(plugs_dir, plug_factory):
    plug_factory(plugs_dir, type_sub="App", name="real", class_name="Real", plug_type="APP")
    (plugs_dir / "App" / "_hidden").mkdir()
    (plugs_dir / "App" / ".dotdir").mkdir()
    loaded = load_all()
    assert [lp.name for lp in loaded] == ["real"]


def test_load_plug_dir_no_finplug_subclass(plugs_dir):
    pkg = plugs_dir / "App" / "broken"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("X = 1\n")
    assert load_plug_dir(pkg, PlugType.APP) is None


def test_load_plug_dir_import_error_returns_none(plugs_dir):
    pkg = plugs_dir / "App" / "syntaxerr"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("def (:\n")  # syntax error
    assert load_plug_dir(pkg, PlugType.APP) is None


def test_load_plug_dir_setup_failure_returns_none(plugs_dir):
    pkg = plugs_dir / "App" / "badsetup"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "from fincli.plugs.base import FinPlug, PlugType\n"
        "class BadSetup(FinPlug):\n"
        "    name='bad'\n"
        "    plug_type=PlugType.APP\n"
        "    def setup(self):\n"
        "        raise RuntimeError('boom')\n"
    )
    assert load_plug_dir(pkg, PlugType.APP) is None


def test_load_by_name_directory_match(plugs_dir, plug_factory):
    plug_factory(plugs_dir, type_sub="App", name="laravel", class_name="Laravel", plug_type="APP")
    lp = load_by_name("laravel")
    assert lp is not None
    assert lp.name == "laravel"


def test_load_by_name_unknown_returns_none(plugs_dir):
    assert load_by_name("nope") is None


def test_load_by_name_app_before_asset_order(plugs_dir, plug_factory):
    # Same dir name in two types — App should be searched first.
    plug_factory(plugs_dir, type_sub="App", name="dup", class_name="DupApp", plug_type="APP")
    plug_factory(plugs_dir, type_sub="Asset", name="dup", class_name="DupAsset", plug_type="ASSET")
    lp = load_by_name("dup")
    assert lp.plug_type is PlugType.APP


def test_load_by_name_fallback_to_declared_name(plugs_dir, plug_factory):
    # Directory name differs from declared plug name.
    plug_factory(plugs_dir, type_sub="App", name="dirname", class_name="P", plug_type="APP")
    # overwrite declared name to something else
    (plugs_dir / "App" / "dirname" / "__init__.py").write_text(
        "from fincli.plugs.base import FinPlug, PlugType\n"
        "class P(FinPlug):\n"
        "    name='declaredname'\n"
        "    plug_type=PlugType.APP\n"
    )
    lp = load_by_name("declaredname")
    assert lp is not None
    assert lp.instance.name == "declaredname"


def test_load_all_only_counts_class_defined_in_module(plugs_dir):
    # A module that imports FinPlug but defines no subclass of its own.
    pkg = plugs_dir / "App" / "importer"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "from fincli.plugs.base import FinPlug  # imported, not subclassed\n"
        "VALUE = 1\n"
    )
    assert load_all() == []
