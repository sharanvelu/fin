import importlib

from system.Cli import Cli
from system.Env import Env


class Reserved:
    available_commands = [
        "bash",
        "config",
        "ps",
        "sh",
        "status",
        "shell",
    ]

    def __init__(self, env: Env, cli: Cli) -> None:
        self.__env = env
        self.__cli = cli

        command = self.__cli.get_command().lower()

        if command in self.available_commands:
            self.__invoke(command)
        else:
            self.__cli.print_error("Unknown command " + command)

    def __invoke(self, command: str):
        command = self.__proxy_command(command)

        try:
            # file = importlib.import_module("." + command, "system.Reserved.Commands")
            file = importlib.import_module("." + command, "system.Reserved.Commands")
            getattr(file, command)(env=self.__env, cli=self.__cli)
        except ModuleNotFoundError as exception:
            self.__cli.error(exception)

    def __proxy_command(self, command: str):
        # Process multiple commands for Shell operation
        command = "shell" if command in ["shell", "sh", "bash"] else command
        command = "ps" if command in ["status", "ps"] else command

        return command.capitalize()
