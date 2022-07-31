# Custom Import
from helpers.Color import Color
from helpers.Command import Output
from helpers.Config import Config
from helpers.System import System
from helpers.Env import Env
from helpers.Application import Application

app = Application()
env = Env()
output = Output()
system = System()

applicationName = app.name.lower()


class Docker:
    network = applicationName + '_network'
    site = Env().env('SITE')

    def __init__(self):
        self.serverProjectDir = system.run('pwd', True)
        self.serverProjectName = system.run('basename `pwd`', True)
        self.containerName = self.serverProjectName + '-server'

    def checkNetwork(self):
        if str(system.run('docker network ls | grep -w ' + self.network, True)).find(self.network) == -1:
            output.printLn('Creating ' + Color.cyan + applicationName + Color.clear + ' Network.')
            system.run('docker network create ' + self.network)
            output.printLn('Network ' + Color.green + 'Created ' + Color.clear + 'Successfully.\n')

    def getContainerIds(self):
        containerIds = []
        for x in system.run('docker ps -f "network=' + self.network + '" -q -a', False, True):
            containerIds.append(x.replace('\n', ''))
        return containerIds


class Asset:
    username = applicationName
    password = 'password'
    database = applicationName
    projectName = applicationName + '_asset'

    def isUp(self, assets, checkAll = False):
        # Todo
        return True

    # Check Asset Container status
    def checkAssetContainer(self):
        if env.env('SKIP_ASSET') == '1':
            output.printLn(Color.cyan + env.getName('SKIP_ASSET') + Color.clear + ' is provided, Skipping Asset containers and DB check.\n')
            if env.env('OVERRIDE_ASSET_CONFIG') != None:
                output.printLn(Color.red + 'Warning : ' + Color.cyan + env.getName('OVERRIDE_ASSET_CONFIG') + Color.clear + ' will be ignored.\n')

            output.process('Starting Proxy Container...')
            self.__startAssetContainer(['proxy'])
            output.printLn('Proxy Container' + Color.green + ' started' + Color.clear + ' Successfully.\n')
        else:
            output.process('Starting Asset Containers...')
            self.__startAssetContainer(self.__getAllowedAssets(env.env('ASSET_CONFIG_OVERRIDE', [])))
            output.printLn('Asset Containers' + Color.green + ' started' + Color.clear + ' Successfully.\n')

    # Start Asset Containers
    def __startAssetContainer(self, assets):
        dockerComposeCommand = 'docker-compose -f ' + app.assetDockerComposeFile + ' -p ' + self.projectName

        # Todo : Check if the containers are already running before starting them again.
        # output = self.system.run(dockerComposeCommand + ' ps | grep -E \'' + "|".join(assets) + '\' | grep exited')

        system.run(dockerComposeCommand + ' up -d ' + " ".join(assets))
        output.emptyLn()
    
    def __getAllowedAssets(self, override = ''):
        config = Config(app.configDir + '/assets')

        if config.getSection('assets', None) is None:
            defaultConfigValues = {'mysql' : True, 'postgres' : True, 'Redis' : True, 'Proxy' : True}
            config.set('assets', defaultConfigValues)

        # By Default, Proxy container will be started
        allowedAssets = ['proxy']
        for asset in ['mysql', 'postgres', 'Redis']:
            if config.get('assets', asset.capitalize()) == 'True' or asset.lower() in override :
                # if configValues[x] == 'True' or x.lower() in override:
                allowedAssets.append(asset.lower())

        return allowedAssets

    def canStartAsset(self, asset):
        return asset.lower() in self.__getAllowedAssets(env.env('ASSET_CONFIG_OVERRIDE', []))


class Proxy:
    site = Docker().site

    def setupProxy(self, containerPort):
        # Check if Asset Up
        if Asset().isUp(['proxy'], True) and containerPort is not None:
            self.__checkSiteInHosts()

            output.process('Setting Up Proxy...')
            self.__addSiteToProxy(env.env('SITE'), 'http://host.docker.internal:' + containerPort)
        else :
            self.__printProxyError()

    def __checkSiteInHosts(self):
        if '*' in self.site:
            output.print('Make sure you have added the appropriate site (')
            output.print(' ' + self.site)
            output.print(' ) in')
            output.print(' /etc/hosts', Color.cyan)
            output.printLn(' file')
        else:
            if system.run('grep -w ' + self.site + ' /etc/hosts', True) is None:
                output.printLn('Specified site is not present in' + Color.cyan + ' /etc/hosts' + Color.clear + ' File.')
                output.printLn('Kindly add the site ' + self.site + ' in the /etc/hosts file')
                output.emptyLn()

    def __addSiteToProxy(self, actualSite, proxySite):
        try:
            dockerComposeCommand = 'docker-compose -f ' + app.assetDockerComposeFile + ' -p ' + Asset().projectName
            command = dockerComposeCommand + ' exec proxy bash -c "add-listener ' + actualSite + ' ' + proxySite + ' >> /dev/null"'
            system.run(command)
            output.printLn('Your Application should be running at ' + Color.red + Color.underline + 'http://' + self.site + Color.clear)
        except:
            self.__printProxyError()
    
    def __printProxyError(self):
        output.error('Unable to configure proxy. Please check your configurations.')
