"""Execution context handed to plug command handlers.

A plug command must not reach into globals; everything it needs to act on the
user's behalf is provided here: the parsed project env, the resolved primary
container name, and small helpers to exec inside the primary container.

Plugs *describe* and *delegate* — the actual Docker exec is performed by these
helpers (which live in Fin core), preserving the single audited Docker path.
"""

from __future__ import annotations

from dataclasses import dataclass

from fincli.core.containers import find_primary, primary_container_name
from fincli.core.env import ProjectEnv


@dataclass
class PlugContext:
    """Everything a plug command handler needs to do its job.

    Attributes:
        env: The loaded project environment.
        project: The resolved project name (cwd basename / FIN_CONTAINER_NAME).
        service: The primary service name (usually ``web``).
    """

    env: ProjectEnv
    project: str
    service: str = "web"

    @property
    def primary_name(self) -> str:
        """Name of the project's primary container."""
        return primary_container_name(self.project, self.service)

    def exec(
        self,
        cmd: list[str] | str,
        *,
        workdir: str | None = None,
        interactive: bool = False,
    ) -> int:
        """Exec *cmd* inside the project's primary container.

        Returns the command's exit code. Warns and returns 1 if the container
        is not running.

        Set ``interactive=True`` for commands that open a session the user
        types into (``bash``, ``sh``, ``tinker``, REPLs). That attaches the
        local stdin to a container TTY and proxies both directions, so typing
        ``exit`` (or Ctrl-D) ends the session and returns control to the shell.
        Without it, an interactive program would hang waiting for input it can
        never receive.

        For one-shot commands (``artisan migrate``, ``composer install``) leave
        ``interactive=False`` — output is streamed to the terminal.
        """
        from fincli.ui.console import warning

        container = find_primary(self.project, self.service)
        if container.status != "running":
            warning(
                f"Container '{self.primary_name}' is not running. Run 'fin up' first."
            )
            return 1

        if interactive:
            from fincli.core.interactive import interactive_exec

            return interactive_exec(container, cmd, workdir=workdir)

        # One-shot: stream output (no stdin attached). A pseudo-TTY is allocated
        # when Fin's stdout is a terminal so the in-container program keeps its
        # ANSI colours; piped output stays clean. Real exit code is returned.
        from fincli.core.interactive import streamed_exec

        return streamed_exec(container, cmd, workdir=workdir)
