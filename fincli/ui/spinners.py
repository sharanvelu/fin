"""Spinner / progress helpers for long-running operations.

Usage::

    from fincli.ui.spinners import fin_spinner

    with fin_spinner("Pulling image..."):
        client.images.pull("traefik:v3.6")

The context manager wraps Rich's transient status so the spinner disappears
once the work completes, leaving the surrounding output clean.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Sequence

from fincli.ui.console import console


@contextmanager
def fin_spinner(message: str, *, spinner: str = "dots") -> Iterator[None]:
    """Show a spinner with *message* for the duration of the ``with`` block."""
    with console.status(f"[cyan]{message}[/cyan]", spinner=spinner):
        yield


@contextmanager
def live_panel(
    title: str, *, border_style: str = "cyan"
) -> Iterator[Callable[[str], None]]:
    """A live-updating boxed log — the panel twin of :func:`fin_spinner`.

    Yields an ``add(line)`` callable; each added line (Rich markup allowed)
    appears inside the panel immediately. Unlike the transient spinner, the
    finished panel stays in the terminal — including on error, so partial
    progress remains visible above the error panel that follows.
    """
    from rich.console import Group
    from rich.live import Live
    from rich.panel import Panel

    lines: list[str] = []

    def render() -> Panel:
        return Panel(
            Group(*lines),
            title=f"[bold {border_style}]{title}[/bold {border_style}]",
            border_style=border_style,
            expand=False,
        )

    with Live(render(), console=console, refresh_per_second=8) as live:

        def add(line: str) -> None:
            lines.append(line)
            live.update(render())

        yield add


@contextmanager
def live_checklist(
    title: str, items: Sequence[str], *, border_style: str = "cyan"
) -> Iterator[Callable[[str, str], None]]:
    """A live boxed list with one in-place-updating line per item.

    Every item starts as an animated spinner line (work in progress); call
    ``set_line(item, markup)`` to replace it with its result (e.g. a ✓/✗
    line). Unlike :func:`live_panel` the lines update in place rather than
    append, and like it, the finished panel stays in the terminal.
    """
    from rich.console import Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.spinner import Spinner

    states: dict[str, Any] = {
        item: Spinner("dots", text=f"[cyan]{item}[/cyan]", style="cyan")
        for item in items
    }

    def render() -> Panel:
        return Panel(
            Group(*states.values()),
            title=f"[bold {border_style}]{title}[/bold {border_style}]",
            border_style=border_style,
            expand=False,
        )

    with Live(render(), console=console, refresh_per_second=8) as live:

        def set_line(item: str, line: str) -> None:
            states[item] = line
            live.update(render())

        yield set_line
