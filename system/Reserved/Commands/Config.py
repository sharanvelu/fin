from exceptions.ActionLengthMismatchException import ActionLengthMismatchException

from system.Cli import Cli
from system.Env import Env
from system.Table import Table

from system.Config import Config as ConfigParser


class Config:
    def __init__(self, env: Env, cli: Cli):
        self.__env = env
        self.__cli = cli
        self.__config = ConfigParser("assets")

        actions = cli.get_actions()
        if len(actions) < 1:
            # TODO : Need to improve the exception classes
            self.__cli.print_error("Minimum 1 argument expected. But None given.")
            raise SystemExit

        if hasattr(self, actions[0]):
            method = getattr(self, actions[0])
            method()
        else:
            self.__cli.print_error("Unknown action provided")

    def __check_asset(self, asset):
        if asset not in ["mysql", "postgres", "redis"]:
            # TODO : Need to improve the exception classes
            self.__cli.print_error("Unknown asset provided")
            raise SystemExit

    def enable(self):
        actions = self.__cli.get_actions()
        if len(actions) != 2:
            # TODO : Need to improve the exception classes
            raise ActionLengthMismatchException(2)

        self.__check_asset(actions[1])

        self.__config.set(actions[1], {"start": True})

        self.__cli.print_ln(
            f"Configuration for '{self.__cli.color.cyan}{actions[1]}{self.__cli.color.clear}' is now '{self.__cli.color.green}enabled{self.__cli.color.clear}'."
        )

    def disable(self):
        actions = self.__cli.get_actions()
        if len(actions) != 2:
            # TODO : Need to improve the exception classes
            raise ActionLengthMismatchException(2)

        self.__check_asset(actions[1])

        self.__config.set(actions[1], {"start": False})

        self.__cli.print_ln(
            f"Configuration for '{self.__cli.color.cyan}{actions[1]}{self.__cli.color.clear}' is now '{self.__cli.color.red}disabled{self.__cli.color.clear}'."
        )

    def list(self):
        if len(self.__cli.get_actions()) != 1:
            # TODO : Need to improve the exception classes
            raise ActionLengthMismatchException(1)

        asset_config_data = self.__config.get_all()

        table = Table()
        for i in asset_config_data:
            status = "Enabled" if asset_config_data.get(i).get("start") == "True" else "Disabled"
            color = self.__cli.color.green if status == 'Enabled' else self.__cli.color.red
            table.add_row([i, "=>", color + status + self.__cli.color.clear])

        self.__cli.print_empty_ln()
        self.__cli.print_ln("Asset Configurations")
        self.__cli.print_empty_ln()
        table.build(table_format='plain')
