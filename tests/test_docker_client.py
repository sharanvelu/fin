"""Tests for fincli.core.docker_client — singleton behaviour and socket detection."""

from __future__ import annotations

from unittest.mock import MagicMock


from fincli.core import docker_client as dc
from fincli.core.docker_client import DockerService, get_docker


def test_singleton_identity():
    a = DockerService()
    b = DockerService()
    assert a is b
    assert get_docker() is a


def test_client_lazily_created_and_cached(monkeypatch):
    mock_client = MagicMock(name="client")
    creator = MagicMock(return_value=mock_client)
    monkeypatch.setattr(DockerService, "_create_client", lambda self: creator())
    DockerService._instance = None

    svc = get_docker()
    assert svc.client is mock_client
    # second access returns the cached client without re-creating
    assert svc.client is mock_client
    creator.assert_called_once()


def test_ping_delegates_to_client(monkeypatch):
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    monkeypatch.setattr(DockerService, "_create_client", lambda self: mock_client)
    DockerService._instance = None
    assert get_docker().ping() is True


def test_close_resets_client(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(DockerService, "_create_client", lambda self: mock_client)
    DockerService._instance = None
    svc = get_docker()
    _ = svc.client
    svc.close()
    mock_client.close.assert_called_once()
    assert svc._client is None


def test_context_manager(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(DockerService, "_create_client", lambda self: mock_client)
    DockerService._instance = None
    with get_docker() as svc:
        assert svc.client is mock_client
    # exit calls close
    mock_client.close.assert_called_once()


# --------------------------------------------------------------------------- #
# _detect_socket
# --------------------------------------------------------------------------- #
def test_detect_socket_defers_to_docker_host(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://1.2.3.4:2375")
    assert DockerService._detect_socket() is None


def test_detect_socket_finds_existing(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    # Force exactly one candidate to "exist".
    def fake_exists(self):
        return str(self) == "/var/run/docker.sock"

    monkeypatch.setattr(dc.Path, "exists", fake_exists)
    result = DockerService._detect_socket()
    assert result == "unix:///var/run/docker.sock"


def test_detect_socket_none_when_no_candidates(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(dc.Path, "exists", lambda self: False)
    assert DockerService._detect_socket() is None
