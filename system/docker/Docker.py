from docker.client import DockerClient

from system.App import App


class Docker:
    # Application Instance
    _app = App()

    # Try to import docker package
    try:
        import docker
    except Exception as e:
        print("Install docker using pip")
        raise SystemExit

    # Create a docker API client
    try:
        _client: DockerClient = docker.from_env()
    except Exception as e:
        print("Docker not running...")
        raise SystemExit

    @property
    def client(self):
        return self._client
