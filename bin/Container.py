# Custom Import

from helpers.Application import Application
from helpers.Colors import Color
from helpers.Docker import Docker, Env, Proxy
from helpers.System import System


class Container:
    system = System()
    app = Application()
    docker = Docker()

    def up(self, actions=[]):
        # Print Info From Server
        # print(Network().getInfoFromServer())

        # Check for required ENV
        Env().checkRequiredEnv()

        # Check pDocker Private network existence
        self.docker.checkNetwork()

        # Check Composer Cache volume existence
        self.docker.checkComposerCacheVolume()

        # Check the status of the Asset Containers
        self.__checkAssetContainer()

        # Start the Project container
        self.__startProjectContainer()

        # Setup Proxy
        Proxy().setupProxy(self.__getContainerPort())

    # Check Asset Container status
    def __checkAssetContainer(self):
        if self.system.env('DOCKR_SKIP_ASSET') == '1':
            self.system.printLn(Color.cyan + 'DOCKR_SKIP_ASSET' + Color.clear + ' is provided, Skipping Asset containers and DB check.\n')
            if self.system.env('DOCKR_OVERRIDE_ASSET_CONFIG') != None:
                self.system.printLn(Color.red + 'Warning : ' + Color.cyan + 'DOCKR_OVERRIDE_ASSET_CONFIG ' + Color.clear + 'will be ignored.\n')

            self.system.printProcess('Starting Proxy Container...')
            self.__startAssetContainer(['proxy'])
            self.system.printLn('Proxy Container ' + Color.green + 'started ' + Color.clear + 'Successfully.\n')
        else:
            self.system.printProcess('Starting Asset Containers...')
            self.__startAssetContainer(['proxy', 'mysql', 'postgres', 'redis'])
            self.system.printLn('Asset Containers ' + Color.green + 'started ' + Color.clear + 'Successfully.\n')

    # Start Asset Containers
    def __startAssetContainer(self, assets):
        Env().putRequiredEnv()
        dockerComposeCommand = 'docker-compose -f ' + self.app.assetDockerComposeFile + ' -p ' + self.app.name.lower() + '_asset'

        # Todo : Check if the containers are already running before starting them again.
        # output = self.system.run(dockerComposeCommand + ' ps | grep -E \'' + "|".join(assets) + '\' | grep exited')

        self.system.run(dockerComposeCommand + ' up -d ' + " ".join(assets))
        self.system.printEmptyLn()

    # Start the Project Container
    def __startProjectContainer(self) :
        Env().putRequiredEnv()
        dockerComposeCommand = 'docker-compose -f ' + self.app.serverDockerComposeFile + ' -p ' + self.docker.projectName

        # Todo : Check if the containers are already running before starting them again.
        # output = self.system.run(dockerComposeCommand + ' ps | grep -E \'' + "|".join(assets) + '\' | grep exited')

        self.system.run(dockerComposeCommand + ' up -d')
        self.system.printEmptyLn()

    def __getContainerPort(self):
        exposedPort = self.system.run('docker ps --filter "name=' + self.docker.containerName + '" --format "{{.Ports}}" -a', True)
        try:
            exposedPort = exposedPort.split(':')[1]
            return exposedPort.split('-')[0]
        except :
            return None

