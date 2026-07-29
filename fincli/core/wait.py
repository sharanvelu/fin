"""Readiness waiting for freshly-started asset containers.

A just-started database engine accepts the container as *running* well before
it can accept client connections. Doing DB presence/creation work in that gap
fails or warns spuriously. This module polls a cheap in-container readiness
probe until the engine answers, so the DB step in :mod:`fincli.core.database`
only proceeds once the asset is actually reachable.

Design notes:

* :func:`wait_for_ready` is the generic poll loop. The ``check`` callable, the
  ``sleep`` function, and the ``timeout`` / ``interval`` are all injectable so
  the suite drives it deterministically (a call-counter check + a no-op sleep)
  and never sleeps for real.
* Timing uses :func:`time.monotonic` (no wall-clock / randomness), and nothing
  sleeps at import time.
* On timeout we *warn and return False* — readiness is best-effort and must
  never crash ``fin up``.
* Engine probes (:func:`mysql_ready`, :func:`postgres_ready`) run inside the
  container via ``exec_run`` so no host DB client is needed.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from fincli.config import Config
from fincli.ui.console import warning
from fincli.ui.spinners import fin_spinner

#: Default poll budget and cadence (seconds).
DEFAULT_TIMEOUT = 30.0
DEFAULT_INTERVAL = 0.5


def wait_for_ready(
    container: Any,
    *,
    check: Callable[[Any], bool],
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
    description: str = "service",
) -> bool:
    """Poll ``check(container)`` until it returns True or *timeout* elapses.

    Shows a :func:`fin_spinner` for the duration. Returns ``True`` as soon as
    the check passes, ``False`` on timeout (after warning). Never raises for an
    ordinary not-ready/timeout condition — readiness is best-effort.

    Args:
        container: The container object passed straight through to *check*.
        check: Predicate that returns True once the service is reachable.
        timeout: Maximum seconds to wait before giving up.
        interval: Seconds to sleep between polls (via the injected *sleep*).
        sleep: Sleep function; injectable so tests pass a no-op.
        description: Human label used in the spinner / warning text.
    """
    start = time.monotonic()
    with fin_spinner(f"Waiting for {description} to be ready…"):
        while True:
            try:
                if check(container):
                    return True
            except Exception:  # noqa: BLE001 - a flaky probe just means "not yet"
                pass
            if time.monotonic() - start >= timeout:
                break
            sleep(interval)
    warning(
        f"{description} did not become ready within {timeout:g}s; continuing anyway."
    )
    return False


def _exec(container: Any, argv: list[str], **kwargs: Any) -> tuple[int | None, bytes]:
    """Run *argv* in *container* and normalise the result to (exit_code, output).

    docker-py's ``exec_run`` returns either an ``(exit_code, output)`` tuple or
    an object exposing ``.exit_code`` / ``.output`` depending on call style;
    handle both so the probes are robust to either.
    """
    result = container.exec_run(argv, **kwargs)
    if isinstance(result, tuple):
        exit_code, output = result
    else:
        exit_code = getattr(result, "exit_code", None)
        output = getattr(result, "output", b"")
    if output is None:
        output = b""
    if isinstance(output, str):
        output = output.encode("utf-8", "replace")
    return exit_code, output


def mysql_ready(container: Any) -> bool:
    """True when the MySQL engine inside *container* answers a ping.

    Runs ``mysqladmin ping`` as root with the password supplied via the exec
    environment (``MYSQL_PWD``) so no credential is interpolated into argv.
    Ready when the command exits 0 and reports the server is alive.
    """
    exit_code, output = _exec(
        container,
        ["mysqladmin", "ping", "-u", "root"],
        environment={"MYSQL_PWD": Config.ASSET_PASSWORD},
    )
    if exit_code != 0:
        return False
    return b"alive" in output.lower()


def postgres_ready(container: Any) -> bool:
    """True when Postgres inside *container* accepts connections.

    Uses ``pg_isready -U <ASSET_USERNAME>``; ready when it exits 0.
    """
    exit_code, _ = _exec(
        container,
        ["pg_isready", "-U", Config.ASSET_USERNAME],
    )
    return exit_code == 0
