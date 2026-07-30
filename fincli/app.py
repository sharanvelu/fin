"""Tool-level metadata and lifecycle helpers for Fin.

``App`` is the place for "who am I" details (display name, version, release
date, the default network) plus small helpers used across the codebase such as
``terminate()`` to exit the whole script cleanly with the right exit code.
"""

from __future__ import annotations

from typing import NoReturn

from fincli import __version__
from fincli.config import Config


# Exit codes (documented contract — see README "Troubleshooting" and DESIGN.md §8).
EXIT_OK = 0  # success
EXIT_USER = 1  # user error (bad input, missing env, not found by user fault)
EXIT_SYSTEM = 2  # system/docker error (daemon down, API failure)


class App:
    """Tool-wide identity and lifecycle helpers.

    Implemented as a lightweight singleton: every instantiation returns the
    same object, so ``App().terminate()`` reads naturally anywhere.
    """

    _instance: "App | None" = None

    #: Display name used in all user-facing output.
    name: str = "Fin"
    #: Semantic version, sourced from the package.
    version: str = __version__
    #: Human-readable release date.
    release_date: str = "2026-07-30"
    #: Default Docker network for all containers.
    network: str = Config.NETWORK
    #: One-line tagline.
    tagline: str = "Run local dev containers, infinitely extensible via plugs."

    def __new__(cls) -> "App":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # --- lifecycle ----------------------------------------------------------
    def terminate(self, message: str | None = None, code: int = EXIT_USER) -> NoReturn:
        """Terminate the entire Fin process.

        Prints *message* as an error panel (when given) via the UI layer, then
        exits with *code*. Importing the console lazily avoids a hard import
        cycle and keeps ``App`` usable in minimal contexts.
        """
        if message:
            # Local import to avoid a circular dependency at module load time.
            from fincli.ui.console import error

            error(message)
        raise SystemExit(code)

    def banner(self) -> str:
        """Return a short identity string, e.g. ``Fin v0.1.0``."""
        return f"{self.name} v{self.version}"
