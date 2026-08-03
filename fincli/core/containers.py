"""Container, label, and network helpers built on the Docker singleton.

This is the single source of truth for:

* The default labels every Fin container carries (so listing/teardown can
  filter precisely on ``FIN_MANAGED=true``).
* The Traefik routing labels for web-exposed services (host from ``FIN_SITE``,
  port from the plug spec).
* Network creation, container lookup by project/type/service, and a small
  ``run`` helper that always applies the standard labels and network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from fincli.config import Config
from fincli.core.docker_client import get_docker
from fincli.core.errors import FinError, NotFound


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #
def base_labels(
    *,
    fin_type: str,
    service: str,
    site: str = "-",
    project: str = "-",
) -> dict[str, str]:
    """Build the standard label set applied to every Fin container.

    Args:
        fin_type: One of ``app`` / ``asset`` / ``global`` / ``proxy``.
        service: Service name (``web`` for primaries; ``mysql``/``redis``/… ).
        site: Routed URL or ``FIN_SITE`` value; ``-`` when not web-exposed.
        project: Project name (cwd basename) or ``-`` for shared containers.
    """
    return {
        Config.LABEL_MANAGED: "true",
        Config.LABEL_TYPE: fin_type,
        Config.LABEL_SERVICE: service,
        Config.LABEL_SITE: site,
        Config.LABEL_PROJECT: project,
    }


def traefik_host_key(site: str) -> str:
    """Derive a Traefik router key from a site host.

    Strips a ``*.`` wildcard prefix and a trailing ``.localhost``, then
    replaces ``.`` and ``-`` with ``_`` so the key is label-safe.
    Example: ``my-app.localhost`` → ``my_app``.
    """
    host = site.strip()
    if host.startswith("*."):
        host = host[2:]
    if host.endswith(".localhost"):
        host = host[: -len(".localhost")]
    return re.sub(r"[.\-]", "_", host) or "app"


def traefik_rule(site: str) -> str:
    """Build the Traefik router rule for a site.

    Wildcards (``*.example.localhost``) become a ``HostRegexp`` rule; plain
    hosts use ``Host(`…`)``.
    """
    host = site.strip()
    if host.startswith("*."):
        # Escape dots, turn the wildcard into a regex segment.
        suffix = re.escape(host[2:])
        return f"HostRegexp(`^.+\\.{suffix}$`)"
    return f"Host(`{host}`)"


def traefik_labels(
    site: str, port: int, additional_hosts: Sequence[str] = ()
) -> dict[str, str]:
    """Build the full Traefik routing label set for a web-exposed service.

    Args:
        site: The host (from ``FIN_SITE`` for primaries, or plug spec).
        port: The container port Traefik load-balances to (from plug spec).
        additional_hosts: Extra hosts (from ``FIN_ADDITIONAL_HOSTS``) routed to
            the same service — each gets its own router so wildcards keep
            working per-host.
    """
    key = traefik_host_key(site)
    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{key}.rule": traefik_rule(site),
        f"traefik.http.routers.{key}.entrypoints": Config.PROXY_ENTRYPOINTS,
        f"traefik.http.routers.{key}.service": f"{key}_service",
        f"traefik.http.services.{key}_service.loadbalancer.server.port": str(port),
    }
    used_keys = {key}
    for host in additional_hosts:
        host = host.strip()
        if not host:
            continue
        extra_key = candidate = traefik_host_key(host)
        # Router keys must be unique per proxy; suffix on collision (e.g. a
        # site and an additional domain that strip to the same key).
        n = 2
        while candidate in used_keys:
            candidate = f"{extra_key}_{n}"
            n += 1
        used_keys.add(candidate)
        labels[f"traefik.http.routers.{candidate}.rule"] = traefik_rule(host)
        labels[f"traefik.http.routers.{candidate}.entrypoints"] = (
            Config.PROXY_ENTRYPOINTS
        )
        labels[f"traefik.http.routers.{candidate}.service"] = f"{key}_service"
    return labels


def managed_filter(**extra: str) -> dict[str, Any]:
    """Build a Docker ``filters`` dict scoped to Fin-managed containers."""
    labels = [f"{Config.LABEL_MANAGED}=true"]
    for key, value in extra.items():
        labels.append(f"{key}={value}")
    return {"label": labels}


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #
def ensure_network() -> None:
    """Create the Fin Docker network if it does not already exist."""
    client = get_docker().client
    existing = client.networks.list(names=[Config.NETWORK])
    if not existing:
        client.networks.create(Config.NETWORK, driver="bridge")


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #
def list_containers(*, all_: bool = False, **label_filters: str) -> list[Any]:
    """List Fin-managed containers, optionally filtered by labels."""
    client = get_docker().client
    return client.containers.list(all=all_, filters=managed_filter(**label_filters))


def find_container(name: str) -> Any:
    """Return a container by exact name, raising :class:`NotFound` if absent."""
    client = get_docker().client
    matches = client.containers.list(all=True, filters={"name": f"^{name}$"})
    if not matches:
        # Fall back to a direct get for id/name flexibility.
        try:
            return client.containers.get(name)
        except Exception as exc:  # noqa: BLE001 - normalised below
            raise NotFound(f"Container '{name}' not found.") from exc
    return matches[0]


def primary_container_name(project: str, service: str = "web") -> str:
    """Standard name for a project's primary container: ``<project>-<service>``."""
    return f"{project}-{service}"


def find_primary(project: str, service: str = "web") -> Any:
    """Find the running primary container for the current project."""
    name = primary_container_name(project, service)
    return find_container(name)


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
@dataclass
class RunResult:
    """Outcome of a container start request."""

    container: Any
    created: bool


def run_container(
    *,
    image: str,
    name: str,
    labels: dict[str, str],
    environment: dict[str, str] | None = None,
    ports: dict[str, Any] | None = None,
    volumes: dict[str, dict[str, str]] | None = None,
    command: Any = None,
    detach: bool = True,
    extra: dict[str, Any] | None = None,
) -> RunResult:
    """Start a container on the Fin network with the given config.

    If a container with *name* already exists it is returned as-is (idempotent
    ``up``). The Fin network is ensured before creation.
    """
    client = get_docker().client

    existing = client.containers.list(all=True, filters={"name": f"^{name}$"})
    if existing:
        container = existing[0]
        if container.status != "running":
            container.start()
        return RunResult(container=container, created=False)

    ensure_network()
    kwargs: dict[str, Any] = {
        "image": image,
        "name": name,
        "labels": labels,
        "detach": detach,
        "network": Config.NETWORK,
        "environment": environment or {},
    }
    if ports:
        kwargs["ports"] = ports
    if volumes:
        kwargs["volumes"] = volumes
    if command is not None:
        kwargs["command"] = command
    if extra:
        kwargs.update(extra)

    try:
        container = client.containers.run(**kwargs)
    except Exception as exc:  # noqa: BLE001 - normalised below
        # A failed run (e.g. a port bind error) can leave a half-created
        # container behind, which would block every subsequent attempt. Remove
        # it so retries start clean, then surface an actionable message.
        _cleanup_failed(client, name)
        raise _friendly_run_error(exc, name=name, ports=ports) from exc
    return RunResult(container=container, created=True)


def _cleanup_failed(client: Any, name: str) -> None:
    """Best-effort removal of a half-created container after a failed run."""
    try:
        leftover = client.containers.list(all=True, filters={"name": f"^{name}$"})
        for c in leftover:
            c.remove(force=True)
    except Exception:  # noqa: BLE001 - cleanup must never mask the real error
        pass


def _friendly_run_error(exc: Exception, *, name: str, ports: dict | None) -> Exception:
    """Translate a raw Docker run error into a friendly :class:`FinError`.

    Port-allocation clashes get a targeted hint; everything else is wrapped so
    the caller still renders a clean panel rather than a traceback.
    """
    message = str(getattr(exc, "explanation", None) or exc)
    if (
        "port is already allocated" in message
        or "address already in use" in message.lower()
    ):
        host_ports = (
            ", ".join(str(v) for v in (ports or {}).values() if v is not None)
            or "its published ports"
        )
        return FinError(
            f"Could not start [bold]{name}[/bold]: {host_ports} already in use.\n"
            "Another process (often another local reverse proxy, or a system "
            "web server) is holding the port.\n"
            "Free it, then run 'fin up' again — stop whatever is listening on "
            "that port, or remove the conflicting container.",
            title="Port In Use",
        )
    return FinError(
        f"Could not start {name}: {message}", title="Container Start Failed"
    )
