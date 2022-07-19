import sys


class Command:
    def getArgs(self):
        return self.args

    def getCommand(self):
        return self.all[0] if len(self.all) > 0 else None

    def getActions(self):
        return self.actions

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
        for command in self.all[1:]:
            if(command.startswith('--')):
                optionData = command.replace('--', '').split('=')
                option = optionData[0]
                value = optionData[1] if len(optionData) > 1 else None
                self.options[option] = value
            else :
                self.actions.append(command)
