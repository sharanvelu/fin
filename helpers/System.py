import os
from time import sleep


class System:
    # Home
    home = os.getenv('SYSTEM_HOME')

    # Run a system command
    def run(self, command, onlyFirstLineOnly=False, outputAsArray = False):
        output = os.popen(command).readlines()

        if onlyFirstLineOnly:
            return output[0].replace('\n', '') if len(output) > 0 else None

        return output if outputAsArray else str(output)

    # Terminate execution
    def terminate(self):
        raise SystemExit

    # Slep or Wait fro specified time before executing the rest
    def wait(self, duration):
        sleep(duration)
