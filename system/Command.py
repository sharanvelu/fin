import importlib

from system.Cli import Cli
from system.Env import Env
from system.Reserved.Reserved import Reserved


class Command:
    def __init__(self, env: Env, cli: Cli):
        self.__cli = cli
        self.__env = env

    @property
    def reserved_commands(self):
        return [
            "bash",
            "config",
            "ps",
            "sh",
            "status",
            "shell",
        ]

    @property
    def global_commands(self):
        return [
            "config",
            "ps",
        ]

    @property
    def is_reserved(self):
        return self.__cli.get_command() in self.reserved_commands

    @property
    def is_global(self):
        return self.__cli.get_command() in self.reserved_commands

    def trigger_plug(self):
        # If the initiated Command is not a reserved Command,
        # Invoke the Plug to proceed further
        if not self.is_reserved:
            # Get the module and invoke the Plugin
            self.__invoke_plugin()

        # If the command provided is a reserved Command
        if self.is_reserved:
            Reserved(env=self.__env, cli=self.__cli)

    def __invoke_plugin(self):
        plug = self.__env.get("PLUG").lower().capitalize()

        # # # Import dynamic Classes
        try:
            file = importlib.import_module(f".{plug}", f"plugins.{plug}")
        except Exception as error:
            self.__cli.error(error, "Plug {}{}{} Not Found.".format(self.__cli.color.cyan, plug, self.__cli.color.clear))

        try:
            plugClass = getattr(file, plug)
            plugClass(env=self.__env, cli=self.__cli)
        except Exception as error:
            self.__cli.error(error, "Error in {}{}{} Plug. Please contact Plug provider.".format(self.__cli.color.cyan, plug, self.__cli.color.clear))
