"""Plug management commands: ``fin plugs list|info|search|install|uninstall``."""

from __future__ import annotations

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.plugs.registry import Registry
from fincli.ui.console import console, error, info, success


@reserved("plugs", help="Manage plugs: list | info <name> | search <q> | install <name> | uninstall <name>.", group="Plugs")
def plugs(args: list[str]) -> int:
    sub = args[0] if args else "list"
    target = args[1] if len(args) > 1 else None

    registry = Registry()
    try:
        if sub in ("list", "ls"):
            return _list(registry)
        if sub == "info":
            return _info(registry, target)
        if sub == "search":
            return _search(registry, target)
        if sub == "install":
            return _install(registry, target)
        if sub == "uninstall":
            return _uninstall(registry, target)
        error(f"Unknown 'plugs' subcommand: {sub}.", title="Invalid Argument")
        return EXIT_USER
    finally:
        registry.close()


def _list(registry: Registry) -> int:
    from rich.table import Table

    records = registry.all()
    if not records:
        info("No plugs installed.")
        return EXIT_OK
    table = Table(title="Installed Plugs", header_style="bold cyan", expand=False)
    table.add_column("Name", style="bold")
    table.add_column("Version", style="magenta")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Commands")
    type_colors = {"APP": "green", "ASSET": "cyan", "GLOBAL": "yellow"}
    for r in records:
        color = type_colors.get(r.plug_type, "white")
        table.add_row(
            r.name,
            r.version,
            f"[{color}]{r.plug_type}[/{color}]",
            "[green]loaded[/green]",
            r.commands or "-",
        )
    console.print(table)
    return EXIT_OK


def _info(registry: Registry, name: str | None) -> int:
    if not name:
        error("Usage: fin plugs info <name>", title="Invalid Argument")
        return EXIT_USER
    r = registry.get(name)
    info(f"[bold]{r.name}[/bold] v{r.version}")
    console.print(f"  type:        {r.plug_type}")
    console.print(f"  description: {r.description or '-'}")
    console.print(f"  commands:    {r.commands or '-'}")
    console.print(f"  path:        [dim]{r.path}[/dim]")
    return EXIT_OK


def _search(registry: Registry, query: str | None) -> int:
    if not query:
        error("Usage: fin plugs search <query>", title="Invalid Argument")
        return EXIT_USER
    results = registry.search(query)  # raises FinError (Not Implemented) for now
    for item in results:
        console.print(f"  {item}")
    return EXIT_OK


def _install(registry: Registry, name: str | None) -> int:
    if not name:
        error("Usage: fin plugs install <name|git-url>", title="Invalid Argument")
        return EXIT_USER
    dest = registry.install(name)
    success(f"Installed plug into [bold]{dest}[/bold]")
    return EXIT_OK


def _uninstall(registry: Registry, name: str | None) -> int:
    if not name:
        error("Usage: fin plugs uninstall <name>", title="Invalid Argument")
        return EXIT_USER
    path = registry.uninstall(name)
    success(f"Uninstalled [bold]{name}[/bold] (removed {path})")
    return EXIT_OK
