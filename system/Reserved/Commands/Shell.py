from system.App import App
from system.Env import Env
from system.Cli import Cli

from system.docker.Exec import Exec as DockerExec


class Shell:
    def __init__(self, env: Env, cli: Cli):
        self.__env = env
        self.__cli = cli

        self.__run_command()

    def __get_container_name(self):
        return App().get_container_name(self.__env.get("HOST"))

    def __run_command(self):
        command = self.__cli.get_command()
        shell = command if command in ['bash', 'sh'] else 'sh'

        DockerExec().run(self.__get_container_name(), shell, False)
