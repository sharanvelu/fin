"""Singleton wrapper around the Docker SDK client.

Responsibilities:
    * Auto-detect the Docker socket across Linux / macOS / Windows-WSL, plus
      common alternatives (Docker Desktop, Colima, Rancher, Podman).
    * Provide a single, lazily-created ``DockerClient`` via the ``.client``
      property.
    * Fail gracefully (raising :class:`DockerUnavailable`) instead of leaking
      a raw traceback when the daemon is unreachable.
    * Support use as a context manager.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fincli.core.errors import DockerUnavailable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from docker import DockerClient


# Candidate unix sockets, in priority order. The first that exists wins unless
# DOCKER_HOST is explicitly set in the environment.
_SOCKET_CANDIDATES = (
    "{home}/.docker/run/docker.sock",  # Docker Desktop (macOS)
    "{home}/.colima/default/docker.sock",  # Colima default
    "{home}/.colima/docker.sock",  # Colima (older)
    "{home}/.rd/docker.sock",  # Rancher Desktop
    "/var/run/docker.sock",  # Linux / WSL standard
    "{home}/.local/share/containers/podman/machine/podman.sock",  # Podman
)


class DockerService:
    """Lazily-initialised singleton wrapping ``docker.from_env``."""

    _instance: "DockerService | None" = None
    _client: "DockerClient | None"

    def __new__(cls) -> "DockerService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
        return cls._instance

    # --- socket detection ---------------------------------------------------
    @staticmethod
    def _detect_socket() -> Optional[str]:
        """Return a ``unix://`` URL for the first socket that exists, or None.

        If ``DOCKER_HOST`` is set we defer to the SDK's own env handling and
        return None here.
        """
        if os.environ.get("DOCKER_HOST"):
            return None
        home = str(Path.home())
        for template in _SOCKET_CANDIDATES:
            path = template.format(home=home)
            if Path(path).exists():
                return f"unix://{path}"
        return None

    # --- client -------------------------------------------------------------
    @property
    def client(self) -> "DockerClient":
        """Return the shared ``DockerClient``, creating it on first access."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> "DockerClient":
        try:
            import docker  # local import keeps module import cheap for tests
            from docker.errors import DockerException
        except ImportError as exc:  # pragma: no cover - install-time only
            raise DockerUnavailable(
                "The 'docker' Python SDK is not installed. Run: pip install docker"
            ) from exc

        socket_url = self._detect_socket()
        try:
            if socket_url:
                client = docker.DockerClient(base_url=socket_url)
            else:
                client = docker.from_env()
            # Force an actual connection so we fail fast and predictably.
            client.ping()
            return client
        except DockerException as exc:
            raise DockerUnavailable() from exc

    def ping(self) -> bool:
        """Return True if the daemon is reachable; raise otherwise."""
        return bool(self.client.ping())

    def close(self) -> None:
        """Close the underlying client if it was created."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # --- context manager ----------------------------------------------------
    def __enter__(self) -> "DockerService":
        # Touch the client so connection errors surface inside the with-block.
        _ = self.client
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def get_docker() -> DockerService:
    """Convenience accessor for the Docker singleton."""
    return DockerService()
