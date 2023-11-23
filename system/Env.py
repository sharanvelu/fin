import os

from system.App import App
from system.Cli import Cli


class Env:
    app = App()
    cli = Cli()

    # Get Name of the ENV variable.
    def get_name(self, name: str) -> str:
        if name.startswith(self.app.name.upper() + "_"):
            return name

        return self.app.name.upper() + "_" + name

    # Get .env Variables from Bash Scripts
    # Project ENVs are loaded within the Bash script and loaded here.
    def get(self, key: str, default: str = None):
        return os.getenv(self.get_name(key), default)

    # Get .env Variables from Bash Scripts
    def pure(self, key: str, default: str = None):
        return os.getenv(key, default)

    # SetEnv for docker compose files.
    # Equivalent to 'export' in 'bash'
    def set(self, key: str, value: str) -> None:
        os.environ[self.get_name(key)] = str(value)

    def check_env_existence(self, envs: list) -> None:
        missing_envs = []
        for env in envs:
            if self.get(env) is None:
                missing_envs.append(self.get_name(env))

        if len(missing_envs) > 0:
            self.cli.print("Required Env(s) ")
            self.cli.print(
                (self.cli.color.clear + ", " + self.cli.color.cyan).join(missing_envs),
                self.cli.color.cyan,
            )
            self.cli.print_ln(
                f" are {self.cli.color.red}missing{self.cli.color.clear} from {self.cli.color.cyan}.env{self.cli.color.clear} file."
            )
            self.app.terminate()

    def __load_system_env(self):
        os.environ[self.get_name("PROJECT_DIR")] = os.getcwd()
        os.environ[self.get_name("PROJECT_NAME")] = os.getcwd().split("/")[-1]
        os.environ[self.get_name("ROOT_PATH")] = "/".join(__file__.split("/")[:-2])

    def load_env(self):
        # Load the .env file into the application.
        # We cannot use the 3rd party package to load the dotenv vars.
        # As we cannot expect everyone to have that package installed in the system.
        if os.path.exists("./.env"):
            with open("./.env") as f:
                # Loop through every line to get the complete env vars.
                for line in f:
                    # Check if the env var is commented.
                    if line[0] != "#":
                        # Split the line into key value pair using the '=' slug.
                        if len(line.strip().split("=", 1)) == 2:
                            key, value = line.strip().split("=", 1)
                            if value != "":
                                os.environ[key] = value.replace('"', "")

            self.__load_system_env()

        else:
            self.cli.print_error(".env file is missing from the project directory.")
            self.cli.print_error("Make sure to run the command inside the Project directory.")
            self.app.terminate()
