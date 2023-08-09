from system.Cli import Cli

from system.docker.Docker import Docker


class Network(Docker):
    __cli = Cli()

    def get(self):
        networks = self._client.networks.list(names=[self._app.network])
        return networks[0] if len(networks) > 0 else None

    def create(self):
        if self.get() is None:
            self.__cli.process("Creating network for " + self._app.name)
            self._client.networks.create(self._app.network)
            self.__cli.print_ln(self._app.name + " Network created.")
            self.__cli.print_empty_ln()
