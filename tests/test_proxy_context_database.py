"""Tests for proxy, plug context, and database helpers."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.core import database as db
from fincli.core import proxy
from fincli.core.env import ProjectEnv
from fincli.plugs.context import PlugContext

from conftest import make_fake_container


def _env(tmp_path, **values):
    return ProjectEnv(cwd=tmp_path, values=dict(values))


# --------------------------------------------------------------------------- #
# proxy
# --------------------------------------------------------------------------- #
def test_is_proxy_running_true(patch_docker):
    c = make_fake_container(name=Config.PROXY_CONTAINER, status="running")
    patch_docker.containers.list.return_value = [c]
    assert proxy.is_proxy_running() is True


def test_is_proxy_running_false_when_absent(patch_docker):
    patch_docker.containers.list.return_value = []
    assert proxy.is_proxy_running() is False


def test_is_proxy_running_false_when_stopped(patch_docker):
    c = make_fake_container(name=Config.PROXY_CONTAINER, status="exited")
    patch_docker.containers.list.return_value = [c]
    assert proxy.is_proxy_running() is False


def test_ensure_proxy_runs_traefik(monkeypatch, patch_docker):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        from fincli.core.containers import RunResult
        return RunResult(container=make_fake_container(), created=True)

    monkeypatch.setattr(proxy, "run_container", fake_run)
    monkeypatch.setattr(proxy, "ensure_network", lambda: None)
    proxy.ensure_proxy()
    assert captured["name"] == Config.PROXY_CONTAINER
    assert captured["image"] == Config.PROXY_IMAGE
    assert captured["labels"]["traefik.enable"] == "true"
    # docker socket mounted read-only
    assert captured["volumes"]["/var/run/docker.sock"]["mode"] == "ro"


# --------------------------------------------------------------------------- #
# PlugContext
# --------------------------------------------------------------------------- #
def test_plug_context_primary_name(tmp_path):
    ctx = PlugContext(env=_env(tmp_path), project="demo")
    assert ctx.primary_name == "demo-web"


def test_plug_context_exec_not_running(monkeypatch, tmp_path):
    import fincli.plugs.context as ctxmod
    c = make_fake_container(name="demo-web", status="exited")
    monkeypatch.setattr(ctxmod, "find_primary", lambda project, service: c)
    ctx = PlugContext(env=_env(tmp_path), project="demo")
    assert ctx.exec(["ls"]) == 1


def test_plug_context_exec_streams(monkeypatch, tmp_path):
    import fincli.plugs.context as ctxmod
    c = make_fake_container(name="demo-web", status="running")
    c.exec_run.return_value = (5, iter([b"out"]))
    monkeypatch.setattr(ctxmod, "find_primary", lambda project, service: c)
    ctx = PlugContext(env=_env(tmp_path), project="demo")
    rc = ctx.exec(["php", "artisan"], workdir="/app")
    assert rc == 5
    _, kwargs = c.exec_run.call_args
    assert kwargs["workdir"] == "/app"


def test_plug_context_exec_none_code(monkeypatch, tmp_path):
    import fincli.plugs.context as ctxmod
    c = make_fake_container(name="demo-web", status="running")
    c.exec_run.return_value = (None, iter([b"out"]))
    monkeypatch.setattr(ctxmod, "find_primary", lambda project, service: c)
    ctx = PlugContext(env=_env(tmp_path), project="demo")
    assert ctx.exec(["x"]) == 0


# --------------------------------------------------------------------------- #
# database
# --------------------------------------------------------------------------- #
def test_ensure_database_no_db_noop(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(db, "_ensure_mysql_database", lambda d: called.append(d))
    db.ensure_project_database(_env(tmp_path))  # no DB_DATABASE
    assert called == []


def test_ensure_database_mysql(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(db, "_ensure_mysql_database", lambda d: called.append(d))
    monkeypatch.setattr(db, "_ensure_postgres_database", lambda d: pytest.fail("wrong engine"))
    db.ensure_project_database(_env(tmp_path, DB_CONNECTION="mysql", DB_DATABASE="mydb"))
    assert called == ["mydb"]


def test_ensure_database_postgres(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(db, "_ensure_postgres_database", lambda d: called.append(d))
    db.ensure_project_database(_env(tmp_path, DB_CONNECTION="pgsql", DB_DATABASE="pgdb"))
    assert called == ["pgdb"]


def test_ensure_database_sqlite_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_ensure_mysql_database", lambda d: pytest.fail("should skip"))
    monkeypatch.setattr(db, "_ensure_postgres_database", lambda d: pytest.fail("should skip"))
    db.ensure_project_database(_env(tmp_path, DB_CONNECTION="sqlite", DB_DATABASE="x"))


def test_ensure_mysql_database_execs(monkeypatch):
    c = make_fake_container(name="fin_mysql", status="running")
    c.exec_run.return_value = type("R", (), {"exit_code": 0, "output": b""})()
    monkeypatch.setattr(db, "find_container", lambda name: c)
    # The readiness wait runs its own exec_run probe first; short-circuit it so
    # this test exercises only the CREATE DATABASE exec contract.
    monkeypatch.setattr(db, "wait_for_ready", lambda container, **kw: True)
    db._ensure_mysql_database("mydb")
    c.exec_run.assert_called_once()
    args, kwargs = c.exec_run.call_args
    argv = args[0]
    # argv must be passed directly (NOT wrapped in `sh -c`), otherwise the
    # backticks around the DB name get interpreted as shell command
    # substitution. Guard against that regression.
    assert argv[0] == "mysql"
    assert argv[:2] != ["sh", "-c"]
    assert any("mydb" in part for part in argv)  # SQL references the DB name
    # Password is supplied via the exec environment, not interpolated.
    assert kwargs.get("environment", {}).get("MYSQL_PWD")


def test_ensure_mysql_database_container_missing(monkeypatch):
    monkeypatch.setattr(db, "find_container", lambda name: (_ for _ in ()).throw(Exception("no container")))
    # Should warn and return without raising.
    db._ensure_mysql_database("mydb")
