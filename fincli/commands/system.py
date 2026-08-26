"""System lifecycle commands: up, down, stop.

These are reserved — they read information from plugs (the primary container
spec, asset specs) but never let a plug execute container actions. All Docker
work goes through the orchestrator / core helpers.

Teardown scopes:
    fin down            → this project's containers (app + worker)
    fin down asset      → all shared asset containers
    fin down all        → every Fin-managed container
    fin stop [asset|all]→ same scopes, stop without removing
    -f / --force        → with `down`, also force-remove non-running containers
                          (running ones are force-removed even without it);
                          `stop` ignores the flag
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.config import Config
from fincli.core.containers import list_containers
from fincli.core.database import ensure_project_database
from fincli.core.env import ProjectEnv
from fincli.core.errors import FinError
from fincli.core.images import prefetch_images
from fincli.core.orchestrator import asset_specs_for, start_assets_for, start_primary
from fincli.core.proxy import ensure_proxy
from fincli.plugs.base import PlugType
from fincli.plugs.loader import load_by_name
from fincli.ui.console import confirm, console, error, info, success, warning
from fincli.ui.spinners import live_checklist

#: Upper bound on concurrent stop/remove operations during teardown.
MAX_CONCURRENT_TEARDOWNS = 8


# --------------------------------------------------------------------------- #
# up
# --------------------------------------------------------------------------- #
def _ensure_plugs_installed(env: ProjectEnv, app_plug_name: str) -> None:
    """Offer to install any FIN_APP / FIN_PLUGS plugs that are missing.

    If the user accepts, each missing plug is installed from the catalog via
    the registry; if they decline, we abort with the manual install commands.
    """
    wanted = [app_plug_name] + [n for n in env.plugs if n != app_plug_name]
    missing = [n for n in wanted if load_by_name(n) is None]
    if not missing:
        return

    plural = len(missing) > 1
    listing = ", ".join(f"[bold]{n}[/bold]" for n in missing)
    warning(
        f"{'These plugs are' if plural else 'This plug is'} not installed: {listing}"
    )
    if not confirm(
        f"Do you want to install {'them' if plural else 'it'} to proceed?",
        default=True,
    ):
        commands = "\n".join(f"  fin plugs install {n}" for n in missing)
        raise FinError(
            f"Cannot start without the missing plug{'s' if plural else ''}. "
            f"Install {'them' if plural else 'it'} with:\n{commands}",
            title="Plugs Not Installed",
        )

    from fincli.plugs.registry import Registry
    from fincli.ui.spinners import live_panel

    # The install log gets its own cyan box (mirroring the red error panel)
    # so it stands apart from the container output that `fin up` prints next.
    console.print()
    registry = Registry()
    try:
        with live_panel("Installing plugs", border_style="cyan") as add:
            for name in missing:
                add(f"[dim]Fetching {name} from the plug catalog…[/dim]")
                dest = registry.install(name)
                add(
                    f"[green]✓[/green] Installed plug [bold]{name}[/bold] [dim]({dest})[/dim]"
                )
    finally:
        registry.close()

    console.print()
    info(
        "You can also manage or install plugs with [bold]fin plugs "
        "<action>[/bold] (list | info | search | install | uninstall)."
    )
    console.print()


@reserved(
    "up",
    help="Start the project's containers (proxy, assets, primary).",
    usage="fin up",
    examples=("fin up",),
)
def up(args: list[str]) -> int:
    env = ProjectEnv.load()

    app_plug_name = env.app_plug
    if not app_plug_name:
        raise FinError(
            "No primary app plug configured. Set [bold]FIN_APP[/bold] in your "
            ".env (e.g. FIN_APP=laravel).",
            title="Missing FIN_APP",
        )

    # Prompt to install any missing FIN_APP / FIN_PLUGS plugs before starting.
    _ensure_plugs_installed(env, app_plug_name)

    lp = load_by_name(app_plug_name)
    if lp is None:
        raise FinError(
            f"App plug '{app_plug_name}' is not installed.", title="Plug Not Found"
        )
    if lp.plug_type != PlugType.APP:
        raise FinError(
            f"Plug '{app_plug_name}' is type {lp.plug_type.value}, not APP.",
            title="Wrong Plug Type",
        )

    plug = lp.instance

    # Validate the plug's env contract (collects all problems at once).
    plug.env_spec().validate(env)

    # Resolve every container spec first so all missing images download
    # concurrently up front, instead of each start blocking on its own pull.
    asset_specs = asset_specs_for(env)
    spec = plug.primary_spec(env)
    if spec is None:
        raise FinError(
            f"App plug '{app_plug_name}' did not provide a primary container spec.",
            title="Invalid Plug",
        )
    prefetch_images([Config.PROXY_IMAGE, *(s.image for s in asset_specs), spec.image])

    # 1) Proxy (always-on, built-in).
    ensure_proxy()

    # 2) Asset containers (enabled assets + any in FIN_PLUGS).
    started_assets = start_assets_for(env, specs=asset_specs)

    # 3) Primary container (mounts cwd into the plug-defined path).
    start_primary(spec, env)

    # 4) Auto-create the project database if applicable.
    if started_assets or env.get("DB_DATABASE"):
        ensure_project_database(env)

    site = env.get("FIN_SITE")
    if site:
        urls = ", ".join(
            f"[cyan]http://{h}[/cyan]" for h in [site, *env.additional_hosts]
        )
        success(f"[bold]{env.project_name}[/bold] is up at {urls}")
    else:
        success(f"[bold]{env.project_name}[/bold] is up.")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# down / stop (shared implementation)
# --------------------------------------------------------------------------- #
def _scope_containers(scope: str, env: ProjectEnv):
    """Return the containers targeted by a teardown *scope*."""
    if scope == "all":
        return list_containers(all_=True)
    if scope == "asset":
        return list_containers(all_=True, FIN_TYPE="asset")
    # default: this project only (app + worker), not shared assets/proxy.
    return list_containers(all_=True, FIN_PROJECT=env.project_name)


def _teardown(args: list[str], *, remove: bool) -> int:
    force = "-f" in args or "--force" in args
    if force and not remove:
        warning("`stop` ignores -f/--force (only `down` force-removes).")
    positional = [a for a in args if not a.startswith("-")]
    scope = positional[0] if positional else "project"

    if scope not in ("project", "asset", "all"):
        error(f"Unknown scope '{scope}'. Use: asset | all", title="Invalid Argument")
        return EXIT_USER

    env = ProjectEnv.load()
    containers = _scope_containers(scope, env)

    if not containers:
        info("No matching Fin containers.")
        return EXIT_OK

    action = "Removing" if remove else "Stopping"
    done = "Removed" if remove else "Stopped"

    def teardown_one(c: Any) -> None:
        if remove:
            c.remove(force=force or c.status == "running")
        elif c.status == "running":
            c.stop()

    # Stops/removes run concurrently: a graceful `stop` waits up to ~10s per
    # container, so doing them one by one scales with the container count.
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

    if failed:
        verb = "remove" if remove else "stop"
        warning(f"Could not {verb} {failed} of {len(containers)} containers.")
    return EXIT_OK


@reserved(
    "down",
    help="Stop and remove containers. Scopes: [asset|all]. Running containers "
    "are force-removed even without -f.",
    usage="fin down [asset|all] [-f]",
    subcommands=(
        ("(none)", "Remove this project's containers (app + worker)."),
        ("asset", "Remove all shared asset containers."),
        ("all", "Remove every Fin-managed container (incl. proxy & assets)."),
    ),
    options=(
        (
            "-f, --force",
            "Also force-remove non-running containers "
            "(running ones are always force-removed).",
        ),
    ),
    examples=("fin down", "fin down asset", "fin down all -f"),
)
def down(args: list[str]) -> int:
    return _teardown(args, remove=True)


@reserved(
    "stop",
    help="Stop containers without removing. Scopes: [asset|all].",
    usage="fin stop [asset|all]",
    subcommands=(
        ("(none)", "Stop this project's containers (app + worker)."),
        ("asset", "Stop all shared asset containers."),
        ("all", "Stop every Fin-managed container."),
    ),
    examples=("fin stop", "fin stop asset", "fin stop all"),
)
def stop(args: list[str]) -> int:
    return _teardown(args, remove=False)
