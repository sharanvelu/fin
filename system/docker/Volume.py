from system.docker.Docker import Docker
from system.Cli import Cli

class Volume(Docker):
    cli = Cli()

    def getVolumeName(self, name):
        return name if name.startswith(self._app.name_key + '_') else (self._app.name_key + '_' + name)

    def get(self, name: str):
        volumes = self._client.volumes.list(filters = {'name' : self.getVolumeName(name)})
        return volumes[0] if len(volumes) > 0 else None
    
    def create(self, name: str):
        name = self.getVolumeName(name)
        if self.get(name) is None:
            self._client.volumes.create(name = name)
