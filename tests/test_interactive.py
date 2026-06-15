"""Tests for fincli.core.interactive — interactive vs fallback exec paths."""

from __future__ import annotations

from unittest.mock import MagicMock

import fincli.core.interactive as inter


def _api_with_exec(exit_code=0, output_chunks=(b"hello\n",)):
    """Build a fake low-level docker API client."""
    api = MagicMock()
    api.exec_create.return_value = {"Id": "exec123"}
    api.exec_start.return_value = iter(output_chunks)
    api.exec_inspect.return_value = {"ExitCode": exit_code}
    return api


def test_streamed_fallback_when_no_tty(monkeypatch, capsys):
    """Without a local TTY, interactive_exec falls back to a streamed exec.

    With stdout not a terminal (piped), no pseudo-TTY is allocated so the
    captured output stays clean.
    """
    api = _api_with_exec(exit_code=7, output_chunks=(b"out-A", b"out-B"))
    fake_client = MagicMock()
    fake_client.api = api
    monkeypatch.setattr(inter, "get_docker", lambda: MagicMock(client=fake_client))

    # Force the "no interactive terminal" branch + non-terminal stdout.
    monkeypatch.setattr(inter.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(inter, "stdout_is_tty", lambda: False)

    container = MagicMock()
    container.id = "cid"
    code = inter.interactive_exec(container, ["echo", "hi"], workdir="/app")

    assert code == 7
    # Non-interactive create: tty False (clean output), workdir forwarded.
    _, kwargs = api.exec_create.call_args
    assert kwargs["tty"] is False
    assert kwargs["workdir"] == "/app"
    # Output streamed to the console.
    out = capsys.readouterr().out
    assert "out-A" in out and "out-B" in out


def test_streamed_allocates_tty_for_colour_when_stdout_is_terminal(monkeypatch, capsys):
    """When stdout IS a terminal, a pseudo-TTY is allocated so the in-container
    program keeps its ANSI colours (the colour-passthrough fix)."""
    api = _api_with_exec(exit_code=0, output_chunks=(b"\x1b[32mok\x1b[0m",))
    fake_client = MagicMock()
    fake_client.api = api
    monkeypatch.setattr(inter, "get_docker", lambda: MagicMock(client=fake_client))
    monkeypatch.setattr(inter, "stdout_is_tty", lambda: True)

    container = MagicMock()
    container.id = "cid"
    code = inter.streamed_exec(container, ["ls", "--color"], workdir="/app")

    assert code == 0
    create_kwargs = api.exec_create.call_args.kwargs
    assert create_kwargs["tty"] is True  # <-- the colour fix
    assert create_kwargs["workdir"] == "/app"
    start_kwargs = api.exec_start.call_args.kwargs
    assert start_kwargs["tty"] is True
    # ANSI escape codes pass straight through to the terminal.
    assert "\x1b[32m" in capsys.readouterr().out


def test_streamed_fallback_exit_code_default(monkeypatch, capsys):
    """A missing ExitCode resolves to 0, not a crash."""
    api = _api_with_exec(output_chunks=())
    api.exec_inspect.return_value = {}
    fake_client = MagicMock()
    fake_client.api = api
    monkeypatch.setattr(inter, "get_docker", lambda: MagicMock(client=fake_client))
    monkeypatch.setattr(inter.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(inter, "stdout_is_tty", lambda: False)

    container = MagicMock()
    container.id = "cid"
    assert inter.interactive_exec(container, ["true"]) == 0


def test_isatty_error_falls_back(monkeypatch):
    """If stdin.isatty()/fileno() raise, we still degrade to streaming."""
    api = _api_with_exec(exit_code=0)
    fake_client = MagicMock()
    fake_client.api = api
    monkeypatch.setattr(inter, "get_docker", lambda: MagicMock(client=fake_client))
    monkeypatch.setattr(inter, "stdout_is_tty", lambda: False)

    def boom():
        raise OSError("no stdin")

    monkeypatch.setattr(inter.sys.stdin, "isatty", boom)

    container = MagicMock()
    container.id = "cid"
    # Should not raise; returns the streamed exec's code.
    assert inter.interactive_exec(container, ["ls"]) == 0
