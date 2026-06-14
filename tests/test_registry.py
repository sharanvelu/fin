"""Tests for fincli.plugs.registry — sqlite cache over the plug tree."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.core.errors import FinError, NotFound
from fincli.plugs.registry import Registry, _looks_like_git, _repo_basename


@pytest.fixture
def registry(tmp_path, monkeypatch, plug_factory):
    """A Registry backed by a tmp sqlite db over a tmp plug tree with 3 plugs."""
    plugs = tmp_path / "plugs"
    for sub in ("App", "Asset", "Global"):
        (plugs / sub).mkdir(parents=True)
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs)
    monkeypatch.setattr(Config, "REGISTRY_DB", tmp_path / "registry.db")

    plug_factory(plugs, type_sub="App", name="laravel", class_name="Laravel",
                 plug_type="APP", description="Laravel app")
    plug_factory(plugs, type_sub="Asset", name="mysql", class_name="MySQL",
                 plug_type="ASSET", description="MySQL db")
    plug_factory(plugs, type_sub="Asset", name="redis", class_name="Redis",
                 plug_type="ASSET", description="Redis")

    reg = Registry()
    yield reg
    reg.close()


def test_sync_returns_count(registry):
    assert registry.sync() == 3


def test_all_returns_records(registry):
    records = registry.all()
    names = {r.name for r in records}
    assert names == {"laravel", "mysql", "redis"}


def test_all_record_fields(registry):
    records = {r.name: r for r in registry.all()}
    mysql = records["mysql"]
    assert mysql.version == "1.0.0"
    assert mysql.plug_type == "ASSET"
    assert mysql.description == "MySQL db"
    assert "mysql" in mysql.path


def test_all_ordered_by_type_then_name(registry):
    records = registry.all()
    # APP < ASSET alphabetically; within ASSET, mysql < redis.
    assert [r.name for r in records] == ["laravel", "mysql", "redis"]


def test_by_type_filters(registry):
    assets = registry.by_type("ASSET")
    assert {r.name for r in assets} == {"mysql", "redis"}
    apps = registry.by_type("app")  # case-insensitive
    assert {r.name for r in apps} == {"laravel"}


def test_get_found(registry):
    r = registry.get("laravel")
    assert r.name == "laravel"
    assert r.plug_type == "APP"


def test_get_missing_raises_notfound(registry):
    with pytest.raises(NotFound):
        registry.get("ghost")


def test_search_raises_not_implemented(registry):
    with pytest.raises(FinError) as exc:
        registry.search("anything")
    assert exc.value.title == "Not Implemented"


def test_sync_refreshes_on_change(registry, tmp_path, plug_factory):
    registry.sync()
    assert len(registry.all(refresh=False)) == 3
    # Add a global plug and re-sync.
    plug_factory(Config.PLUGS_DIR, type_sub="Global", name="extra",
                 class_name="Extra", plug_type="GLOBAL")
    assert registry.sync() == 4
    assert len(registry.all(refresh=False)) == 4


def test_uninstall_removes_dir_and_resyncs(registry):
    path = registry.uninstall("redis")
    assert not path.exists()
    with pytest.raises(NotFound):
        registry.get("redis", refresh=False)


def test_install_without_url_raises(registry):
    with pytest.raises(FinError) as exc:
        registry.install("somename")
    assert exc.value.title == "Not Implemented"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://github.com/u/r", True),
        ("http://x/y", True),
        ("git@github.com:u/r.git", True),
        ("ssh://git@host/r", True),
        ("repo.git", True),
        ("plainname", False),
    ],
)
def test_looks_like_git(value, expected):
    assert _looks_like_git(value) is expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/u/myplug.git", "myplug"),
        ("https://github.com/u/myplug", "myplug"),
        ("git@github.com:u/other.git", "other"),
        ("https://x/y/trailing/", "trailing"),
    ],
)
def test_repo_basename(url, expected):
    assert _repo_basename(url) == expected
