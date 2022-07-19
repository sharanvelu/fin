import os
from time import sleep

# Custom Import
from helpers.Colors import Color


class System:
    # Get .env Variables from Bash Scripts
    # Project ENV's are loaded within the Bash script and loaded here.
    def env(self, key, default=None):
        return os.getenv(key, default)

    # SetEnv for docker compose files.
    # Equivalent to 'export' in 'bash'
    def setEnv(self, key, value):
        os.environ[key] = str(value)

    # Print Output in the terminal
    # Customize color and style of
    def printOutput(self, text, color, newLine=False, style=''):
        if text:
            if newLine:
                print(color + style + text + Color.clear)
            else:
                print(color + style + text + Color.clear, end='')
        else:
            print('-')

    # Print a statement
    def print(self, text, color='', style=''):
        self.printOutput(text, color, False, style)

    # Print a statement and add a new Line
    def printLn(self, text, color='', style=''):
        self.printOutput(text, color, True, style)

    # Print an Empty Line
    def printEmptyLn(self):
        print(" ")

    # Print a statement with a Process indicator
    def printProcess(self, text, color='', style=''):
        self.printOutput(Color.process + text, color, True, style)

    # Run a system command
    def run(self, command, onlyFirstLineOnly=False):
        output = os.popen(command).readlines()

        if onlyFirstLineOnly:
            return output[0].replace('\n', '') if len(output) > 0 else None

        return str(output)

    # Terminate execution
    def terminate(self):
        raise SystemExit

    # Slep or Wait fro specified time before executing the rest
    def wait(self, duration):
        sleep(duration)

