"""Fin CLI entrypoint.

We deliberately do our own argv dispatch (rather than a pure Typer app) because
command resolution is dynamic: a sub-command may be a reserved system command
*or* contributed by a plug discovered at runtime. Typer/Click still powers
``--help`` and the curated top-level command list for discoverability.

Flow:
    fin <command> [args...]
      → load project env (.env in cwd)
      → resolve: reserved → FIN_APP → FIN_PLUGS → GLOBAL
      → run, rendering any error as a Rich panel with the right exit code.
"""

from __future__ import annotations

import sys

from fincli.app import EXIT_OK, EXIT_USER, App
from fincli.core.env import ProjectEnv
from fincli.core.errors import handle_errors
from fincli.resolver import resolve


def _print_help() -> None:
    """Render the curated help / command overview."""
    from fincli.commands import RESERVED_CANONICAL, load_reserved
    from fincli.ui.console import console
    from rich.table import Table
    from rich.panel import Panel

    load_reserved()
    app = App()
    console.print(
        Panel.fit(
            f"[bold cyan]{app.name}[/bold cyan] [dim]v{app.version}[/dim]\n{app.tagline}",
            border_style="cyan",
        )
    )

    # Group reserved commands for display.
    groups: dict[str, list] = {}
    for cmd in RESERVED_CANONICAL.values():
        groups.setdefault(cmd.group, []).append(cmd)

    for group_name in sorted(groups):
        table = Table(title=group_name, header_style="bold cyan", title_justify="left", expand=False)
        table.add_column("Command", style="bold")
        table.add_column("Aliases", style="magenta")
        table.add_column("Description")
        for cmd in sorted(groups[group_name], key=lambda c: c.name):
            table.add_row(cmd.name, ", ".join(cmd.aliases) or "-", cmd.help)
        console.print(table)

    console.print(
        "\n[dim]Plug commands (e.g. artisan, composer) are available when the "
        "matching plug is configured via FIN_APP / FIN_PLUGS.[/dim]"
    )
    console.print("[dim]Run 'fin plugs list' to see loaded plugs.[/dim]")


@handle_errors
def _dispatch(argv: list[str]) -> int:
    """Resolve and run a single command invocation."""
    if not argv or argv[0] in ("-h", "--help", "help"):
        # `fin help <command>` could be deepened later; for now show overview.
        _print_help()
        return EXIT_OK

    if argv[0] in ("-v", "--version", "version"):
        from fincli.ui.console import console

        console.print(App().banner())
        return EXIT_OK

    name, args = argv[0], argv[1:]
    env = ProjectEnv.load()

    resolution = resolve(name, args, env)
    if resolution is None:
        from fincli.ui.console import error, hint

        error(f"Unknown command: [bold]{name}[/bold]", title="Unknown Command")
        hint("Run 'fin --help' to see available commands.")
        return EXIT_USER

    return resolution.run() or EXIT_OK


def main() -> None:
    """Console-script entrypoint."""
    exit_code = _dispatch(sys.argv[1:])
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
