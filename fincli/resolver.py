"""Command resolution: reserved → FIN_APP → FIN_PLUGS → GLOBAL.

When a sub-command is run, Fin searches in this order:

1. Reserved (system) commands — owned by Fin, never delegated.
2. The primary app plug named by ``FIN_APP`` (a.k.a. ``FIN_PLUG``).
3. The auxiliary plugs listed in ``FIN_PLUGS`` (comma-separated).
4. Installed ``GLOBAL`` plugs.

The first match wins. Reserved commands are handled directly by Fin; plug
commands are dispatched to the plug's handler with a :class:`PlugContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fincli.commands import RESERVED_COMMANDS, load_reserved
from fincli.core.env import ProjectEnv
from fincli.plugs.base import FinPlug, PlugCommand, PlugType
from fincli.plugs.context import PlugContext
from fincli.plugs.loader import LoadedPlug, load_all, load_by_name


@dataclass
class Resolution:
    """The outcome of resolving a command name to something runnable."""

    kind: str  # "reserved" | "plug"
    run: Callable[[], int]
    source: str  # "system" or the plug name


def _plug_lookup_order(env: ProjectEnv) -> list[LoadedPlug]:
    """Return plugs in resolution order: FIN_APP, then FIN_PLUGS, then GLOBAL.

    Loading is lazy and de-duplicated by plug name.
    """
    ordered: list[LoadedPlug] = []
    seen: set[str] = set()

    def add(lp: LoadedPlug | None) -> None:
        if lp and lp.instance.name not in seen:
            seen.add(lp.instance.name)
            ordered.append(lp)

    # 1) FIN_APP (the primary application plug)
    if env.app_plug:
        add(load_by_name(env.app_plug))

    # 2) FIN_PLUGS (auxiliary plugs, in declared order)
    for plug_name in env.plugs:
        add(load_by_name(plug_name))

    # 3) GLOBAL plugs (everything installed under Global/)
    for lp in load_all():
        if lp.plug_type == PlugType.GLOBAL:
            add(lp)

    return ordered


def _find_plug_command(
    plug: FinPlug, name: str
) -> PlugCommand | None:
    """Find a command (by name or alias) within a plug."""
    commands = plug.commands()
    if name in commands:
        return commands[name]
    for cmd in commands.values():
        if name in cmd.aliases:
            return cmd
    return None


def resolve(name: str, args: list[str], env: ProjectEnv) -> Resolution | None:
    """Resolve a command *name* to a runnable, or return None if unknown."""
    load_reserved()

    # 1) Reserved system commands — highest priority, never delegated.
    if name in RESERVED_COMMANDS:
        cmd = RESERVED_COMMANDS[name]
        return Resolution(
            kind="reserved",
            run=lambda: cmd.handler(args),
            source="system",
        )

    # 2-4) Plug commands, in resolution order.
    for lp in _plug_lookup_order(env):
        plug_cmd = _find_plug_command(lp.instance, name)
        if plug_cmd is not None:
            project = env.project_name
            ctx = PlugContext(env=env, project=project)
            return Resolution(
                kind="plug",
                run=lambda pc=plug_cmd, c=ctx: pc.handler(c, args),
                source=lp.instance.name,
            )

    return None
