from docker.client import DockerClient

from system.App import App

class Docker:
    # Try to import docker package
    try:
        import docker
    except:
        print('Install docker using pip')
        raise SystemExit

    # Create a docker API client
    try:
        _client: DockerClient = docker.from_env()
    except Exception as e:
        print('Docker not running...')
        raise SystemExit

    # Application Instance
    _app = App()


    



