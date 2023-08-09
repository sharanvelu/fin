from system.docker.Docker import Docker
from system.Cli import Cli


class Volume(Docker):
    cli = Cli()

    def get_volume_name(self, name):
        if name.startswith(self._app.name_key + "_"):
            return name

        return self._app.name_key + "_" + name

    def get(self, name: str):
        volumes = self._client.volumes.list(
            filters={"name": self.get_volume_name(name)}
        )

        return volumes[0] if len(volumes) > 0 else None

    def create(self, name: str):
        name = self.get_volume_name(name)

        if self.get(name) is None:
            self._client.volumes.create(name=name)
