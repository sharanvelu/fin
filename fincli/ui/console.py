"""The single Rich Console instance plus standard message helpers.

Per Fin's output standards, *all* terminal output flows through this module.
Nothing outside ``fincli/ui`` should call ``print()`` directly.

Message conventions:
    success → ``✓`` green      error   → ``✗`` red
    warning → ``⚠`` yellow     info    → ``ℹ`` cyan
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

#: The one shared console for normal output.
console: Console = Console()
#: A dedicated stderr console for errors/warnings, so output can be piped.
err_console: Console = Console(stderr=True)


def success(message: str) -> None:
    """Print a green success line."""
    console.print(f"[green]✓[/green] {message}")


def error(message: str, *, title: str = "Error") -> None:
    """Print a red error panel to stderr (never a raw traceback).

    *message* may contain Rich markup (e.g. ``[bold]name[/bold]``); it is
    parsed and rendered with a red base style.
    """
    body = Text.from_markup(message)
    body.stylize("red")
    console.print()
    err_console.print(
        Panel(
            body,
            title=f"[red]✗ {title}[/red]",
            border_style="red",
            expand=False,
        )
    )


def warning(message: str) -> None:
    """Print a yellow warning line to stderr."""
    err_console.print(f"[yellow]⚠[/yellow] {message}")


def info(message: str) -> None:
    """Print a cyan informational line."""
    console.print(f"[cyan]ℹ[/cyan] {message}")


def hint(message: str) -> None:
    """Print a dim helper hint."""
    console.print(f"[dim]{message}[/dim]")


def print(*args, **kwargs) -> None:  # noqa: A001 - intentional Rich passthrough
    """Thin passthrough to the shared console's ``print``."""
    console.print(*args, **kwargs)


def confirm(message: str, *, default: bool = False) -> bool:
    """Ask a yes/no question and return the answer.

    Uses Rich's prompt; in non-interactive contexts returns *default*.
    """
    from rich.prompt import Confirm

    try:
        return Confirm.ask(f"[yellow]?[/yellow] {message}", default=default)
    except (EOFError, KeyboardInterrupt):
        return default
