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
    # avoid stats network calls; stub make_container_table to a sentinel
    monkeypatch.setattr(cc, "make_container_table", lambda *a, **k: "TABLE")
    assert cc.ps([]) == EXIT_OK


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
    c = make_fake_container(name="demo-web", status="running")
    c.exec_run.return_value = (3, iter([b"output"]))
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)
    rc = cc.exec_cmd(["ls", "-la"])
    assert rc == 3
    c.exec_run.assert_called_once()
    args, kwargs = c.exec_run.call_args
    assert args[0] == ["ls", "-la"]


def test_exec_handles_none_output(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web", status="running")
    c.exec_run.return_value = (0, None)
    monkeypatch.setattr(cc.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path)))
    monkeypatch.setattr(cc, "find_primary", lambda project: c)
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
