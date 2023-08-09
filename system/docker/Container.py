from system.Cli import Cli
from system.Env import Env

from system.docker.Docker import Docker


class Container(Docker):
    __cli = Cli()

    STATUS_RUNNING = 'running'
    STATUS_EXITED = 'exited'

    # Constructor
    def __init__(self) -> None:
        pass

    # Run Docker Container
    def run(self, image: str, name: str, labels: dict = {}, volumes: list = [], command: (str or list) = None, ports: dict = {}, environment: dict = {}, platform: str = None) -> None:
        try:
            if self.__can_start_container_with_name(name):
                self.__cli.process('Starting container for ' + self.__cli.color.cyan + name)

                self._client.containers.run(
                    image=image,
                    name=name,
                    labels=labels,
                    volumes=volumes,
                    ports=ports,
                    command=command,
                    environment=environment,
                    detach=True,
                    network=self._app.network,
                    platform=platform,
                )
        except RuntimeError as error:
            print(error.args)
        except Exception as exception:
            print(exception)
            raise SystemExit

    # Get list of all Containers
    def list(self, all: bool = True, filters: dict = None, limit: int = None):
        return self._client.containers.list(all=all, filters=filters, limit=limit)

    # Get details of a Containers
    def get(self, container: str):
        return self._client.containers.get(container)

    # Check for existence of a container with Same Name
    def __can_start_container_with_name(self, name: str) -> bool:
        existing_container = self.list(all=True, filters={'name': name}, limit=1)
        if len(existing_container) == 0:
            return True

        if existing_container[0].status != self.STATUS_RUNNING:
            existing_container[0].start()

        return False

    def exec(self, command: str = None) -> None:
        if command is not None:
            container_name = self._app.get_container_name(Env().get("HOST"))
            container = self.list(all=True, filters={"name": container_name})[0]

            print(container.exec_run(cmd=command, tty=True, stdin=True))
