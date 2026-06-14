"""Tests for fincli.app.App and the __main__ dispatch entrypoint."""

from __future__ import annotations

import pytest

from fincli.app import EXIT_OK, EXIT_USER, App
from fincli import __main__ as main_mod


def test_app_singleton():
    assert App() is App()


def test_app_banner():
    assert App().banner() == f"Fin v{App().version}"


def test_app_terminate_raises_systemexit():
    with pytest.raises(SystemExit) as exc:
        App().terminate(code=EXIT_USER)
    assert exc.value.code == EXIT_USER


def test_app_terminate_with_message():
    with pytest.raises(SystemExit):
        App().terminate("something failed", code=5)


def test_dispatch_help():
    assert main_mod._dispatch([]) == EXIT_OK
    assert main_mod._dispatch(["--help"]) == EXIT_OK
    assert main_mod._dispatch(["help"]) == EXIT_OK


def test_dispatch_version():
    assert main_mod._dispatch(["--version"]) == EXIT_OK
    assert main_mod._dispatch(["version"]) == EXIT_OK


def test_dispatch_unknown_command(monkeypatch, tmp_path):
    monkeypatch.setattr(main_mod.ProjectEnv, "load",
                        classmethod(lambda cls: main_mod.ProjectEnv(cwd=tmp_path, values={})))
    monkeypatch.setattr(main_mod, "resolve", lambda name, args, env: None)
    assert main_mod._dispatch(["bogus"]) == EXIT_USER


def test_dispatch_runs_resolution(monkeypatch, tmp_path):
    from fincli.resolver import Resolution

    monkeypatch.setattr(main_mod.ProjectEnv, "load",
                        classmethod(lambda cls: main_mod.ProjectEnv(cwd=tmp_path, values={})))
    res = Resolution(kind="reserved", run=lambda: 0, source="system")
    monkeypatch.setattr(main_mod, "resolve", lambda name, args, env: res)
    assert main_mod._dispatch(["up"]) == EXIT_OK
