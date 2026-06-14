"""Tests for fincli.commands.__init__ — reserved decorator and registry."""

from __future__ import annotations

from fincli.commands import (
    RESERVED_CANONICAL,
    RESERVED_COMMANDS,
    ReservedCommand,
    load_reserved,
    reserved,
)


def test_reserved_decorator_registers():
    @reserved("mytest_cmd", help="h", aliases=("mt",), group="Testing")
    def handler(args):
        return 0

    assert "mytest_cmd" in RESERVED_COMMANDS
    cmd = RESERVED_COMMANDS["mytest_cmd"]
    assert isinstance(cmd, ReservedCommand)
    assert cmd.help == "h"
    assert cmd.group == "Testing"
    # alias points to the same command
    assert RESERVED_COMMANDS["mt"] is cmd
    # canonical map excludes alias keys
    assert "mytest_cmd" in RESERVED_CANONICAL
    assert "mt" not in RESERVED_CANONICAL
    # decorator returns the original function
    assert handler(["x"]) == 0


def test_load_reserved_registers_all_system_commands():
    load_reserved()
    for name in ("up", "down", "stop", "ps", "exec", "inspect", "logs",
                 "images", "config", "asset", "plugs"):
        assert name in RESERVED_COMMANDS, f"missing reserved command: {name}"


def test_load_reserved_aliases():
    load_reserved()
    # ps has aliases status/containers; images has alias img.
    assert RESERVED_COMMANDS["status"] is RESERVED_COMMANDS["ps"]
    assert RESERVED_COMMANDS["containers"] is RESERVED_COMMANDS["ps"]
    assert RESERVED_COMMANDS["img"] is RESERVED_COMMANDS["images"]


def test_reserved_command_handler_signature():
    load_reserved()
    cmd = RESERVED_COMMANDS["up"]
    # handler accepts a list[str] argument
    assert callable(cmd.handler)
