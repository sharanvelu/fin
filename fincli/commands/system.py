"""System lifecycle commands: up, down, stop.

These are reserved — they read information from plugs (the primary container
spec, asset specs) but never let a plug execute container actions. All Docker
work goes through the orchestrator / core helpers.

Teardown scopes:
    fin down            → this project's containers (app + worker)
    fin down asset      → all shared asset containers
    fin down all        → every Fin-managed container
    fin stop [asset|all]→ same scopes, stop without removing
    -f / --force        → force removal
"""

from __future__ import annotations

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.core.containers import list_containers
from fincli.core.database import ensure_project_database
from fincli.core.env import ProjectEnv
from fincli.core.errors import FinError
from fincli.core.orchestrator import start_assets_for, start_primary
from fincli.core.proxy import ensure_proxy
from fincli.plugs.base import PlugType
from fincli.plugs.loader import load_by_name
from fincli.ui.console import error, info, success, warning


# --------------------------------------------------------------------------- #
# up
# --------------------------------------------------------------------------- #
@reserved("up", help="Start the project's containers (proxy, assets, primary).")
def up(args: list[str]) -> int:
    env = ProjectEnv.load()

    app_plug_name = env.app_plug
    if not app_plug_name:
        raise FinError(
            "No primary app plug configured. Set [bold]FIN_APP[/bold] in your "
            ".env (e.g. FIN_APP=laravel).",
            title="Missing FIN_APP",
        )

    lp = load_by_name(app_plug_name)
    if lp is None:
        raise FinError(f"App plug '{app_plug_name}' is not installed.", title="Plug Not Found")
    if lp.plug_type != PlugType.APP:
        raise FinError(
            f"Plug '{app_plug_name}' is type {lp.plug_type.value}, not APP.",
            title="Wrong Plug Type",
        )

    plug = lp.instance

    # Validate the plug's env contract (collects all problems at once).
    plug.env_spec().validate(env)

    # 1) Proxy (always-on, built-in).
    ensure_proxy()

    # 2) Asset containers (enabled assets + any in FIN_PLUGS).
    started_assets = start_assets_for(env)

    # 3) Primary container (mounts cwd into the plug-defined path).
    spec = plug.primary_spec(env)
    if spec is None:
        raise FinError(
            f"App plug '{app_plug_name}' did not provide a primary container spec.",
            title="Invalid Plug",
        )
    start_primary(spec, env)

    # 4) Auto-create the project database if applicable.
    if started_assets or env.get("DB_DATABASE"):
        ensure_project_database(env)

    site = env.get("FIN_SITE")
    if site:
        success(f"[bold]{env.project_name}[/bold] is up at [cyan]http://{site}[/cyan]")
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
    for c in containers:
        try:
            if remove:
                c.remove(force=force or c.status == "running")
            else:
                if c.status == "running":
                    c.stop()
            success(f"{action[:-3]}ed [bold]{c.name}[/bold]")
        except Exception as exc:  # noqa: BLE001 - report, keep going
            warning(f"Could not {action.lower()[:-3]} {c.name}: {exc}")
    return EXIT_OK


@reserved(
    "down",
    help="Stop and remove containers. Scopes: [asset|all]; -f to force.",
)
def down(args: list[str]) -> int:
    return _teardown(args, remove=True)


@reserved(
    "stop",
    help="Stop containers without removing. Scopes: [asset|all].",
)
def stop(args: list[str]) -> int:
    return _teardown(args, remove=False)
