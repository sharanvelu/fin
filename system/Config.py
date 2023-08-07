import os
import configparser

from system.Env import Env
from system.App import App

class Config:
    __app = App()

    def __init__(self, config: str) -> None:
        self.config = config
        self.__createConfigFile(config)

        # Method to read config file settings
        configParser = configparser.ConfigParser()
        configParser.read(self.__getConfigFilePath(config))

        self.__config = configParser

    def __getConfigFilePath(self, config):
        env = Env()
        configPath = env.pure('HOME') + '/.config/' + self.__app.name_key + '/' + config
        return configPath if configPath.endswith('.ini') else (configPath + '.ini')

    def __createConfigFile(self, config):
        configFilePath = self.__getConfigFilePath(config)
        if not os.path.exists(configFilePath):
            fp = open(configFilePath, 'x')
            fp.close()

    def getAll(self):
        return self.__config._sections

    def getSection(self, section: str, default: dict = {}):
        if self.__config.has_section(section):
            return self.getAll()[section]

        return default

    def get(self, section: str, option: str, default = None):
        if self.__config.has_option(section, option):
            return self.__config.get(section, option)

        return default
    
    def set(self, section: str, options: dict = {}) :
        if not self.__config.has_section(section):
            self.__config.add_section(section)

        for option in options:
            self.__config.set(section, str(option), str(options[option]))

            with open(self.__getConfigFilePath(self.config), 'w') as configfileObj:
                self.__config.write(configfileObj)
                configfileObj.flush()
                configfileObj.close()


# Config usage Example

# from helpers.Configuration import Configuration
# config = Configuration()
# config.read('/Users/sharan/Projects/dockr-python/config.ini')
# print(config.getAll())
# print(config.get('FTPSettings', 'username'))
# config.set('section', {'key': 'value'})
