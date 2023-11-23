from datetime import datetime

from system.Env import Env
from system.Cli import Cli
from system.Table import Table

from system.docker.Container import Container


class Ps:
    def __init__(self, env: Env, cli: Cli):
        self.__env = env
        self.__cli = cli

        self.__container = Container()

        self.__table_headers = ["Container ID", "Container Name", "Service", "Site", "Status", "Time"]

        self.__print_table_content()

    def __print_table_content(self):
        self.__cli.print_ln("--------- Asset Containers ---------", self.__cli.color.cyan)
        self.__build_asset_containers_list()
        self.__cli.print_empty_ln()
        self.__cli.print_ln("------ Application Containers ------", self.__cli.color.cyan)
        self.__build_application_containers_list()

    def __build_asset_containers_list(self):
        table = Table(self.__table_headers)
        table.build(self.__get_containers_data_from_container_type("asset"))

    def __build_application_containers_list(self):
        table = Table(self.__table_headers)
        table.build(self.__get_containers_data_from_container_type("application"))

    def __get_containers_data_from_container_type(self, container_type: str) -> list:
        labels = ["com.example.vendor=" + self.__env.app.name, "com.example.type=" + container_type]

        list_of_containers = self.__container.list(all=True, filters={"label": labels})

        container_data = []
        for container in list_of_containers:
            container_data.append(self.__process_container_data_for_table(container))

        return container_data

    def __process_container_data_for_table(self, container):
        return [
            container.attrs["Config"]["Hostname"],
            container.attrs["Name"].strip("/"),
            container.attrs["Config"]["Labels"]["com.example.service"],
            "https://" + container.attrs["Config"]["Labels"]["com.example.host"],
            container.attrs["State"]["Status"].capitalize(),
            datetime.fromisoformat(container.attrs["State"]["StartedAt"]).ctime(),
        ]
