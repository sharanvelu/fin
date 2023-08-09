import sys

from system.App import App


class Color:
    # Font Colors
    clear = "\033[0m"
    red = "\033[38;5;196m"
    green = "\033[38;3;32m"
    white = "\033[1;37m"
    cyan = "\033[1;36m"

    # Font Styling
    bold = "\033[1m"
    underline = "\033[4m"
    italic = "\033[3m"

    # Process Indicator
    process = cyan + "=> " + clear

    # Process Indicator
    error = red + "## "


class Output:
    color = Color()

    # Print Output in the terminal
    # Customize color and style of
    def __print_output(self, text: str, color: str, new_line: bool = False, style: str = "") -> None:
        if text:
            if new_line:
                print(color + style + text + Color.clear)
            else:
                print(color + style + text + Color.clear, end="")
        else:
            print("-")

    # Print a statement
    def print(self, text: str, color: str = "", style: str = "") -> None:
        self.__print_output(text, color, False, style)

    # Print a statement and add a new Line
    def print_ln(self, text: str, color: str = "", style: str = "") -> None:
        self.__print_output(text, color, True, style)

    # Print an Empty Line
    def print_empty_ln(self) -> None:
        print(" ")

    # Print a statement with a Process indicator
    def process(self, text: str, color: str = "", style: str = "") -> None:
        self.__print_output(Color.process + text, color, True, style)

    # Print a statement with a Error indicator
    def error(self, text: str, color: str = "", style: str = "") -> None:
        self.__print_output(Color.error + text, color, True, style)

    # Print a statement with a Error indicator
    def dd(self, text: str, color: str = "", style: str = "") -> None:
        self.__print_output(text, color, True, style)
        App().terminate()


class Cli(Output):
    def get_args(self):
        return self.args

    def get_command(self):
        return self.all[0] if len(self.all) > 0 else None

    def get_actions(self):
        return self.actions

    def get_flags(self):
        return self.flags

    def get_options(self):
        return self.options

    def get_option(self, option):
        if self.has_option(option):
            return self.options[option]

        return None

    def has_option(self, option):
        return True if option in self.options else False

    def __init__(self):
        self.args = sys.argv
        self.all = sys.argv[1:]
        self.options = {}
        self.actions = []
        self.flags = []
        for arg in self.all[1:]:
            if arg.startswith("--"):
                option_data = arg.replace("--", "").split("=")
                option = option_data[0]
                value = option_data[1] if len(option_data) > 1 else None
                self.options[option] = value
            elif arg.startswith("-"):
                self.flags.append(arg.replace("-", ""))
            else:
                self.actions.append(arg)
