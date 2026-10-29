"""Turns plug ContainerSpecs into running containers.

This is where Fin acts *on behalf of* plugs: a plug only ever returns a
:class:`~fincli.plugs.base.ContainerSpec`; the orchestrator is the sole code
path that attaches the standard labels, wires Traefik routing, mounts the
project directory, and calls Docker. Plugs never touch the daemon.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fincli.config import Config
from fincli.core.certs import install_certs
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
from fincli.ui.spinners import fin_spinner, live_checklist

#: Upper bound on concurrent stop/remove operations during teardown.
MAX_CONCURRENT_TEARDOWNS = 8


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
        # FIN_ADDITIONAL_HOSTS hosts ride along; FIN_SITE stays the anchor.
        labels.update(traefik_labels(site, spec.web_port, env.additional_hosts))

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
    # Install the user's CA certs if this plug opted in (runs every `up`;
    # idempotent, so certs added later are picked up without a recreate).
    if spec.install_certs:
        install_certs(result.container, spec)
    return result.container


def resolve_enabled_assets(env: ProjectEnv) -> list[Any]:
    """Return loaded ASSET plugs that should start for this project.

    Selection order of precedence:
        1. ``FIN_OVERRIDE_ASSETS`` env (comma-separated) — if set, it alone
           decides (assets named in ``FIN_PLUGS`` are *not* added).
        2. Otherwise, the persisted enable flags from ``fin config
           enable/disable``, plus any assets named in ``FIN_PLUGS``.
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

    # Assets explicitly listed in FIN_PLUGS are also included.
    for name in env.plugs:
        lp = load_by_name(name)
        if lp and lp.plug_type == PlugType.ASSET:
            selected[lp.instance.name] = lp

    return list(selected.values())


def asset_specs_for(env: ProjectEnv) -> list[ContainerSpec]:
    """Resolve every enabled asset plug's ContainerSpecs without starting them.

    Split out from :func:`start_assets_for` so ``up`` can collect all images
    (and prefetch the missing ones concurrently) before any container starts.
    """
    specs: list[ContainerSpec] = []
    for lp in resolve_enabled_assets(env):
        specs.extend(lp.instance.asset_specs(env))
    return specs


def start_assets_for(
    env: ProjectEnv, specs: list[ContainerSpec] | None = None
) -> list[Any]:
    """Start every enabled asset plug's containers. Returns started containers.

    Pass *specs* (from :func:`asset_specs_for`) to reuse an earlier resolution
    instead of asking each plug for its specs a second time.
    """
    if specs is None:
        specs = asset_specs_for(env)
    return [start_asset(spec) for spec in specs]


def teardown_containers(
    containers: list[Any], *, remove: bool, force: bool = False
) -> int:
    """Concurrently stop — and with *remove*, delete — the given containers.

    Containers tear down independently of each other, but a graceful stop
    waits up to ~10s for the process to exit, so they run in a worker pool
    with a live checklist updating as each one finishes. Semantics:

    * ``remove=False`` — gracefully stop running containers; leave the rest.
    * ``remove=True`` — gracefully stop running containers, then remove every
      container (running or not).
    * ``remove=True, force=True`` — force-remove everything immediately
      (kill, no graceful shutdown).

    Each failure renders inline on its checklist line; the number of failures
    is returned so callers can summarise (teardown never raises per-container).
    """
    action = "Removing" if remove else "Stopping"
    done = "Removed" if remove else "Stopped"

    def teardown_one(c: Any) -> None:
        if not remove:
            if c.status == "running":
                c.stop()
            return
        if force:
            c.remove(force=True)
            return
        if c.status == "running":
            c.stop()
        c.remove()

    failed = 0
    names = [c.name for c in containers]
    with live_checklist(f"{action} containers", names) as set_line:
        with ThreadPoolExecutor(
            max_workers=min(MAX_CONCURRENT_TEARDOWNS, len(containers))
        ) as pool:
            futures = {pool.submit(teardown_one, c): c for c in containers}
            for future in as_completed(futures):
                c = futures[future]
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 - report, keep going
                    failed += 1
                    set_line(c.name, f"[red]✗[/red] {c.name} [dim]— {exc}[/dim]")
                else:
                    set_line(c.name, f"[green]✓[/green] {done} [bold]{c.name}[/bold]")
    return failed


def start_asset(spec: ContainerSpec, fin_type: str = "asset") -> Any:
    """Start a shared asset/proxy container (idempotent, fixed name)."""
    name = spec.container_name or f"fin_{spec.service}"
    site = "-"
    labels = base_labels(
        fin_type=fin_type, service=spec.service, site=site, project="-"
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
    if spec.install_certs:
        install_certs(result.container, spec)
    return result.container
