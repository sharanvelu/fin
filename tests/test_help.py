"""Tests for the help system (overview + per-command help)."""

from __future__ import annotations

import pytest

from fincli import help as help_mod
from fincli import __main__ as main_mod
from fincli.app import EXIT_OK, EXIT_USER
from fincli.config import Config
from fincli.core.env import ProjectEnv

from conftest import write_plug


def _empty_env(tmp_path):
    return ProjectEnv(cwd=tmp_path, values={})


#: Body for a synthetic APP plug that contributes an `artisan` command (alias
#: `art`) plus a FIN_SITE env var — enough to exercise the plug-command help
#: renderer without depending on the external plugs repo.
_SYNTH_PLUG_BODY = '''
    def env_spec(self):
        from fincli.core.env import EnvSpec, EnvVar
        return EnvSpec.of([
            EnvVar("FIN_SITE", required=True, description="hostname the app is served at"),
        ])

    def commands(self):
        def _artisan(ctx, args):
            return 0
        return {
            "artisan": PlugCommand(
                "artisan", _artisan, "Run an artisan command.", aliases=("art",)
            ),
        }
'''


@pytest.fixture
def synthetic_plug(tmp_path, monkeypatch):
    """Point Config.PLUGS_DIR at a hermetic synthetic 'laravel' plug.

    The help *renderer* is what's under test; we only need *a* plug that
    contributes a command (with an alias) and an env spec. Overrides the autouse
    `isolate_config` empty-dir so the plug and its commands are discoverable.
    """
    plugs_dir = tmp_path / "plugs"
    write_plug(
        plugs_dir,
        type_sub="App",
        name="laravel",
        class_name="LaravelPlug",
        plug_type="APP",
        description="Laravel / PHP application runtime.",
        body_extra=_SYNTH_PLUG_BODY,
    )
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs_dir)
    yield


# --------------------------------------------------------------------------- #
# wants_help
# --------------------------------------------------------------------------- #
def test_wants_help_detects_flags():
    assert help_mod.wants_help(["--help"])
    assert help_mod.wants_help(["-h"])
    assert help_mod.wants_help(["foo", "--help"])
    assert not help_mod.wants_help(["foo", "bar"])
    assert not help_mod.wants_help([])


# --------------------------------------------------------------------------- #
# print_overview
# --------------------------------------------------------------------------- #
def test_print_overview_lists_reserved_commands(capsys):
    help_mod.print_overview()
    out = capsys.readouterr().out
    # A few representative reserved commands across groups.
    for name in ("up", "down", "ps", "config", "plugs", "images"):
        assert name in out
    assert "Fin" in out  # banner


# --------------------------------------------------------------------------- #
# print_command_help — reserved
# --------------------------------------------------------------------------- #
def test_command_help_reserved_found(capsys):
    found = help_mod.print_command_help("config")
    assert found is True
    out = capsys.readouterr().out
    assert "fin config" in out
    # Subcommands rendered.
    assert "enable" in out and "disable" in out
    # Examples rendered.
    assert "fin config list" in out


def test_command_help_reserved_renders_bracket_literals(capsys):
    """`[asset|all]` must survive (not be parsed as Rich markup)."""
    help_mod.print_command_help("down")
    out = capsys.readouterr().out
    assert "[asset|all]" in out
    assert "-f" in out  # the force option


def test_command_help_alias_resolves(capsys):
    # `art` is an alias of the laravel plug's artisan command; `status` is a
    # reserved alias of ps.
    assert help_mod.print_command_help("status") is True
    out = capsys.readouterr().out
    assert "fin ps" in out  # canonical command shown


def test_command_help_unknown_returns_false(capsys):
    assert help_mod.print_command_help("definitely-not-a-command") is False


# --------------------------------------------------------------------------- #
# print_command_help — plug command
# --------------------------------------------------------------------------- #
def test_command_help_plug_command(capsys, tmp_path, synthetic_plug):
    # The synthetic laravel plug contributes `artisan`.
    found = help_mod.print_command_help("artisan", env=_empty_env(tmp_path))
    assert found is True
    out = capsys.readouterr().out
    assert "fin artisan" in out
    assert "laravel" in out  # owning plug named
    assert "FIN_SITE" in out  # env spec table rendered


def test_command_help_plug_alias(capsys, tmp_path, synthetic_plug):
    # `art` is an alias of artisan.
    found = help_mod.print_command_help("art", env=_empty_env(tmp_path))
    assert found is True
    out = capsys.readouterr().out
    assert "artisan" in out


# --------------------------------------------------------------------------- #
# dispatch integration
# --------------------------------------------------------------------------- #
def test_dispatch_command_help_flag(monkeypatch, tmp_path):
    # `fin config --help` should NOT run config; it should render help.
    ran = []
    monkeypatch.setattr(main_mod, "resolve",
                        lambda name, args, env: ran.append(name) or None)
    code = main_mod._dispatch(["config", "--help"])
    assert code == EXIT_OK
    assert ran == []  # resolve/run never called


def test_dispatch_help_subcommand(monkeypatch, tmp_path):
    code = main_mod._dispatch(["help", "up"])
    assert code == EXIT_OK


def test_dispatch_help_unknown_command_exits_user():
    code = main_mod._dispatch(["help", "nope-not-real"])
    assert code == EXIT_USER
