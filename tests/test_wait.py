"""Tests for asset readiness waiting (``fincli.core.wait``).

These tests must never sleep for real: a no-op ``sleep`` is always injected,
and the poll loop is driven deterministically by call-counting checks. Timeout
behaviour is exercised by monkeypatching ``time.monotonic`` to a controllable
clock so no wall-clock time passes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fincli.config import Config
from fincli.core import wait
from fincli.core.wait import mysql_ready, postgres_ready, wait_for_ready


def _no_sleep(_seconds: float) -> None:
    """A sleep that never sleeps."""
    return None


# --------------------------------------------------------------------------- #
# wait_for_ready
# --------------------------------------------------------------------------- #
def test_ready_immediately():
    sleeps: list[float] = []
    ok = wait_for_ready(
        object(),
        check=lambda _c: True,
        sleep=lambda s: sleeps.append(s),
        description="MySQL",
    )
    assert ok is True
    assert sleeps == []  # passed on the first poll, never slept


def test_ready_after_n_polls():
    # Check flips to True on the 3rd call.
    calls = {"n": 0}

    def check(_c) -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    sleeps: list[float] = []
    ok = wait_for_ready(
        object(),
        check=check,
        interval=0.5,
        sleep=lambda s: sleeps.append(s),
        description="Postgres",
    )
    assert ok is True
    assert calls["n"] == 3
    # Slept between the first two failed polls only.
    assert sleeps == [0.5, 0.5]


def test_timeout_returns_false_without_real_sleep(monkeypatch):
    # Drive a fake monotonic clock: each read advances by the interval so the
    # loop hits the timeout deterministically and never touches the real clock.
    ticks = iter([0.0, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])

    def fake_monotonic() -> float:
        try:
            return next(ticks)
        except StopIteration:
            return 999.0

    monkeypatch.setattr(wait.time, "monotonic", fake_monotonic)

    slept_real = {"v": False}

    def sleep(_s):
        slept_real["v"] = True  # only the injected no-op; never time.sleep

    ok = wait_for_ready(
        object(),
        check=lambda _c: False,  # never ready
        timeout=1.0,
        interval=0.5,
        sleep=sleep,
        description="MySQL",
    )
    assert ok is False


def test_check_exception_is_treated_as_not_ready():
    # A probe that raises early then succeeds should not crash the wait.
    calls = {"n": 0}

    def check(_c) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection refused")
        return True

    ok = wait_for_ready(
        object(),
        check=check,
        sleep=_no_sleep,
        description="MySQL",
    )
    assert ok is True
    assert calls["n"] == 2


# --------------------------------------------------------------------------- #
# mysql_ready
# --------------------------------------------------------------------------- #
def _container_returning(result):
    c = MagicMock(name="container")
    c.exec_run.return_value = result
    return c


def test_mysql_ready_true_on_alive():
    c = _container_returning(
        type("R", (), {"exit_code": 0, "output": b"mysqld is alive\n"})()
    )
    assert mysql_ready(c) is True
    args, kwargs = c.exec_run.call_args
    assert args[0][0] == "mysqladmin"
    # Password supplied via the exec environment, not interpolated into argv.
    assert kwargs["environment"]["MYSQL_PWD"] == Config.ASSET_PASSWORD


def test_mysql_ready_false_on_nonzero_exit():
    c = _container_returning(
        type("R", (), {"exit_code": 1, "output": b"can't connect\n"})()
    )
    assert mysql_ready(c) is False


def test_mysql_ready_false_when_not_alive():
    c = _container_returning(type("R", (), {"exit_code": 0, "output": b""})())
    assert mysql_ready(c) is False


def test_mysql_ready_handles_tuple_result():
    # docker-py can return a plain (exit_code, output) tuple.
    c = _container_returning((0, b"mysqld is alive"))
    assert mysql_ready(c) is True


# --------------------------------------------------------------------------- #
# postgres_ready
# --------------------------------------------------------------------------- #
def test_postgres_ready_true_on_zero_exit():
    c = _container_returning(
        type("R", (), {"exit_code": 0, "output": b"accepting connections\n"})()
    )
    assert postgres_ready(c) is True
    args, _ = c.exec_run.call_args
    assert args[0][0] == "pg_isready"
    assert Config.ASSET_USERNAME in args[0]


def test_postgres_ready_false_on_nonzero_exit():
    c = _container_returning(
        type("R", (), {"exit_code": 2, "output": b"no response\n"})()
    )
    assert postgres_ready(c) is False
