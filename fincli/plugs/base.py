"""The ``FinPlug`` base class — the plugin spec interface.

Only classes that subclass :class:`FinPlug` are treated as plugs by the
loader. A plug is *declarative*: it describes containers and commands and
returns information when asked, but it never executes Docker actions itself.
Fin acts on the plug's behalf (see the system commands). This keeps a single,
auditable code path for anything that touches the Docker daemon.

A plug provides:

* identity — :attr:`name`, :attr:`version`, :attr:`plug_type`
* an env contract — :meth:`env_spec`
* container specs — :meth:`primary_spec` (APP) and/or :meth:`asset_specs`
* sub-commands — :meth:`commands` mapping a name to a handler
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from fincli.core.env import EnvSpec, ProjectEnv


class PlugType(str, Enum):
    """The three plug categories."""

    APP = "APP"
    ASSET = "ASSET"
    GLOBAL = "GLOBAL"


@dataclass
class PortMapping:
    """A container port optionally published to a host port.

    ``host=None`` means "let Docker pick" (rendered as ``{container/proto: None}``).
    """

    container: int
    host: int | None = None
    protocol: str = "tcp"

    def as_docker(self) -> tuple[str, Any]:
        key = f"{self.container}/{self.protocol}"
        return key, self.host


@dataclass
class VolumeMount:
    """A host→container bind mount."""

    host: str
    container: str
    mode: str = "rw"


@dataclass
class ContainerSpec:
    """A declarative description of one container Fin should run.

    The plug fills this in; the system ``up`` command turns it into an actual
    container, attaching the standard Fin labels and (for web-exposed services)
    the Traefik routing labels.
    """

    #: Service identity — becomes the ``FIN_SERVICE`` label.
    service: str
    #: Image reference (``repo:tag``).
    image: str
    #: Suffix for the container name (``<project>-<name_suffix>``). For assets
    #: use a fixed shared name via :attr:`container_name` instead.
    name_suffix: str = "web"
    #: Fixed container name (assets use this; primaries derive from project).
    container_name: str | None = None
    #: Environment variables passed into the container.
    environment: dict[str, str] = field(default_factory=dict)
    #: Ports to publish.
    ports: list[PortMapping] = field(default_factory=list)
    #: Bind mounts (the project dir mount is added by `up` for primaries).
    volumes: list[VolumeMount] = field(default_factory=list)
    #: Optional command override.
    command: Any = None
    #: Whether this service is exposed over HTTP and should get Traefik labels.
    web_exposed: bool = False
    #: The container port Traefik load-balances to (required if web_exposed).
    web_port: int | None = None
    #: Path inside the container where the project dir is mounted (primaries).
    workdir_mount: str | None = None
    #: Extra kwargs forwarded to ``containers.run``.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlugCommand:
    """A sub-command contributed by a plug.

    The handler receives the :class:`fincli.plugs.context.PlugContext` and the
    list of remaining CLI arguments, and returns an exit code (0 = success).
    """

    name: str
    handler: Callable[..., int]
    help: str = ""
    aliases: tuple[str, ...] = ()


class FinPlug:
    """Base class all plugs must extend.

    Subclasses set the class attributes :attr:`name`, :attr:`version`, and
    :attr:`plug_type`, and override the methods relevant to their type.
    """

    #: Unique plug name (used for resolution and ``fin plugs`` commands).
    name: str = ""
    #: Plug version string.
    version: str = "0.0.0"
    #: One of :class:`PlugType`.
    plug_type: PlugType = PlugType.GLOBAL
    #: Short human description.
    description: str = ""

    # --- lifecycle ----------------------------------------------------------
    def setup(self) -> None:
        """Optional hook called once after instantiation by the loader.

        Use for cheap initialisation only. Must not touch Docker.
        """

    # --- env contract -------------------------------------------------------
    def env_spec(self) -> EnvSpec:
        """Return the env requirements this plug needs. Override as needed."""
        return EnvSpec()

    # --- container specs ----------------------------------------------------
    def primary_spec(self, env: ProjectEnv) -> ContainerSpec | None:
        """Return the primary container spec for APP plugs (else None)."""
        return None

    def asset_specs(self, env: ProjectEnv) -> list[ContainerSpec]:
        """Return auxiliary container specs (assets). Default: none."""
        return []

    # --- commands -----------------------------------------------------------
    def commands(self) -> Mapping[str, PlugCommand]:
        """Return the sub-commands this plug contributes (name → command)."""
        return {}

    # --- introspection ------------------------------------------------------
    def info(self) -> dict[str, Any]:
        """Return a serialisable summary used by ``fin plugs info``."""
        cmds = list(self.commands().keys())
        return {
            "name": self.name,
            "version": self.version,
            "type": self.plug_type.value,
            "description": self.description,
            "commands": cmds,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<FinPlug {self.name} v{self.version} ({self.plug_type.value})>"
