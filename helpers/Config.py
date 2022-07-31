import configparser
from email.policy import default


class Config:
    def __init__(self, filePath):
        self.filePath = filePath if filePath.endswith('.ini') else (filePath + '.ini')

        # Method to read config file settings
        configParser = configparser.ConfigParser()
        configParser.read(self.filePath)

        self.config = configParser

    def getAll(self):
        return self.config._sections

    def getSection(self, section, default = {}):
        if self.config.has_section(section):
            return self.getAll()[section]

        return default

    def get(self, section, option, default = None):
        if self.config.has_option(section, option):
            return self.config.get(section, option)

        return default
    
    def set(self, section, options = {}) :
        if not self.config.has_section(section):
            self.config.add_section(section)

        for option in options:
            self.config.set(section, str(option), str(options[option]))

            with open(self.filePath, 'w') as configfileObj:
                self.config.write(configfileObj)
                configfileObj.flush()
                configfileObj.close()


# Config usage Example

# from helpers.Configuration import Configuration
# config = Configuration()
# config.read('/Users/sharan/Projects/dockr-python/config.ini')
# print(config.getAll())
# print(config.get('FTPSettings', 'username'))
# config.set('section', {'key': 'value'})
