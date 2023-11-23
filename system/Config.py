import os
import configparser

from system.App import App
from system.Env import Env


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
        data = {}
        for section in self.__config.sections():
            data[section] = self.get_section(section)

        return data

    def get_section(self, section: str, default: dict = {}) -> dict:
        if self.__config.has_section(section):
            options = {}
            for option in self.__config.options(section):
                options[option] = self.get(section, option)

            return options

        return default

    def get(self, section: str, option: str, default: str = None) -> str:
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
