"""Fin-specific exceptions and a decorator that renders them cleanly.

End users must never see a raw Python traceback. Command functions raise
:class:`FinError` (or its subclasses) for expected failures; the
:func:`handle_errors` decorator catches those plus the common Docker SDK
exceptions and renders a friendly Rich panel, then exits with the right code.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from fincli.app import EXIT_SYSTEM, EXIT_USER


class FinError(Exception):
    """A user-facing error. *exit_code* defaults to user-error (1)."""

    def __init__(self, message: str, *, exit_code: int = EXIT_USER, title: str = "Error"):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.title = title


class DockerUnavailable(FinError):
    """Raised when the Docker daemon cannot be reached."""

    def __init__(self, message: str = "Could not connect to Docker. Is Docker running?"):
        super().__init__(message, exit_code=EXIT_SYSTEM, title="Docker Unavailable")


class NotFound(FinError):
    """Raised when a container, image, or plug cannot be found."""

    def __init__(self, message: str):
        super().__init__(message, exit_code=EXIT_USER, title="Not Found")


def handle_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a command callable so all known errors render as Rich panels.

    Catches, in order: :class:`FinError`, Docker SDK ``NotFound`` /
    ``APIError`` / ``DockerException``, and finally any unexpected exception
    (shown as a generic system error, never a traceback).
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Imported here so this module has no hard dependency on the docker SDK
        # at import time (keeps unit tests light).
        from docker import errors as derr  # type: ignore

        from fincli.ui.console import error

        try:
            return func(*args, **kwargs)
        except FinError as exc:
            error(exc.message, title=exc.title)
            raise SystemExit(exc.exit_code)
        except derr.NotFound as exc:
            error(_clean_docker_message(exc), title="Not Found")
            raise SystemExit(EXIT_USER)
        except derr.APIError as exc:
            error(_clean_docker_message(exc), title="Docker API Error")
            raise SystemExit(EXIT_SYSTEM)
        except derr.DockerException:
            error(
                "Could not connect to Docker. Is Docker running?",
                title="Docker Unavailable",
            )
            raise SystemExit(EXIT_SYSTEM)
        except KeyboardInterrupt:
            error("Interrupted.", title="Cancelled")
            raise SystemExit(EXIT_USER)

    return wrapper


def _clean_docker_message(exc: Exception) -> str:
    """Extract a human-readable message from a Docker SDK exception."""
    explanation = getattr(exc, "explanation", None)
    if explanation:
        return str(explanation)
    return str(exc)
