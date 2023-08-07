import os

class Exec:
    def __init__(self) -> None:
        pass

    def run(self, containerName: str, command: str):
        return os.system('docker exec -it ' + containerName + ' ' + command)
