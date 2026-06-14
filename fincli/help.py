"""Help rendering for Fin — top-level overview and per-command help.

Two entry points:

* :func:`print_overview` — the curated list of all commands (``fin --help``).
* :func:`print_command_help` — detailed help for a single command, reserved
  *or* plug-contributed (``fin <command> --help`` / ``fin help <command>``).

Per-command help is introspected, never executed: for reserved commands it
reads the :class:`~fincli.commands.ReservedCommand` metadata; for plug commands
it reads the :class:`~fincli.plugs.base.PlugCommand` plus the owning plug's
:meth:`~fincli.plugs.base.FinPlug.env_spec`.
"""

from __future__ import annotations

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from fincli.app import App
from fincli.core.env import ProjectEnv
from fincli.ui.console import console

#: Flags that mean "show help" anywhere in an argv.
HELP_FLAGS = {"-h", "--help"}


def wants_help(args: list[str]) -> bool:
    """True if a help flag appears anywhere in *args*."""
    return any(a in HELP_FLAGS for a in args)


# --------------------------------------------------------------------------- #
# Top-level overview
# --------------------------------------------------------------------------- #
def print_overview() -> None:
    """Render the curated help / command overview (``fin --help``)."""
    from fincli.commands import RESERVED_CANONICAL, load_reserved

    load_reserved()
    app = App()
    console.print(
        Panel.fit(
            f"[bold cyan]{app.name}[/bold cyan] [dim]v{app.version}[/dim]\n{app.tagline}",
            border_style="cyan",
        )
    )
    console.print("[dim]Usage:[/dim] [bold]fin <command> [args...][/bold]")
    console.print("[dim]Help for a command:[/dim] [bold]fin <command> --help[/bold]\n")

    groups: dict[str, list] = {}
    for cmd in RESERVED_CANONICAL.values():
        groups.setdefault(cmd.group, []).append(cmd)

    for group_name in sorted(groups):
        table = Table(
            title=group_name,
            header_style="bold cyan",
            title_justify="left",
            expand=False,
        )
        table.add_column("Command", style="bold")
        table.add_column("Aliases", style="magenta")
        table.add_column("Description")
        for cmd in sorted(groups[group_name], key=lambda c: c.name):
            table.add_row(escape(cmd.name), escape(", ".join(cmd.aliases) or "-"), escape(cmd.help))
        console.print(table)

    # Plug commands, grouped by plug (only if any plugs are loaded).
    _print_plug_overview()

    console.print(
        "\n[dim]Plug commands are available when the matching plug is configured "
        "via FIN_APP / FIN_PLUGS. Run 'fin plugs list' to see loaded plugs.[/dim]"
    )


def _print_plug_overview() -> None:
    """List plug-contributed commands grouped by plug, best-effort."""
    try:
        from fincli.plugs.loader import load_all

        env = ProjectEnv.load()
    except Exception:  # noqa: BLE001 - overview must never crash
        return

    relevant = []
    try:
        loaded = load_all()
    except Exception:  # noqa: BLE001
        return

    for lp in loaded:
        cmds = lp.instance.commands()
        if cmds:
            relevant.append((lp.instance, cmds))

    for plug, cmds in relevant:
        title = f"Plug: {escape(plug.name)}"
        table = Table(title=title, header_style="bold cyan", title_justify="left", expand=False)
        table.add_column("Command", style="bold")
        table.add_column("Aliases", style="magenta")
        table.add_column("Description")
        seen = set()
        for cmd in cmds.values():
            if cmd.name in seen:
                continue
            seen.add(cmd.name)
            table.add_row(escape(cmd.name), escape(", ".join(cmd.aliases) or "-"), escape(cmd.help))
        console.print(table)


# --------------------------------------------------------------------------- #
# Per-command help
# --------------------------------------------------------------------------- #
def print_command_help(name: str, env: ProjectEnv | None = None) -> bool:
    """Render detailed help for a single command.

    Returns True if the command was found (reserved or plug), False otherwise.
    """
    from fincli.commands import RESERVED_COMMANDS, load_reserved

    load_reserved()

    # Reserved command?
    if name in RESERVED_COMMANDS:
        _print_reserved_help(RESERVED_COMMANDS[name])
        return True

    # Plug command?
    env = env or ProjectEnv.load()
    found = _print_plug_command_help(name, env)
    return found


def _print_reserved_help(cmd) -> None:
    """Render help for a reserved command from its metadata.

    Author-supplied strings (help text, usage, subcommand/option labels) may
    legitimately contain ``[...]`` (e.g. ``[asset|all]``); these are escaped so
    Rich does not mistake them for markup tags and silently drop them.
    """
    aliases = f"  [dim](aliases: {escape(', '.join(cmd.aliases))})[/dim]" if cmd.aliases else ""
    usage = cmd.usage or f"fin {cmd.name} [args...]"
    body_lines = [
        f"[bold cyan]fin {escape(cmd.name)}[/bold cyan]{aliases}",
        "",
        escape(cmd.help or "(no description)"),
        "",
        f"[dim]Usage:[/dim] [bold]{escape(usage)}[/bold]",
    ]
    console.print(
        Panel(
            "\n".join(body_lines),
            border_style="cyan",
            title="[cyan]Command Help[/cyan]",
            expand=False,
        )
    )

    if cmd.subcommands:
        table = Table(title="Subcommands", header_style="bold cyan", title_justify="left", expand=False)
        table.add_column("Subcommand", style="bold")
        table.add_column("Description")
        for sub_name, sub_help in cmd.subcommands:
            table.add_row(escape(sub_name), escape(sub_help))
        console.print(table)

    if cmd.options:
        table = Table(title="Options", header_style="bold cyan", title_justify="left", expand=False)
        table.add_column("Flag", style="magenta")
        table.add_column("Description")
        for flag, flag_help in cmd.options:
            table.add_row(escape(flag), escape(flag_help))
        console.print(table)

    if cmd.examples:
        console.print("[bold cyan]Examples:[/bold cyan]")
        for ex in cmd.examples:
            console.print(f"  [green]$[/green] {escape(ex)}")


def _print_plug_command_help(name: str, env: ProjectEnv) -> bool:
    """Render help for a plug-contributed command. Returns True if found."""
    from fincli.plugs.loader import load_all

    try:
        loaded = load_all()
    except Exception:  # noqa: BLE001
        loaded = []

    for lp in loaded:
        plug = lp.instance
        cmds = plug.commands()
        match = None
        if name in cmds:
            match = cmds[name]
        else:
            for c in cmds.values():
                if name in c.aliases:
                    match = c
                    break
        if match is None:
            continue

        aliases = f"  [dim](aliases: {escape(', '.join(match.aliases))})[/dim]" if match.aliases else ""
        body = [
            f"[bold cyan]fin {escape(match.name)}[/bold cyan]{aliases}",
            f"[dim]from plug:[/dim] [magenta]{escape(plug.name)}[/magenta] v{escape(plug.version)}",
            "",
            escape(match.help or "(no description)"),
            "",
            f"[dim]Usage:[/dim] [bold]fin {escape(match.name)} [args...][/bold]",
        ]
        console.print(
            Panel("\n".join(body), border_style="cyan", title="[cyan]Plug Command Help[/cyan]", expand=False)
        )

        # Show the plug's env requirements — useful context for plug commands.
        spec = plug.env_spec()
        if spec.variables:
            table = Table(
                title=f"Environment ({plug.name})",
                header_style="bold cyan",
                title_justify="left",
                expand=False,
            )
            table.add_column("Variable", style="bold")
            table.add_column("Required", justify="center")
            table.add_column("Default", style="magenta")
            table.add_column("Description")
            for var in spec.variables:
                req = "[red]yes[/red]" if var.required else "no"
                choices = (
                    f" [dim](one of: {escape(', '.join(var.choices))})[/dim]"
                    if var.choices else ""
                )
                table.add_row(
                    escape(var.name),
                    req,
                    escape(var.default or "-"),
                    escape(var.description or "") + choices,
                )
            console.print(table)
        return True

    return False
