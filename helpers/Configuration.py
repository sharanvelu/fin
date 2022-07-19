import configparser


class Configuration:
    def read(self, filePath):
        # Method to read config file settings
        configParser = configparser.ConfigParser()
        configParser.read(filePath)

        self.config = configParser

    def getAll(self):
        return self.config._sections

    def get(self, section, option):
        if self.config.has_option(section, option):
            return self.config.get(section, option)
        return ''


## Config usage Example

# from helpers.Configuration import Configuration
# config = Configuration()
# config.read('/Users/sharan/Projects/dockr-python/config.ini')
# print(config.getAll())
# print(config.get('FTPSettings', 'username'))

