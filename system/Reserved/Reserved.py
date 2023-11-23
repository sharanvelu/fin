import importlib

from system.Cli import Cli
from system.Env import Env


class Reserved:
    __available_commands = [
        "config",
        "ps",
    ]

    def __init__(self, env: Env, cli: Cli) -> None:
        self.__env = env
        self.__cli = cli

        self.__invoke_command()

    def __invoke_command(self):
        command = self.__cli.get_command().lower().capitalize()

        if command.lower() in self.__available_commands:
            try:
                # file = importlib.import_module("." + command, "system.Reserved.Commands")
                file = importlib.import_module("." + command, "system.Reserved.Commands")
                getattr(file, command)(env=self.__env, cli=self.__cli)
            except ModuleNotFoundError as exception:
                self.__cli.error(exception)

        else:
            self.__cli.print_error("Unknown command " + command)
