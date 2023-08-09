import os
import configparser

from system.Env import Env
from system.App import App


class Config:
    __app = App()

    def __init__(self, config: str) -> None:
        self.config = config
        self.__create_config_file(config)

        # Method to read config file settings
        config_parser = configparser.ConfigParser()
        config_parser.read(self.__get_config_file_path(config))

        self.__config = config_parser

    def __get_config_file_path(self, config):
        env = Env()
        config_path = env.pure("HOME") + "/.config/" + self.__app.name_key + "/" + config
        return config_path if config_path.endswith(".ini") else (config_path + ".ini")

    def __create_config_file(self, config):
        config_file_path = self.__get_config_file_path(config)
        if not os.path.exists(config_file_path):
            fp = open(config_file_path, "x")
            fp.close()

    def get_all(self):
        return self.__config._sections

    def get_section(self, section: str, default: dict = {}) -> dict:
        if self.__config.has_section(section):
            return self.get_all()[section]

        return default

    def get(self, section: str, option: str, default: str = '') -> str:
        if self.__config.has_option(section, option):
            return self.__config.get(section, option)

        return default

    def set(self, section: str, options: dict = {}) -> None:
        if not self.__config.has_section(section):
            self.__config.add_section(section)

        for option in options:
            self.__config.set(section, str(option), str(options[option]))

            with open(self.__get_config_file_path(self.config), "w") as configfileObj:
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
