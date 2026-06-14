"""Tests for fincli.core.errors — FinError hierarchy and handle_errors decorator."""

from __future__ import annotations

import pytest

import docker.errors as derr

from fincli.app import EXIT_SYSTEM, EXIT_USER
from fincli.core.errors import (
    DockerUnavailable,
    FinError,
    NotFound,
    _clean_docker_message,
    handle_errors,
)


# --------------------------------------------------------------------------- #
# exception classes
# --------------------------------------------------------------------------- #
def test_finerror_defaults():
    e = FinError("boom")
    assert e.message == "boom"
    assert e.exit_code == EXIT_USER
    assert e.title == "Error"


def test_finerror_custom():
    e = FinError("boom", exit_code=7, title="Custom")
    assert e.exit_code == 7
    assert e.title == "Custom"


def test_docker_unavailable_is_system():
    e = DockerUnavailable()
    assert isinstance(e, FinError)
    assert e.exit_code == EXIT_SYSTEM
    assert e.title == "Docker Unavailable"


def test_not_found_is_user():
    e = NotFound("missing")
    assert isinstance(e, FinError)
    assert e.exit_code == EXIT_USER
    assert e.title == "Not Found"


# --------------------------------------------------------------------------- #
# handle_errors decorator
# --------------------------------------------------------------------------- #
def test_handle_errors_passthrough_return():
    @handle_errors
    def ok(x):
        return x * 2

    assert ok(3) == 6


def test_handle_errors_finerror_exit_code(capsys):
    @handle_errors
    def boom():
        raise FinError("user mistake", exit_code=EXIT_USER)

    with pytest.raises(SystemExit) as exc:
        boom()
    assert exc.value.code == EXIT_USER


def test_handle_errors_docker_unavailable_exit_code():
    @handle_errors
    def boom():
        raise DockerUnavailable()

    with pytest.raises(SystemExit) as exc:
        boom()
    assert exc.value.code == EXIT_SYSTEM


def test_handle_errors_docker_notfound():
    @handle_errors
    def boom():
        raise derr.NotFound("no such container")

    with pytest.raises(SystemExit) as exc:
        boom()
    assert exc.value.code == EXIT_USER


def test_handle_errors_docker_apierror():
    @handle_errors
    def boom():
        raise derr.APIError("api failed")

    with pytest.raises(SystemExit) as exc:
        boom()
    assert exc.value.code == EXIT_SYSTEM


def test_handle_errors_docker_exception():
    @handle_errors
    def boom():
        raise derr.DockerException("daemon down")

    with pytest.raises(SystemExit) as exc:
        boom()
    assert exc.value.code == EXIT_SYSTEM


def test_handle_errors_keyboard_interrupt():
    @handle_errors
    def boom():
        raise KeyboardInterrupt()

    with pytest.raises(SystemExit) as exc:
        boom()
    assert exc.value.code == EXIT_USER


def test_handle_errors_preserves_metadata():
    @handle_errors
    def documented():
        """My docstring."""
        return 1

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "My docstring."


# --------------------------------------------------------------------------- #
# _clean_docker_message
# --------------------------------------------------------------------------- #
def test_clean_docker_message_uses_explanation():
    exc = derr.APIError("raw", explanation="friendly explanation")
    assert _clean_docker_message(exc) == "friendly explanation"


def test_clean_docker_message_fallback_to_str():
    exc = Exception("plain message")
    assert _clean_docker_message(exc) == "plain message"
