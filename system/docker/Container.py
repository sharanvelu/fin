from system.Cli import Cli
from system.Env import Env

from .Docker import Docker

class Container(Docker):
    __cli = Cli()

    STATUS_RUNNING='running'
    STATUS_EXITED='exited'

    # Contructor
    def __init__(self) -> None:
        pass

    # Run Docker Container
    def run(self, image: str, name: str, labels: dict = {}, volumes: dict = {}, command = None, ports: dict = {}, environment: dict = {}, platform: str = None) -> None:
        try:
            if self.__canStartContainerWithName(name):
                self.__cli.process('Starting container for ' + self.__cli.color.cyan + name)

                self._client.containers.run(
                    image = image,
                    name = name,
                    labels = labels,
                    volumes = volumes,
                    ports = ports,
                    command = command,
                    environment = environment,
                    detach=True,
                    network=self._app.network,
                    platform=platform
                )
        except RuntimeError as error:
            print(error.args)
        except Exception as exception:
            print(exception)
            raise SystemExit

    # Get list of all Containers
    def list(self, all: bool = True, filters: dict = None, limit: int = None):
        return self._client.containers.list(all=all, filters=filters, limit=limit)

    # Check for existence of a container with Same Name
    def __canStartContainerWithName(self, name: str):
        existingcontainer = self.list(all=True, filters={'name': name}, limit=1)
        if len(existingcontainer) == 0:
            return True

        if existingcontainer[0].status != self.STATUS_RUNNING:
            existingcontainer[0].start()

        return False

    def exec(self, command = None):
        if command is not None:
            containerName = self._app.getContainerName(Env().get('HOST'))
            container = self.list(all = True, filters = {'name' : containerName})[0]

            print(container.exec_run(cmd = command, tty = True, stdin = True, stream = True, socket = True))
