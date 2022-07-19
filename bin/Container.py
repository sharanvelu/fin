# Custom Import

from helpers.Application import Application
from helpers.Colors import Color
from helpers.Docker import Docker, Env
from helpers.Network import Network
from helpers.System import System


class Container:
    system = System()
    app = Application()

    status = 'running'

    def up(self, actions=[]):
        network = Network()
        docker = Docker()

        # Print Info From Server
        # print(network.getInfoFromServer())

        # Check for required ENV
        Env().checkRequiredEnv()

        # Check pDocker Private network existence
        docker.checkNetwork()

        # Check Composer Cache volume existence
        docker.checkComposerCacheVolume()

        # Check the status of the Asset Containers
        self.checkAssetContainer()

        # Start the Project container
        self.startProjectContainer()

        # print(self.status)

    # Check Asset Container status
    def checkAssetContainer(self):
        if self.system.env('DOCKR_SKIP_ASSET') == '1':
            self.system.printLn(Color.cyan + 'DOCKR_SKIP_ASSET' + Color.clear + ' is provided, Skipping Asset containers and DB check.\n')
            if self.system.env('DOCKR_OVERRIDE_ASSET_CONFIG') != None:
                self.system.printLn(Color.red + 'Warning : ' + Color.cyan + 'DOCKR_OVERRIDE_ASSET_CONFIG ' + Color.clear + 'will be ignored.\n')

            self.system.printProcess('Starting Proxy Container...')
            self.startAssetContainer(['proxy'])
            self.system.printLn('Proxy Container ' + Color.green + 'started ' + Color.clear + 'Successfully.\n')
        else:
            self.system.printProcess('Starting Asset Containers...')
            self.startAssetContainer(['proxy', 'mysql', 'postgres', 'redis'])
            self.system.printLn('Asset Containers ' + Color.green + 'started ' + Color.clear + 'Successfully.\n')

    # Start Asset Containers
    def startAssetContainer(self, assets):
        Env().putRequiredEnv()
        dockerComposeCommand = 'docker-compose -f ' + self.app.dockerComposeFile + ' -p ' + self.app.name.lower() + '_asset'

        # Todo : Check if the containers are already running before starting them again.
        # output = self.system.run(dockerComposeCommand + ' ps | grep -E \'' + "|".join(assets) + '\' | grep exited')

        self.system.run(dockerComposeCommand + ' up -d ' + " ".join(assets))
        self.system.printEmptyLn()

    # Start the Project Container
    def startProjectContainer(self) :
        'docker run '
        print('starting proj cont')
    
    def getVolumes(self):
        return '--volume=fin_composer_cache:/root/.composer/cache ' + \
            '--volume=' +  + '/:/var/www/html/'
