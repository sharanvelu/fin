"""Tests for the bundled plugs (Laravel app + MySQL/Redis/Postgres assets).

These load the *real* bundled plugs/ directory by name, exercising the plug
contracts (env spec, primary/asset specs, command maps).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fincli.config import Config
from fincli.core.env import ProjectEnv
from fincli.plugs.base import PlugType
from fincli.plugs.loader import load_by_name

BUNDLED = Path(__file__).resolve().parent.parent / "plugs"


@pytest.fixture
def bundled_plugs(monkeypatch):
    monkeypatch.setattr(Config, "PLUGS_DIR", BUNDLED)
    return BUNDLED


def _env(tmp_path, **values):
    return ProjectEnv(cwd=tmp_path, values=dict(values))


def test_laravel_loads(bundled_plugs):
    lp = load_by_name("laravel")
    assert lp is not None
    assert lp.plug_type is PlugType.APP
    assert lp.instance.name == "laravel"


def test_laravel_env_spec(bundled_plugs):
    lp = load_by_name("laravel")
    spec = lp.instance.env_spec()
    names = {v.name for v in spec.variables}
    assert "FIN_SITE" in names
    assert "FIN_PHP_VERSION" in names
    assert "FIN_COMPOSER_VERSION" in names
    # FIN_SITE is required
    site_var = next(v for v in spec.variables if v.name == "FIN_SITE")
    assert site_var.required is True


def test_laravel_primary_spec(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    spec = lp.instance.primary_spec(_env(tmp_path, FIN_SITE="app.localhost", FIN_PHP_VERSION="8.3"))
    assert spec.service == "web"
    assert spec.image == "sharanvelu/laravel-php:8.3"
    assert spec.web_exposed is True
    assert spec.web_port == 80
    assert spec.workdir_mount == "/var/www/html"


def test_laravel_primary_spec_custom_image(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    spec = lp.instance.primary_spec(_env(tmp_path, FIN_DOCKER_IMAGE="custom/image:tag"))
    assert spec.image == "custom/image:tag"


def test_laravel_commands(bundled_plugs):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    for name in ("artisan", "composer", "tinker", "migrate", "bash", "php"):
        assert name in cmds
    # artisan has an alias
    assert "art" in cmds["artisan"].aliases


class FakeCtx:
    """Records the args/kwargs a plug command handler passes to ctx.exec().

    Mirrors the real PlugContext.exec signature, including the ``interactive``
    kwarg used by REPL/shell handlers (tinker, bash).
    """

    def __init__(self):
        self.calls = []

    def exec(self, cmd, *, workdir=None, interactive=False):
        self.calls.append({"cmd": cmd, "workdir": workdir, "interactive": interactive})
        return 0


def test_laravel_artisan_handler_delegates(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()

    ctx = FakeCtx()
    rc = cmds["artisan"].handler(ctx, ["migrate", "--seed"])
    assert rc == 0
    assert ctx.calls[0]["cmd"] == ["php", "artisan", "migrate", "--seed"]
    assert ctx.calls[0]["workdir"] == "/var/www/html"


def test_laravel_migrate_subcommands(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()

    ctx = FakeCtx()
    cmds["migrate"].handler(ctx, ["fresh"])
    assert ctx.calls[0]["cmd"] == ["php", "artisan", "migrate:fresh"]


# --------------------------------------------------------------------------- #
# Interactive contract: REPL/shell handlers attach stdin; one-shots do not.
# --------------------------------------------------------------------------- #
def test_laravel_tinker_is_interactive(bundled_plugs):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["tinker"].handler(ctx, [])
    assert ctx.calls[0]["interactive"] is True


def test_laravel_bash_is_interactive(bundled_plugs):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["bash"].handler(ctx, [])
    assert ctx.calls[0]["interactive"] is True


@pytest.mark.parametrize("name,args", [("artisan", ["list"]), ("migrate", [])])
def test_laravel_oneshot_handlers_not_interactive(bundled_plugs, name, args):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds[name].handler(ctx, args)
    assert ctx.calls[0]["interactive"] is False


@pytest.mark.parametrize(
    "plug_name,expected_image,container_name",
    [
        ("mysql", "mysql:8.0", "fin_mysql"),
        ("postgres", "postgres:16-alpine", "fin_postgres"),
        ("redis", "redis:7-alpine", "fin_redis"),
    ],
)
def test_asset_plugs(bundled_plugs, tmp_path, plug_name, expected_image, container_name):
    lp = load_by_name(plug_name)
    assert lp is not None
    assert lp.plug_type is PlugType.ASSET
    specs = lp.instance.asset_specs(_env(tmp_path))
    assert len(specs) == 1
    spec = specs[0]
    assert spec.image == expected_image
    assert spec.container_name == container_name


@pytest.mark.parametrize(
    "plug_name,container_name,image",
    [
        ("postgres", "fin_postgres", "postgres:16-alpine"),
        ("redis", "fin_redis", "redis:7-alpine"),
    ],
)
def test_asset_spec_has_ports_and_volumes(
    bundled_plugs, tmp_path, plug_name, container_name, image
):
    lp = load_by_name(plug_name)
    spec = lp.instance.asset_specs(_env(tmp_path))[0]
    assert spec.container_name == container_name
    assert spec.image == image
    assert spec.ports  # at least one published port
    assert spec.volumes  # at least one persistent volume


def test_mysql_uses_config_credentials(bundled_plugs, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ASSET_USERNAME", "fin")
    monkeypatch.setattr(Config, "ASSET_PASSWORD", "password")
    lp = load_by_name("mysql")
    spec = lp.instance.asset_specs(_env(tmp_path))[0]
    assert spec.environment["MYSQL_USER"] == "fin"
    assert spec.environment["MYSQL_PASSWORD"] == "password"
