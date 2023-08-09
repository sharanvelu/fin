import os

from system.docker.Docker import Docker
from system.docker.Container import Container as DockerContainer


class Exec:
    def __init__(self) -> None:
        pass

    def run(self, container_name: str, command: str, use_api: bool = False):
        try:
            if DockerContainer().get(container=container_name):
                if use_api:
                    docker = Docker()

                    exec_data = docker.client.api.exec_create(
                        container=container_name, cmd=command, stdin=True, tty=True
                    )

                    output_bytes = docker.client.api.exec_start(
                        exec_id=exec_data.get("Id"), tty=True
                    )

                    print(output_bytes.decode())

                else:
                    os.system("docker exec -it " + container_name + " " + command)

        except Exception as e:
            raise SystemExit
