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

    def exec(self, cmd: list[str] | str, *, workdir: str | None = None,
             tty: bool = True, stream: bool = True) -> int:
        """Exec *cmd* inside the project's primary container.

        Streams output to the terminal via the UI console and returns the
        command's exit code. Raises :class:`fincli.core.errors.NotFound` (with a
        friendly message) if the container is not running.
        """
        from fincli.ui.console import console, warning

        container = find_primary(self.project, self.service)
        if container.status != "running":
            warning(f"Container '{self.primary_name}' is not running. Run 'fin up' first.")
            return 1

        exec_kwargs: dict = {"tty": tty, "stream": stream, "demux": False}
        if workdir:
            exec_kwargs["workdir"] = workdir

        if stream:
            exit_code_holder = container.exec_run(cmd, **exec_kwargs)
            # docker-py returns (exit_code, output_generator) when stream=True
            code, output = exit_code_holder
            if output is not None:
                for chunk in output:
                    console.file.write(chunk.decode("utf-8", errors="replace"))
                    console.file.flush()
            # When streaming, exit code may be None until drained; re-inspect.
            if code is None:
                code = 0
            return int(code)
        result = container.exec_run(cmd, **exec_kwargs)
        if result.output:
            console.file.write(result.output.decode("utf-8", errors="replace"))
            console.file.flush()
        return int(result.exit_code or 0)
