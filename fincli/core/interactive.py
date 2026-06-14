"""Interactive exec sessions inside a container (bash, sh, tinker, …).

The high-level ``container.exec_run`` helper only *streams output* — it never
attaches the local stdin to the exec, so an interactive shell can never receive
keystrokes (typing ``exit`` does nothing; the process hangs until Ctrl+C).

This module uses the Docker SDK's **low-level API** to:

1. Create an exec with stdin + a TTY attached.
2. Obtain the raw bidirectional socket.
3. Put the local terminal into raw mode (so keys, including Ctrl-C/Ctrl-D, pass
   through to the container instead of being handled by fin).
4. Proxy bytes both ways with ``select`` until the remote side closes — which
   happens exactly when the in-container shell exits.
5. Restore the terminal and return the exec's real exit code.

This stays entirely within the Docker Python SDK — no ``docker exec`` shell-out.
On platforms without the Unix terminal modules (e.g. native Windows) it falls
back to a non-interactive streamed exec.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from fincli.core.docker_client import get_docker


def _raw_socket(sock: Any) -> Any:
    """Return the underlying OS socket from docker-py's exec_start result.

    docker-py wraps the connection; the real socket is usually at ``_sock``.
    """
    inner = getattr(sock, "_sock", None)
    return inner if inner is not None else sock


def _resize(api: Any, exec_id: str) -> None:
    """Match the container TTY size to the local terminal (best effort)."""
    try:
        cols, rows = os.get_terminal_size(sys.stdout.fileno())
        api.exec_resize(exec_id, height=rows, width=cols)
    except Exception:  # noqa: BLE001 - resize is non-essential
        pass


def interactive_exec(container: Any, cmd: list[str] | str, *, workdir: str | None = None) -> int:
    """Run *cmd* as a fully interactive session inside *container*.

    Returns the command's exit code. Falls back to a streamed (non-interactive)
    exec when a real terminal isn't available or the platform lacks the Unix
    terminal modules.
    """
    api = get_docker().client.api

    # Without a real local TTY there's nothing to make interactive — stream it.
    try:
        stdin_is_tty = sys.stdin.isatty()
        stdin_fd = sys.stdin.fileno()
    except (ValueError, OSError):
        stdin_is_tty = False
        stdin_fd = -1

    if not stdin_is_tty:
        return _streamed_exec(api, container, cmd, workdir=workdir)

    try:
        import select
        import termios
        import tty as tty_mod
    except ImportError:  # pragma: no cover - non-Unix fallback
        return _streamed_exec(api, container, cmd, workdir=workdir)

    create_kwargs: dict[str, Any] = {
        "stdin": True,
        "stdout": True,
        "stderr": True,
        "tty": True,
    }
    if workdir:
        create_kwargs["workdir"] = workdir
    exec_id = api.exec_create(container.id, cmd, **create_kwargs)["Id"]

    sock = api.exec_start(exec_id, tty=True, stream=True, socket=True, demux=False)
    raw = _raw_socket(sock)
    raw.setblocking(True)

    old_settings = termios.tcgetattr(stdin_fd)
    _resize(api, exec_id)

    # Resize the container TTY when the local window changes.
    try:
        import signal

        def _on_winch(_signum, _frame):
            _resize(api, exec_id)

        previous_winch = signal.signal(signal.SIGWINCH, _on_winch)
    except (ImportError, ValueError, AttributeError, OSError):
        previous_winch = None

    try:
        tty_mod.setraw(stdin_fd)
        stdout_fd = sys.stdout.fileno()

        while True:
            try:
                readable, _, _ = select.select([raw, stdin_fd], [], [])
            except (InterruptedError, OSError):
                continue

            # Container → local terminal.
            if raw in readable:
                try:
                    data = raw.recv(65536)
                except OSError:
                    break
                if not data:
                    break  # remote closed → the shell exited
                os.write(stdout_fd, data)

            # Local keystrokes → container.
            if stdin_fd in readable:
                try:
                    keys = os.read(stdin_fd, 65536)
                except OSError:
                    break
                if not keys:
                    # Local EOF; signal it once to the container and stop sending.
                    try:
                        raw.shutdown(1)  # SHUT_WR
                    except OSError:
                        pass
                else:
                    try:
                        raw.sendall(keys)
                    except OSError:
                        break
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
        if previous_winch is not None:
            try:
                import signal

                signal.signal(signal.SIGWINCH, previous_winch)
            except (ValueError, OSError):
                pass
        try:
            raw.close()
        except OSError:
            pass

    try:
        return int(api.exec_inspect(exec_id).get("ExitCode") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _streamed_exec(api: Any, container: Any, cmd: list[str] | str, *, workdir: str | None) -> int:
    """Non-interactive fallback: run the exec and stream its output."""
    from fincli.ui.console import console

    create_kwargs: dict[str, Any] = {"stdout": True, "stderr": True, "tty": False}
    if workdir:
        create_kwargs["workdir"] = workdir
    exec_id = api.exec_create(container.id, cmd, **create_kwargs)["Id"]
    stream = api.exec_start(exec_id, stream=True, demux=False)
    for chunk in stream:
        if chunk:
            console.file.write(chunk.decode("utf-8", errors="replace"))
            console.file.flush()
    try:
        return int(api.exec_inspect(exec_id).get("ExitCode") or 0)
    except Exception:  # noqa: BLE001
        return 0
