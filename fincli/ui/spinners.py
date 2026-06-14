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
from typing import Iterator

from fincli.ui.console import console


@contextmanager
def fin_spinner(message: str, *, spinner: str = "dots") -> Iterator[None]:
    """Show a spinner with *message* for the duration of the ``with`` block."""
    with console.status(f"[cyan]{message}[/cyan]", spinner=spinner):
        yield
