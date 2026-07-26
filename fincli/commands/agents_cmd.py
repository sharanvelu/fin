"""AI-agent instruction files: ``fin agents list|install``.

Generates per-agent instruction files into the current project so AI coding
agents (Claude Code, Cursor, Codex, …) run project commands through ``fin``
instead of directly on the host. See :mod:`fincli.agents`.
"""

from __future__ import annotations

from pathlib import Path

from fincli.agents import DEFAULT_TARGETS, TARGETS, build_content, install_files
from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.core.env import ProjectEnv
from fincli.ui.console import console, error, hint, info, success


@reserved(
    "agents",
    help="Generate files that teach AI coding agents to run commands via fin.",
    group="System",
    usage="fin agents <list|install> [agent ...|all]",
    subcommands=(
        ("list", "List supported agents and the files they generate."),
        (
            "install [agent ...|all]",
            f"Generate instruction files into this project (default: {' '.join(DEFAULT_TARGETS)}).",
        ),
    ),
    examples=(
        "fin agents install",
        "fin agents install claude cursor",
        "fin agents install all",
    ),
)
def agents(args: list[str]) -> int:
    sub = args[0] if args else "list"
    if sub in ("list", "ls"):
        return _list()
    if sub == "install":
        return _install(args[1:])
    error(f"Unknown 'agents' subcommand: {sub}.", title="Invalid Argument")
    return EXIT_USER


def _list() -> int:
    from rich.table import Table

    cwd = Path.cwd()
    table = Table(title="AI Agent Targets", header_style="bold cyan", expand=False)
    table.add_column("Agent", style="bold")
    table.add_column("Writes")
    table.add_column("Default")
    table.add_column("Present")
    for target in TARGETS.values():
        present = (cwd / target.path).exists()
        table.add_row(
            f"{target.name}\n[dim]{target.label}[/dim]",
            target.path,
            "[green]yes[/green]" if target.name in DEFAULT_TARGETS else "-",
            "[green]yes[/green]" if present else "-",
        )
    console.print(table)
    hint(r"Run 'fin agents install \[agent ...|all]' inside a project to generate them.")
    return EXIT_OK


def _install(args: list[str]) -> int:
    names = list(dict.fromkeys(a.lower() for a in args)) or list(DEFAULT_TARGETS)
    if "all" in names:
        names = list(TARGETS)
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        error(
            f"Unknown agent(s): {', '.join(unknown)}. "
            f"Available: {', '.join(TARGETS)} (or 'all').",
            title="Invalid Argument",
        )
        return EXIT_USER

    env = ProjectEnv.load()
    if not env.fin_vars():
        error(
            f"No FIN_* variables found in {env.cwd / '.env'} — this doesn't "
            "look like a Fin project.",
            title="Not a Fin Project",
        )
        hint("cd into a project with FIN_* vars in its .env, then re-run.")
        return EXIT_USER

    content = build_content(env)
    if not content.commands:
        info(
            "No plug commands found (is the FIN_APP plug installed?) — "
            "generating generic instructions with core commands only."
        )

    # Many targets share AGENTS.md — write each distinct file once.
    files: list = []
    seen_paths: set[str] = set()
    for n in names:
        for gf in TARGETS[n].render(content):
            if gf.path not in seen_paths:
                seen_paths.add(gf.path)
                files.append(gf)

    for gf, action in install_files(env.cwd, files):
        merged = " [dim](merged into fin block)[/dim]" if gf.managed_block else ""
        if action == "unchanged":
            info(f"{gf.path} already up to date")
        elif action == "skipped":
            note = f" — {gf.skip_hint}" if gf.skip_hint else ""
            info(f"{gf.path} exists, left untouched{note}")
        else:
            success(f"{action} [bold]{gf.path}[/bold]{merged}")
    hint("Commit these files so every teammate's agent picks them up.")
    return EXIT_OK
