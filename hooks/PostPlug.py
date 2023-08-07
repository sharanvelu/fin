from system.App import App
from system.Env import Env
from system.Cli import Cli

from system.docker.Asset import Asset

class PostPlug:
    __availableCommands = [
        'up'
    ]

    def __init__(self, app: App, env: Env, cli: Cli) -> None:
        self.__app = app
        self.__env = env
        self.__cli = cli

        # Check if the command is available
        if cli.getCommand() in self.__availableCommands:
            getattr(self, cli.getCommand())()

    def up(self):
        # Create Database for Projects
        #

        self.__cli.printLn('Your Application should be running at ' + self.__cli.color.green + self.__env.get('HOST'))
