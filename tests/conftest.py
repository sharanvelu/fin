"""Shared pytest fixtures for the Fin test suite.

The whole suite is hermetic: it must NEVER touch a real Docker daemon, the
real ``~/.fin`` data dir, or the bundled ``plugs/`` directory unless a test
explicitly opts in. Two mechanisms enforce that:

* ``reset_docker_singleton`` (autouse) clears ``DockerService._instance`` and
  ``_client`` before *and* after every test, so a mocked client from one test
  never leaks into the next.
* ``isolate_config`` (autouse) re-points ``Config.DATA_DIR`` / ``CONFIG_FILE`` /
  ``REGISTRY_DB`` at a per-test tmp dir, so the store / registry tests can never
  clobber a developer's real ``~/.fin``.

``mock_docker_client`` builds a ``MagicMock`` shaped like the docker SDK client;
``patch_docker`` wires it into ``DockerService`` so ``get_docker().client``
returns it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fincli.config import Config
from fincli.core import docker_client as docker_client_mod


# --------------------------------------------------------------------------- #
# Fake docker SDK objects
# --------------------------------------------------------------------------- #
def make_fake_container(
    *,
    name: str = "demo-web",
    status: str = "running",
    id: str = "abc123def456",
    short_id: str | None = None,
    image_tags: list[str] | None = None,
    labels: dict[str, str] | None = None,
    attrs: dict | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like a docker-py Container.

    Exposes the attributes Fin reads: ``.name``, ``.status``, ``.id``,
    ``.short_id``, ``.image.tags``, ``.attrs`` (with Config/Labels and
    NetworkSettings/Ports), and stubbed action methods (start/stop/remove/
    exec_run/logs/stats).
    """
    c = MagicMock(name=f"container::{name}")
    c.name = name
    c.status = status
    c.id = id
    c.short_id = short_id if short_id is not None else id[:12]

    image = MagicMock()
    image.tags = image_tags if image_tags is not None else ["demo:latest"]
    c.image = image

    base_attrs = {
        "Config": {"Labels": labels or {"FIN_MANAGED": "true", "FIN_SERVICE": "web"}},
        "NetworkSettings": {"Ports": {}},
        "Created": "2026-06-14T10:00:00Z",
    }
    if attrs:
        base_attrs.update(attrs)
    c.attrs = base_attrs

    # exec_run: when stream=True docker-py returns (exit_code, output_gen).
    c.exec_run.return_value = (0, iter([b"ok\n"]))
    c.logs.return_value = b"log line\n"
    c.stats.return_value = {}
    return c


def make_fake_image(
    *,
    short_id: str = "img0001",
    tags: list[str] | None = None,
    size: int = 100 * 1024 * 1024,
    created: str = "2026-06-14T10:00:00Z",
) -> MagicMock:
    """Build a MagicMock that quacks like a docker-py Image."""
    img = MagicMock(name="image")
    img.short_id = short_id
    img.tags = tags if tags is not None else ["demo:latest"]
    img.attrs = {"Size": size, "Created": created}
    img.id = f"sha256:{short_id}"
    return img


# Expose factories on the module so tests can ``import conftest`` style is not
# needed — they're injected as fixtures below too.
@pytest.fixture
def fake_container():
    return make_fake_container


@pytest.fixture
def fake_image():
    return make_fake_image


# --------------------------------------------------------------------------- #
# Docker client mock
# --------------------------------------------------------------------------- #
@pytest.fixture
def mock_docker_client() -> MagicMock:
    """A MagicMock simulating ``docker.DockerClient``.

    Sensible defaults: empty lists for containers/images/networks, a truthy
    ``ping``, and ``containers.run`` returning a fresh fake container.
    """
    client = MagicMock(name="docker_client")

    client.ping.return_value = True

    client.containers.list.return_value = []
    client.containers.run.return_value = make_fake_container(name="created-web")
    client.containers.get.side_effect = lambda n: make_fake_container(name=n)

    client.images.list.return_value = []
    client.images.remove.return_value = None
    client.images.prune.return_value = {"SpaceReclaimed": 0}

    client.networks.list.return_value = []
    client.networks.create.return_value = MagicMock(name="network")

    return client


@pytest.fixture
def patch_docker(monkeypatch, mock_docker_client) -> MagicMock:
    """Make ``get_docker().client`` return ``mock_docker_client``.

    Patches ``DockerService._create_client`` so no real daemon is contacted,
    and primes the singleton's cached client. Returns the mock for assertions.
    """
    monkeypatch.setattr(
        docker_client_mod.DockerService,
        "_create_client",
        lambda self: mock_docker_client,
    )
    # Reset so the next .client access goes through the patched creator.
    docker_client_mod.DockerService._instance = None
    return mock_docker_client


# --------------------------------------------------------------------------- #
# Autouse isolation
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def reset_docker_singleton():
    """Clear the DockerService singleton before and after every test."""
    docker_client_mod.DockerService._instance = None
    yield
    svc = docker_client_mod.DockerService._instance
    if svc is not None and getattr(svc, "_client", None) is not None:
        # Don't call a possibly-mock close in a way that errors.
        svc._client = None
    docker_client_mod.DockerService._instance = None


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Point all Config paths at a per-test tmp dir.

    Guards against tests writing to the developer's real ~/.fin. Individual
    tests override PLUGS_DIR / CONFIG_FILE / REGISTRY_DB as needed.
    """
    data_dir = tmp_path / "fin-data"
    monkeypatch.setattr(Config, "DATA_DIR", data_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", data_dir / "config.json")
    monkeypatch.setattr(Config, "REGISTRY_DB", data_dir / "registry.db")
    # Default PLUGS_DIR -> empty tmp tree; plug-loading tests override it.
    plugs_dir = tmp_path / "plugs-empty"
    plugs_dir.mkdir()
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs_dir)
    yield


# --------------------------------------------------------------------------- #
# Plug-tree helpers
# --------------------------------------------------------------------------- #
def write_plug(
    plugs_dir: Path,
    *,
    name: str,
    class_name: str,
    plug_type: str,
    version: str = "1.0.0",
    description: str = "",
    body_extra: str = "",
) -> Path:
    """Write a minimal flat FinPlug file ``plugs_dir/<name>.py``.

    Returns the file path.
    """
    source = plug_source(
        name=name,
        class_name=class_name,
        plug_type=plug_type,
        version=version,
        description=description,
        body_extra=body_extra,
    )
    plugs_dir.mkdir(parents=True, exist_ok=True)
    flat = plugs_dir / f"{name}.py"
    flat.write_text(source, encoding="utf-8")
    return flat


def plug_source(
    *,
    name: str,
    class_name: str,
    plug_type: str,
    version: str = "1.0.0",
    description: str = "",
    body_extra: str = "",
) -> str:
    """Return the source text of a minimal FinPlug subclass."""
    return f'''
from fincli.plugs.base import FinPlug, PlugType, PlugCommand


class {class_name}(FinPlug):
    name = "{name}"
    version = "{version}"
    plug_type = PlugType.{plug_type}
    description = "{description}"
{body_extra}
'''


@pytest.fixture
def plug_factory():
    """Return the ``write_plug`` helper for building temp plugs."""
    return write_plug
