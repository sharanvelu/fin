import os

class Exec:
    def __init__(self) -> None:
        pass

    def run(self, container: str, command: str):
        return os.system('docker exec -it ' + container + ' ' + command)
