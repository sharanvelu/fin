from helpers.Application import Application
from helpers.Color import Color
from helpers.Command import Output
from helpers.Docker import Asset, Docker, Proxy
from helpers.Env import Env
from helpers.System import System

class Container:
    app = Application()
    asset = Asset()
    docker = Docker()
    env = Env()
    system = System()
    output = Output()

    def up(self, actions=[]):
        # Print Info From Server
        # print(Network().getInfoFromServer())

        # Check for required ENV
        self.__checkRequiredEnv()

        # Check pDocker Private network existence
        self.docker.checkNetwork()

        # Check the status of the Asset Containers
        self.asset.checkAssetContainer()

        # Start the Project container
        self.__startProjectContainer()

        # Setup Proxy
        Proxy().setupProxy(self.__getContainerPort())

    # Check whether the required ENV var are present
    def __checkRequiredEnv(self):
        if self.env.env('SITE') == None:
            Output().printLn('Required Parameter ' + Color.cyan + self.env.getName('SITE') + Color.clear + ' is ' +
                             Color.red + 'missing' + Color.clear + ' from' + Color.cyan + ' .env' + Color.clear)

            # Terminate execution as required params is not present
            System().terminate()

    # Start the Project Container
    def __startProjectContainer(self):
        dockerImage = 'sharanvelu/laravel-php:' + self.env.env('PHP_VERSION', 'latest')
        if self.env.env('DOCKER_IMAGE', None) is not None:
            dockerImage = self.env.env('DOCKER_IMAGE')

        envs = {
            'CONTAINER_NAME': self.docker.containerName,
            'FIN_ASSET_USERNAME': self.asset.username,
            'FIN_ASSET_PASSWORD': self.asset.password,
            'FIN_ASSET_DEFAULT_DATABASE': self.asset.database,
            'FIN_NETWORK': self.docker.network,
            'PROJECT_ROOT_DIR': self.docker.serverProjectDir,
            'FIN_DOCKER_IMAGE': dockerImage,
            'FIN_COMPOSER_VERSION': self.env.env('COMPOSER_VERSION', '2')
        }
        self.env.setEnvs(envs)
        dockerComposeCommand = 'docker-compose -f ' + self.app.serverDockerComposeFile + ' -p ' + self.docker.serverProjectName

        # Todo : Check if the containers are already running before starting them again.
        # Need to change logic for project containers
        # output = self.system.run(dockerComposeCommand + ' ps | grep -E \'' + "|".join(assets) + '\' | grep exited')

        self.system.run(dockerComposeCommand + ' up -d')
        self.output.emptyLn()

    def __getContainerPort(self):
        exposedPort = self.system.run(
            'docker ps --filter "name=' + self.docker.containerName + '" --format "{{.Ports}}" -a', True)
        try:
            exposedPort = exposedPort.split(':')[1]
            return exposedPort.split('-')[0]
        except:
            return None