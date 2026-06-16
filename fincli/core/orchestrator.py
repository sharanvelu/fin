"""Turns plug ContainerSpecs into running containers.

This is where Fin acts *on behalf of* plugs: a plug only ever returns a
:class:`~fincli.plugs.base.ContainerSpec`; the orchestrator is the sole code
path that attaches the standard labels, wires Traefik routing, mounts the
project directory, and calls Docker. Plugs never touch the daemon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fincli.config import Config
from fincli.core.containers import (
    base_labels,
    ensure_network,
    primary_container_name,
    run_container,
    traefik_labels,
)
from fincli.core.env import ProjectEnv
from fincli.plugs.base import ContainerSpec, PortMapping, VolumeMount
from fincli.ui.console import success
from fincli.ui.spinners import fin_spinner


def _ports_to_docker(ports: list[PortMapping]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in ports:
        key, host = p.as_docker()
        out[key] = host
    return out


def _volumes_to_docker(volumes: list[VolumeMount]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for v in volumes:
        out[v.host] = {"bind": v.container, "mode": v.mode}
    return out


def start_primary(spec: ContainerSpec, env: ProjectEnv) -> Any:
    """Start an APP plug's primary container for the current project.

    Mounts the current working directory into the container at
    ``spec.workdir_mount`` (host path = cwd, container path from the plug
    spec), applies Fin + Traefik labels, and publishes the spec's ports.
    """
    project = env.project_name
    name = spec.container_name or primary_container_name(project, spec.name_suffix)
    site = env.get("FIN_SITE", "-") or "-"

    labels = base_labels(
        fin_type="app",
        service=spec.service,
        site=f"http://{site}" if site != "-" else "-",
        project=project,
    )
    if spec.web_exposed and spec.web_port and site != "-":
        labels.update(traefik_labels(site, spec.web_port))

    volumes = list(spec.volumes)
    if spec.workdir_mount:
        # Bind the project directory (where `fin` was invoked) into the container.
        volumes.append(VolumeMount(host=str(env.cwd), container=spec.workdir_mount))

    ensure_network()
    with fin_spinner(f"Starting {name}…"):
        result = run_container(
            image=spec.image,
            name=name,
            labels=labels,
            environment=spec.environment,
            ports=_ports_to_docker(spec.ports),
            volumes=_volumes_to_docker(volumes),
            command=spec.command,
            extra=spec.extra,
        )
    verb = "Started" if result.created else "Already running:"
    success(f"{verb} [bold]{name}[/bold] [dim]({spec.image})[/dim]")
    return result.container


def resolve_enabled_assets(env: ProjectEnv) -> list[Any]:
    """Return loaded ASSET plugs that should start for this project.

    Selection order of precedence:
        1. ``FIN_OVERRIDE_ASSETS`` env (comma-separated) — if set, wins.
        2. The persisted enable flags from ``fin config enable/disable``.
    Plugs named in ``FIN_PLUGS`` that are assets are always included.
    """
    from fincli.core.store import is_asset_enabled
    from fincli.plugs.base import PlugType
    from fincli.plugs.loader import load_all, load_by_name

    override = env.get("FIN_OVERRIDE_ASSETS")
    selected: dict[str, Any] = {}

    if override:
        for name in [n.strip() for n in override.split(",") if n.strip()]:
            lp = load_by_name(name)
            if lp and lp.plug_type == PlugType.ASSET:
                selected[lp.instance.name] = lp
        return list(selected.values())

    # Persisted config: any asset explicitly enabled.
    for lp in load_all():
        if lp.plug_type == PlugType.ASSET and is_asset_enabled(lp.instance.name):
            selected[lp.instance.name] = lp

    # Assets explicitly listed in FIN_PLUGS are always included.
    for name in env.plugs:
        lp = load_by_name(name)
        if lp and lp.plug_type == PlugType.ASSET:
            selected[lp.instance.name] = lp

    return list(selected.values())


def start_assets_for(env: ProjectEnv) -> list[Any]:
    """Start every enabled asset plug's containers. Returns started containers."""
    started: list[Any] = []
    for lp in resolve_enabled_assets(env):
        for spec in lp.instance.asset_specs(env):
            started.append(start_asset(spec))
    return started


def start_asset(spec: ContainerSpec, fin_type: str = "asset") -> Any:
    """Start a shared asset/proxy container (idempotent, fixed name)."""
    name = spec.container_name or f"fin_{spec.service}"
    site = "-"
    labels = base_labels(
        fin_type=fin_type,
        service=spec.service,
        site=site, project="-"
    )
    if spec.web_exposed and spec.web_port:
        # Asset web UIs (e.g. a proxy dashboard) may route via a fixed host.
        host = spec.environment.get("FIN_ASSET_SITE", f"{spec.service}.localhost")
        labels.update(traefik_labels(host, spec.web_port))
        labels[Config.LABEL_SITE] = f"http://{host}"

    ensure_network()
    with fin_spinner(f"Starting {name}…"):
        result = run_container(
            image=spec.image,
            name=name,
            labels=labels,
            environment=spec.environment,
            ports=_ports_to_docker(spec.ports),
            volumes=_volumes_to_docker(spec.volumes),
            command=spec.command,
            extra=spec.extra,
        )
    verb = "Started" if result.created else "Already running:"
    success(f"{verb} [bold]{name}[/bold] [dim]({spec.image})[/dim]")
    return result.container
