"""Asset lifecycle command: ``fin asset up|stop|down``.

Manages the shared auxiliary containers (DB/redis/…) independently of any one
project. ``up`` ensures the proxy and starts every enabled asset; ``stop`` and
``down`` operate on all asset-typed containers.
"""

from __future__ import annotations

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.core.containers import list_containers
from fincli.core.env import ProjectEnv
from fincli.core.orchestrator import start_assets_for
from fincli.core.proxy import ensure_proxy
from fincli.ui.console import error, info, success, warning


@reserved(
    "asset",
    help="Manage shared asset containers: up | stop | down.",
    usage="fin asset <up|stop|down> [-f]",
    subcommands=(
        ("up", "Ensure the proxy and start every enabled asset container."),
        ("stop", "Stop all asset containers without removing them."),
        ("down", "Remove all asset containers (running ones are force-removed)."),
    ),
    options=(
        (
            "-f, --force",
            "With 'down': also force-remove non-running containers "
            "(running ones are always force-removed).",
        ),
    ),
    examples=("fin asset up", "fin asset stop", "fin asset down -f"),
)
def asset(args: list[str]) -> int:
    sub = args[0] if args else "up"
    rest = args[1:]

    if sub == "up":
        ensure_proxy()
        started = start_assets_for(ProjectEnv.load())
        if not started:
            info("No assets enabled. Enable one with 'fin config enable <asset>'.")
        return EXIT_OK

    if sub in ("stop", "down"):
        remove = sub == "down"
        force = "-f" in rest or "--force" in rest
        if force and not remove:
            warning("`stop` ignores -f/--force (only `down` force-removes).")
        containers = list_containers(all_=True, FIN_TYPE="asset")
        if not containers:
            info("No asset containers running.")
            return EXIT_OK
        for c in containers:
            try:
                if remove:
                    c.remove(force=force or c.status == "running")
                    success(f"Removed [bold]{c.name}[/bold]")
                else:
                    if c.status == "running":
                        c.stop()
                    success(f"Stopped [bold]{c.name}[/bold]")
            except Exception as exc:  # noqa: BLE001
                warning(f"Could not {sub} {c.name}: {exc}")
        return EXIT_OK

    error(
        f"Unknown 'asset' subcommand: {sub}. Use up | stop | down.",
        title="Invalid Argument",
    )
    return EXIT_USER
