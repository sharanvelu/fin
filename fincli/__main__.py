"""Fin CLI entrypoint.

We deliberately do our own argv dispatch (rather than a pure Typer app) because
command resolution is dynamic: a sub-command may be a reserved system command
*or* contributed by a plug discovered at runtime. Help is rendered by
:mod:`fincli.help` for both the top-level overview and per-command pages.

Flow:
    fin <command> [args...]
      → if no args / help flag: render help (overview or per-command)
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


@handle_errors
def _dispatch(argv: list[str]) -> int:
    """Resolve and run a single command invocation."""
    from fincli.help import HELP_FLAGS, print_overview, wants_help

    # No args, or a bare help/-h/--help → top-level overview.
    if not argv or argv[0] in HELP_FLAGS:
        print_overview()
        return EXIT_OK

    if argv[0] in ("-v", "--version", "version"):
        from fincli.ui.console import console

        console.print(App().banner())
        return EXIT_OK

    # `fin help [command]` → overview or per-command help.
    if argv[0] == "help":
        if len(argv) < 2:
            print_overview()
            return EXIT_OK
        return _show_command_help(argv[1])

    name, args = argv[0], argv[1:]

    # `fin <command> --help` / `-h` → per-command help (before running it).
    if wants_help(args):
        return _show_command_help(name)

    env = ProjectEnv.load()

    resolution = resolve(name, args, env)
    if resolution is None:
        from fincli.ui.console import error, hint

        error(f"Unknown command: [bold]{name}[/bold]", title="Unknown Command")
        hint("Run 'fin --help' to see available commands.")
        return EXIT_USER

    return resolution.run() or EXIT_OK


def _show_command_help(name: str) -> int:
    """Render per-command help; report cleanly if the command is unknown."""
    from fincli.help import print_command_help

    if print_command_help(name):
        return EXIT_OK
    from fincli.ui.console import error, hint

    error(f"Unknown command: [bold]{name}[/bold]", title="Unknown Command")
    hint("Run 'fin --help' to see available commands.")
    return EXIT_USER


def main() -> None:
    """Console-script entrypoint."""
    exit_code = _dispatch(sys.argv[1:])
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
