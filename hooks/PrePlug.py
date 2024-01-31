from system.App import App
from system.Env import Env
from system.Cli import Cli

from system.docker.Asset import Asset
from system.docker.Network import Network


class PrePlug:
    __available_commands = [
        "up",
    ]

    __info_check_commands = [
        "up",
    ]

    def __init__(self, app: App, env: Env, cli: Cli) -> None:
        self.__app = app
        self.__env = env
        self.__cli = cli

        # TODO : Uncomment the following lines when done with working on the info response server.
        # if cli.get_command() in self.__info_check_commands:
        #     self.__check_info_from_server()

        # Check if the command is available
        if cli.get_command() in self.__available_commands:
            getattr(self, cli.get_command())()

    def up(self):
        # Create Application Network
        Network().create()

        # Start the Asset Containers based on config and Overrides
        Asset().start()

    def __check_info_from_server(self):
        try:
            import requests

            response_from_server = requests.get(self.__app.info_url)

            if response_from_server.status_code == 200:
                self.__cli.print_ln("================================")
                self.__cli.print_ln("Info From " + self.__app.name, self.__cli.color.cyan)
                self.__cli.print_ln("++++++++++++++++++++++++++++++++")
                self.__cli.print_ln(response_from_server.text)
                self.__cli.print_ln("================================")
                self.__cli.print_empty_ln()

        except Exception as exception:
            self.__cli.error(exception)
            pass
