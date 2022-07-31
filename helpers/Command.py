import sys

# Custom Import
from helpers.Color import Color


class Command:
    def getArgs(self):
        return self.args

    def getCommand(self):
        return self.all[0] if len(self.all) > 0 else None

    def getActions(self):
        return self.actions

    def getFlags(self):
        return self.flags

    def getOptions(self):
        return self.options

    def getOption(self, option):
        if self.hasOption(option):
            return self.options[option]

        return None

    def hasOption(self, option):
        return True if option in self.options else False

    def __init__(self):
        self.args = sys.argv
        self.all = sys.argv[1:]
        self.options = {}
        self.actions = []
        self.flags = []
        for arg in self.all[1:]:
            if(arg.startswith('--')):
                optionData = arg.replace('--', '').split('=')
                option = optionData[0]
                value = optionData[1] if len(optionData) > 1 else None
                self.options[option] = value
            elif(arg.startswith('-')):
                self.flags.append(arg.replace('-', ''))
            else:
                self.actions.append(arg)

class Output:
    # Print Output in the terminal
    # Customize color and style of
    def __printOutput(self, text, color, newLine=False, style=''):
        if text:
            if newLine:
                print(color + style + text + Color.clear)
            else:
                print(color + style + text + Color.clear, end='')
        else:
            print('-')

    # Print a statement
    def print(self, text, color='', style=''):
        self.__printOutput(text, color, False, style)

    # Print a statement and add a new Line
    def printLn(self, text, color='', style=''):
        self.__printOutput(text, color, True, style)

    # Print an Empty Line
    def emptyLn(self):
        print(" ")

    # Print a statement with a Process indicator
    def process(self, text, color='', style=''):
        self.__printOutput(Color.process + text, color, True, style)

    # Print a statement with a Error indicator
    def error(self, text, color='', style=''):
        self.__printOutput(Color.error + text, color, True, style)
