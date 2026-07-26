"""Reserved (system) commands.

These are owned by Fin and never delegated to plugs. The `up` command in
particular only *reads information* from plugs — it never lets a plug execute
container actions. Each reserved command is registered in
:data:`RESERVED_COMMANDS` via the :func:`reserved` decorator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ReservedCommand:
    """A reserved command handler.

    The handler receives the remaining argv (after the command name) and
    returns an exit code.

    Optional help metadata (used by ``fin <command> --help``):
        usage:       a one-line usage string (e.g. ``fin down [asset|all] [-f]``).
        subcommands: a list of ``(name, description)`` pairs for commands that
                     dispatch on a first positional argument (config, asset, …).
        options:     a list of ``(flag, description)`` pairs for notable flags.
        examples:    example invocations shown verbatim.
    """

    name: str
    handler: Callable[[list[str]], int]
    help: str = ""
    aliases: tuple[str, ...] = ()
    group: str = "System"
    usage: str = ""
    subcommands: tuple[tuple[str, str], ...] = ()
    options: tuple[tuple[str, str], ...] = ()
    examples: tuple[str, ...] = ()


#: Global registry of reserved commands, keyed by name and alias.
RESERVED_COMMANDS: dict[str, ReservedCommand] = {}
#: Canonical-name → command (no alias duplicates), for help listing.
RESERVED_CANONICAL: dict[str, ReservedCommand] = {}


def reserved(
    name: str,
    *,
    help: str = "",
    aliases: tuple[str, ...] = (),
    group: str = "System",
    usage: str = "",
    subcommands: tuple[tuple[str, str], ...] = (),
    options: tuple[tuple[str, str], ...] = (),
    examples: tuple[str, ...] = (),
) -> Callable[[Callable[[list[str]], int]], Callable[[list[str]], int]]:
    """Decorator registering a function as a reserved command."""

    def decorator(func: Callable[[list[str]], int]) -> Callable[[list[str]], int]:
        cmd = ReservedCommand(
            name=name,
            handler=func,
            help=help,
            aliases=aliases,
            group=group,
            usage=usage,
            subcommands=subcommands,
            options=options,
            examples=examples,
        )
        RESERVED_COMMANDS[name] = cmd
        RESERVED_CANONICAL[name] = cmd
        for alias in aliases:
            RESERVED_COMMANDS[alias] = cmd
        return func

    return decorator


def load_reserved() -> None:
    """Import all reserved-command modules so they register themselves."""
    # Imported for side effects (registration via @reserved).
    from fincli.commands import (  # noqa: F401
        agents_cmd,
        asset,
        config_cmd,
        containers,
        images,
        plugs_cmd,
        system,
    )
