import os
from .App import App
from .Cli import Cli

class Env:
    app = App()
    cli = Cli()

    # Get Name of the ENV variable.
    def getName(self, name):
        return (
            name
            if name.startswith(self.app.name.upper() + "_")
            else (self.app.name.upper() + "_" + name)
        )

    # Get .env Variables from Bash Scripts
    # Project ENV's are loaded within the Bash script and loaded here.
    def get(self, key, default=None):
        return os.getenv(self.getName(key), default)

    # Get .env Variables from Bash Scripts
    def pure(self, key, default=None):
        return os.getenv(key, default)

    # SetEnv for docker compose files.
    # Equivalent to 'export' in 'bash'
    def set(self, key, value):
        os.environ[self.getName(key)] = str(value)

    # Put Required Env into OS environments
    def setEnvs(self, envs):
        for env in envs:
            self.setEnv(env, envs[env])

    def checkEnvExistence(self, envs: list) -> None:
        missingEnvs = []
        for env in envs:
            if self.get(env) == None:
                missingEnvs.append(self.getName(env))

        if len(missingEnvs) > 0:
            self.cli.print("Required Env(s) ")
            self.cli.print(
                self.cli.color.cyan
                + (self.cli.color.clear + ", " + self.cli.color.cyan).join(missingEnvs)
            )
            self.cli.print(" are" + self.cli.color.red + " missing ")
            self.cli.printLn(" from" + self.cli.color.cyan + " .env" + self.cli.color.clear + " file.")

            self.app.terminate()

    def __loadSystemEnv(self):
        os.environ[self.getName('PROJECT_DIR')] = os.getcwd()
        os.environ[self.getName('PROJECT_NAME')] = os.getcwd().split('/')[-1]
        os.environ[self.getName('ROOT_PATH')] = '/'.join(__file__.split('/')[:-2])

    def loadEnv(self):
        # Load the .env file into the application.
        ## We cannot use the 3rd party plackage to load the dotenv vars.
        ## As we cannot expect everyone to have that package installed in the system.
        if os.path.exists('./.env'):
            with open('./.env') as f:
                # Loop through every line to get the complete env vars.
                for line in f:
                    # Check if the env var is commented.
                    if line[0] != '#':
                        # Split the line into key value pair using the '=' slug.
                        if len(line.strip().split('=', 1)) == 2:
                            key, value = line.strip().split('=', 1)
                            if value != '':
                                os.environ[key] = value.replace('"', '')

            self.__loadSystemEnv()

        else:
            self.cli.error(".env file is missing from the project directory.")
            self.cli.error("Make sure to run the command inside the Project directory.")
            self.app.terminate()

