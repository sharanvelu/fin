from system.App import App
from system.Env import Env
from system.Cli import Cli


class PostPlug:
    __available_commands = [
        "up",
    ]

    def __init__(self, app: App, env: Env, cli: Cli) -> None:
        self.__app = app
        self.__env = env
        self.__cli = cli

        # Check if the command is available
        if cli.get_command() in self.__available_commands:
            getattr(self, cli.get_command())()

    def up(self):
        # Create Database for Projects
        #

        self.__cli.print_ln("Your Application should be running at " + self.__cli.color.green + self.__env.get("HOST"))
