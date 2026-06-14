"""Tests for fincli.commands.containers — ps / exec / inspect / logs."""

from __future__ import annotations

import pytest

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import containers as cc
from fincli.core.env import ProjectEnv

from conftest import make_fake_container


def _env(cwd, **values):
    return ProjectEnv(cwd=cwd, values=dict(values))


# --------------------------------------------------------------------------- #
# ps
# --------------------------------------------------------------------------- #
def test_ps_empty(monkeypatch):
    monkeypatch.setattr(cc, "list_containers", lambda **kw: [])
    assert cc.ps([]) == EXIT_OK


def test_ps_lists(monkeypatch):
    c = make_fake_container(name="demo-web", status="running")
    monkeypatch.setattr(cc, "list_containers", lambda **kw: [c])
    # avoid stats network calls; stub the grouped renderer to a sentinel
    monkeypatch.setattr(cc, "render_grouped_containers", lambda *a, **k: "GROUP")
    assert cc.ps([]) == EXIT_OK


def test_ps_renders_grouped(monkeypatch):
    """ps drives the grouped renderer over the listed containers."""
    app = make_fake_container(
        name="myapp-web", status="running",
        labels={"FIN_TYPE": "app", "FIN_SERVICE": "web"},
    )
    asset = make_fake_container(
        name="fin_redis", status="running", id="redis00000001",
        labels={"FIN_TYPE": "asset", "FIN_SERVICE": "redis"},
    )
    captured = {}
    monkeypatch.setattr(cc, "list_containers", lambda **kw: [app, asset])
    monkeypatch.setattr(cc, "_read_stats", lambda containers: {})

    def fake_render(containers, **kwargs):
        captured["containers"] = list(containers)
        return "GROUP"

    monkeypatch.setattr(cc, "render_grouped_containers", fake_render)
    assert cc.ps([]) == EXIT_OK
    assert captured["containers"] == [app, asset]


def test_ps_all_flag(monkeypatch):
    captured = {}
    monkeypatch.setattr(cc, "list_containers", lambda **kw: captured.update(kw) or [])
    cc.ps(["-a"])
    assert captured["all_"] is True


def test_read_stats_skips_non_running(monkeypatch):
    running = make_fake_container(name="r", status="running", id="run111111111")
    running.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200, "percpu_usage": [1, 1]},
            "system_cpu_usage": 2000,
            "online_cpus": 2,
        },
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        "memory_stats": {"usage": 1048576},
    }
    stopped = make_fake_container(name="s", status="exited", id="stop222222222")
    stats = cc._read_stats([running, stopped])
    assert running.id in stats
    assert stopped.id not in stats
    assert stats[running.id]["mem"] == "1MB"


def test_cpu_percent_handles_missing_keys():
    assert cc._cpu_percent({}) == "-"


def test_mem_usage_units():
    assert cc._mem_usage({"memory_stats": {"usage": 512}}) == "512B"
    assert cc._mem_usage({"memory_stats": {"usage": 2048}}) == "2KB"
    assert cc._mem_usage({}) == "-"


# --------------------------------------------------------------------------- #
# exec
# --------------------------------------------------------------------------- #
def test_exec_no_args(monkeypatch):
    assert cc.exec_cmd([]) == EXIT_USER


def test_exec_not_running(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web", status="exited")
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)
    assert cc.exec_cmd(["ls"]) == EXIT_USER


def test_exec_runs_and_returns_code(monkeypatch, tmp_path):
    # `fin exec` delegates to interactive_exec (which proxies stdin for shells
    # and streams otherwise) and returns its exit code.
    c = make_fake_container(name="demo-web", status="running")
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)

    captured = {}
    import fincli.core.interactive as inter

    def fake_interactive(container, cmd, **kwargs):
        captured["cmd"] = cmd
        return 3

    monkeypatch.setattr(inter, "interactive_exec", fake_interactive)
    rc = cc.exec_cmd(["ls", "-la"])
    assert rc == 3
    assert captured["cmd"] == ["ls", "-la"]


def test_exec_handles_zero_code(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web", status="running")
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)

    import fincli.core.interactive as inter

    monkeypatch.setattr(inter, "interactive_exec", lambda container, cmd, **kw: 0)
    assert cc.exec_cmd(["true"]) == 0


# --------------------------------------------------------------------------- #
# inspect
# --------------------------------------------------------------------------- #
def test_inspect_primary(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web")
    c.attrs = {"Id": "abc", "State": {"Status": "running"}}
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)
    assert cc.inspect([]) == EXIT_OK


def test_inspect_named_container(monkeypatch, tmp_path):
    c = make_fake_container(name="other")
    c.attrs = {"Id": "xyz"}
    captured = {}

    def fake_find(name):
        captured["name"] = name
        return c

    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_container", fake_find)
    assert cc.inspect(["other"]) == EXIT_OK
    assert captured["name"] == "other"


# --------------------------------------------------------------------------- #
# logs
# --------------------------------------------------------------------------- #
def test_logs_primary_no_follow(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web")
    c.logs.return_value = b"hello logs\n"
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)
    assert cc.logs([]) == EXIT_OK
    c.logs.assert_called_once()
    _, kwargs = c.logs.call_args
    assert "stream" not in kwargs


def test_logs_named_with_tail(monkeypatch, tmp_path):
    c = make_fake_container(name="svc")
    c.logs.return_value = b"x\n"
    captured = {}

    def fake_find(name):
        captured["name"] = name
        return c

    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_container", fake_find)
    assert cc.logs(["svc", "--tail", "50"]) == EXIT_OK
    assert captured["name"] == "svc"
    _, kwargs = c.logs.call_args
    assert kwargs["tail"] == 50


def test_logs_follow(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web")
    c.logs.return_value = iter([b"line1\n", b"line2\n"])
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)
    assert cc.logs(["-f"]) == EXIT_OK
    _, kwargs = c.logs.call_args
    assert kwargs["follow"] is True
