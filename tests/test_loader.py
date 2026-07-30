"""Tests for fincli.plugs.loader — discovery of flat <name>.py plug files."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.plugs.base import PlugType
from fincli.plugs.loader import (
    LoadedPlug,
    load_all,
    load_by_name,
    load_plug_file,
)


@pytest.fixture
def plugs_dir(tmp_path, monkeypatch):
    """A fresh PLUGS_DIR pointed at an empty tmp directory."""
    d = tmp_path / "plugs"
    d.mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", d)
    return d


def test_load_all_finds_dummy_app_plug(plugs_dir, plug_factory):
    path = plug_factory(
        plugs_dir,
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
    assert lp.plug_type is PlugType.APP  # from the declared plug_type
    assert lp.instance.description == "a dummy app"
    assert lp.path == path  # the real .py file


def test_load_all_explicit_dir_argument(plugs_dir, plug_factory):
    plug_factory(plugs_dir, name="cache", class_name="CachePlug", plug_type="ASSET")
    loaded = load_all(plugs_dir)
    assert [lp.name for lp in loaded] == ["cache"]
    assert loaded[0].plug_type is PlugType.ASSET


def test_load_all_multiple_types(plugs_dir, plug_factory):
    plug_factory(plugs_dir, name="webapp", class_name="WebApp", plug_type="APP")
    plug_factory(plugs_dir, name="db", class_name="Db", plug_type="ASSET")
    plug_factory(plugs_dir, name="tool", class_name="Tool", plug_type="GLOBAL")
    loaded = load_all()
    names = {lp.name: lp.plug_type for lp in loaded}
    assert names == {
        "webapp": PlugType.APP,
        "db": PlugType.ASSET,
        "tool": PlugType.GLOBAL,
    }


def test_load_all_skips_underscore_dot_and_non_py(plugs_dir, plug_factory):
    plug_factory(plugs_dir, name="real", class_name="Real", plug_type="APP")
    (plugs_dir / "_helper.py").write_text("X = 1\n")
    (plugs_dir / ".hidden.py").write_text("X = 1\n")
    (plugs_dir / "notes.txt").write_text("not a plug\n")
    (plugs_dir / "somedir").mkdir()  # directories are not plugs any more
    loaded = load_all()
    assert [lp.name for lp in loaded] == ["real"]


def test_load_plug_file_no_finplug_subclass(plugs_dir):
    py = plugs_dir / "broken.py"
    py.write_text("X = 1\n")
    assert load_plug_file(py) is None


def test_load_plug_file_import_error_returns_none(plugs_dir):
    py = plugs_dir / "syntaxerr.py"
    py.write_text("def (:\n")  # syntax error
    assert load_plug_file(py) is None


def test_load_plug_file_setup_failure_returns_none(plugs_dir):
    py = plugs_dir / "badsetup.py"
    py.write_text(
        "from fincli.plugs.base import FinPlug, PlugType\n"
        "class BadSetup(FinPlug):\n"
        "    name='bad'\n"
        "    plug_type=PlugType.APP\n"
        "    def setup(self):\n"
        "        raise RuntimeError('boom')\n"
    )
    assert load_plug_file(py) is None


def test_load_by_name_filename_match(plugs_dir, plug_factory):
    plug_factory(plugs_dir, name="laravel", class_name="Laravel", plug_type="APP")
    lp = load_by_name("laravel")
    assert lp is not None
    assert lp.name == "laravel"


def test_load_by_name_unknown_returns_none(plugs_dir):
    assert load_by_name("nope") is None


def test_load_by_name_fallback_to_declared_name(plugs_dir):
    # File name differs from the declared plug name.
    (plugs_dir / "filename.py").write_text(
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
    (plugs_dir / "importer.py").write_text(
        "from fincli.plugs.base import FinPlug  # imported, not subclassed\nVALUE = 1\n"
    )
    assert load_all() == []


def test_one_bad_plug_never_hides_the_others(plugs_dir, plug_factory):
    plug_factory(plugs_dir, name="good", class_name="Good", plug_type="APP")
    (plugs_dir / "bad.py").write_text("def (:\n")  # syntax error
    assert [lp.name for lp in load_all()] == ["good"]
