"""Tests for fincli.plugs.registry — sqlite cache over the plug tree."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.core.errors import FinError, NotFound
from fincli.plugs.registry import Registry, _looks_like_git


@pytest.fixture
def registry(tmp_path, monkeypatch, plug_factory):
    """A Registry backed by a tmp sqlite db over a tmp plug tree with 3 plugs."""
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
        description="MySQL db",
    )
    plug_factory(
        plugs,
        name="redis",
        class_name="Redis",
        plug_type="ASSET",
        description="Redis",
    )

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


def test_search_filters_catalog_and_flags_installed(registry, monkeypatch):
    from fincli.plugs import catalog

    entries = [
        {"name": "laravel", "type": "APP", "description": "Laravel app"},
        {"name": "postgres", "type": "ASSET", "description": "Postgres db"},
    ]
    monkeypatch.setattr(catalog, "fetch_catalog", lambda: entries)
    results = registry.search("e")  # matches both names
    by_name = {e["name"]: e for e in results}
    assert by_name["laravel"]["installed"] is True  # in the fixture tree
    assert by_name["postgres"]["installed"] is False


def test_search_propagates_network_error(registry, monkeypatch):
    from fincli.plugs import catalog

    def boom():
        raise FinError("no network", title="Network Error")

    monkeypatch.setattr(catalog, "fetch_catalog", boom)
    with pytest.raises(FinError) as exc:
        registry.search("anything")
    assert exc.value.title == "Network Error"


def test_sync_refreshes_on_change(registry, tmp_path, plug_factory):
    registry.sync()
    assert len(registry.all(refresh=False)) == 3
    # Add a global plug and re-sync.
    plug_factory(
        Config.PLUGS_DIR,
        name="extra",
        class_name="Extra",
        plug_type="GLOBAL",
    )
    assert registry.sync() == 4
    assert len(registry.all(refresh=False)) == 4


def test_uninstall_removes_file_and_resyncs(registry):
    path = registry.uninstall("redis")
    assert not path.exists()
    with pytest.raises(NotFound):
        registry.get("redis", refresh=False)


def test_uninstall_removes_flat_file(registry, plug_factory):
    plug_factory(
        Config.PLUGS_DIR, name="flatty", class_name="Flatty", plug_type="GLOBAL"
    )
    registry.sync()
    path = registry.uninstall("flatty")
    assert path == Config.PLUGS_DIR / "flatty.py"
    assert not path.exists()


# --------------------------------------------------------------------------- #
# catalog install
# --------------------------------------------------------------------------- #
def _catalog_source(name="postgres", class_name="Postgres", plug_type="ASSET"):
    from conftest import plug_source

    return plug_source(name=name, class_name=class_name, plug_type=plug_type)


def test_install_from_catalog_writes_flat_file(registry, monkeypatch):
    from fincli.plugs import catalog

    monkeypatch.setattr(
        catalog, "fetch_plug_source", lambda name: _catalog_source(name=name)
    )
    dest = registry.install("postgres")
    assert dest == Config.PLUGS_DIR / "postgres.py"
    assert dest.is_file()
    record = registry.get("postgres")
    assert record.plug_type == "ASSET"
    assert record.path == str(dest)


def test_install_from_catalog_rejects_invalid_source(registry, monkeypatch):
    from fincli.plugs import catalog

    monkeypatch.setattr(
        catalog, "fetch_plug_source", lambda name: "x = 1  # no FinPlug here"
    )
    with pytest.raises(FinError) as exc:
        registry.install("postgres")
    assert exc.value.title == "Invalid Plug"
    assert not (Config.PLUGS_DIR / "postgres.py").exists()


def test_install_from_catalog_rejects_name_mismatch(registry, monkeypatch):
    from fincli.plugs import catalog

    monkeypatch.setattr(
        catalog,
        "fetch_plug_source",
        lambda name: _catalog_source(name="other", class_name="Other"),
    )
    with pytest.raises(FinError) as exc:
        registry.install("postgres")
    assert exc.value.title == "Invalid Plug"
    assert not (Config.PLUGS_DIR / "postgres.py").exists()


def test_install_from_catalog_refuses_already_installed(registry, monkeypatch):
    from fincli.plugs import catalog

    monkeypatch.setattr(
        catalog,
        "fetch_plug_source",
        lambda name: pytest.fail("must not fetch when already installed"),
    )
    with pytest.raises(FinError) as exc:
        registry.install("laravel")  # installed by the fixture
    assert "already installed" in exc.value.message


def test_install_from_catalog_not_found(registry, monkeypatch):
    from fincli.plugs import catalog

    def raise_not_found(name):
        raise NotFound(f"No plug named '{name}' in the catalog.")

    monkeypatch.setattr(catalog, "fetch_plug_source", raise_not_found)
    with pytest.raises(NotFound):
        registry.install("ghost")


def test_install_rejects_invalid_name(registry):
    with pytest.raises(FinError) as exc:
        registry.install("Bad/../Name")
    assert exc.value.title == "Invalid Argument"


# --------------------------------------------------------------------------- #
# git install
# --------------------------------------------------------------------------- #
def _make_git_plug_repo(base, files: dict[str, str]):
    """Init a local git repo at *base* containing *files* (path → source)."""
    import subprocess

    base.mkdir(parents=True)
    for rel, source in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": __import__("os").environ["PATH"],
    }
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        ["git", "commit", "-q", "-m", "x"],
    ):
        subprocess.run(cmd, cwd=base, check=True, capture_output=True, env=env)
    return base


def test_install_from_git_single_plug(registry, tmp_path):
    repo = _make_git_plug_repo(
        tmp_path / "gitrepo",
        {"plugs/memcached.py": _catalog_source(name="memcached", class_name="Mc")},
    )
    dest = registry.install("ignored", repo_url=str(repo))
    assert dest == Config.PLUGS_DIR / "memcached.py"
    assert registry.get("memcached").plug_type == "ASSET"


def test_install_from_git_no_plug_raises(registry, tmp_path):
    repo = _make_git_plug_repo(tmp_path / "gitrepo", {"README.md": "hi"})
    with pytest.raises(FinError) as exc:
        registry.install("ignored", repo_url=str(repo))
    assert exc.value.title == "Invalid Plug"


def test_install_from_git_multiple_plugs_raises(registry, tmp_path):
    repo = _make_git_plug_repo(
        tmp_path / "gitrepo",
        {
            "plugs/one.py": _catalog_source(name="one", class_name="One"),
            "plugs/two.py": _catalog_source(name="two", class_name="Two"),
        },
    )
    with pytest.raises(FinError) as exc:
        registry.install("ignored", repo_url=str(repo))
    assert "multiple plugs" in exc.value.message


def test_install_from_git_refuses_already_installed(registry, tmp_path):
    repo = _make_git_plug_repo(
        tmp_path / "gitrepo",
        {"laravel.py": _catalog_source(name="laravel", class_name="Laravel")},
    )
    with pytest.raises(FinError) as exc:
        registry.install("ignored", repo_url=str(repo))
    assert "already installed" in exc.value.message


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
