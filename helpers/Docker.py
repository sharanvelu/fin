# Custom Import
from helpers.Colors import Color
from helpers.System import System
from helpers.Application import Application

app = Application()
system = System()
color = Color()


class Docker:
    # Network
    network = app.name.lower() + '_network'

    # Composer Cache Volume
    composerCacheVolume = app.name.lower() + '_composer_cache_1'

    # Project Name
    assetProjectName = app.name.lower() + '_asset'
    projectName = ''
    projectDir = ''

    # Image
    image = ''

    # PHP Version
    phpVersion = ''

    # Container Name
    containerName = ''

    def __init__(self):
        self.projectDir = system.env('PROJECT_ROOT_DIR')
        projectDirArray = self.projectDir.split('/')
        self.projectName = projectDirArray[-1].replace(' ', '-').lower()

        # Image
        self.phpVersion = system.env('DOCKR_PHP_VERSION', 'latest')
        defaultImage = 'sharanvelu/laravel-php' + self.phpVersion
        self.image = system.env('DOCKR_DOCKER_IMAGE', defaultImage)

        # Container Name
        self.containerName = system.env('DOCKR_CONTAINER_NAME', self.projectName)

    def checkNetwork(self):
        output = system.run('docker network ls | grep -w ' + self.network, True)
        if str(output).find(self.network) == -1:
            system.printLn('Creating ' + Color.cyan + app.name + Color.clear + ' Network.')
            system.run('docker network create ' + self.network)
            system.printLn('Network ' + Color.green + 'Created ' + Color.clear + 'Successfully.\n')

    def checkComposerCacheVolume(self):
        output = system.run('docker volume ls | grep -w ' + self.composerCacheVolume, True)
        if str(output).find(self.composerCacheVolume) == -1:
            system.printLn('Creating ' + Color.cyan + app.name + Color.clear + ' Composer Cache Volume.')
            system.run('docker volume create ' + self.composerCacheVolume)
            system.printLn('Composer Cache Volume ' + Color.green + 'Created ' + Color.clear + 'Successfully.\n')


class Asset:
    # Username
    username = app.name.lower()

    # password
    password = 'password'

    # Default Database
    database = app.name.lower()

    # Is Asset Up # Todo
    def isAssetUp(self, asset):
        return True


class Feature:
    # Composer Version
    composerVersion = ''

    # Site
    site = ''

    def __init__(self):
        self.composerVersion = system.env('DOCKR_COMPOSER_VERSION', '2')
        self.site = 'http://' + system.env('DOCKR_SITE')


class Env:
    # Put Required Env into OS environments
    def putRequiredEnv(self):
        docker = Docker()
        asset = Asset()
        feature = Feature()

        # Container
        system.setEnv('FIN_CONTAINER_NAME', docker.containerName)

        # Asset
        system.setEnv('FIN_ASSET_USERNAME', asset.username)
        system.setEnv('FIN_ASSET_PASSWORD', asset.password)
        system.setEnv('FIN_ASSET_DEFAULT_DATABASE', asset.database)

        # Docker
        system.setEnv('FIN_NETWORK', docker.network)
        system.setEnv('FIN_COMPOSER_CACHE_VOLUME', docker.composerCacheVolume)

        # Project
        system.setEnv('PROJECT_ROOT_DIR', docker.projectDir)

        # Docker Image
        system.setEnv('FIN_DOCKER_IMAGE', docker.image)

        # Features
        system.setEnv('FIN_COMPOSER_VERSION', feature.composerVersion)
        system.setEnv('FIN_SITE', feature.site)

    # Check whether the required ENV var are present
    def checkRequiredEnv(self):
        if system.env('DOCKR_SITE') == None:
            system.printLn('Required Parameter ' + Color.cyan + 'DOCKR_SITE' + Color.clear + ' is ' + Color.red + 'missing' + Color.clear + ' from ' + Color.cyan + '.env' + Color.clear)

            # Terminate execution as required params is not present
            system.terminate()

class Proxy:
    def setupProxy(self, containerPort):
        # Check if Asset Up
        if Asset().isAssetUp('proxy'):
            self.__checkSiteInHosts()

            system.printProcess('Setting Up Proxy...')
            self.__addSiteToProxy(system.env('DOCKR_SITE'), 'http://host.docker.internal:' + containerPort)

    def __checkSiteInHosts(self):
        site = Feature().site
        if '*' in Feature().site:
            system.print('Make sure you have added the appropriate site (')
            system.print(' ' + site)
            system.print(' ) in')
            system.print(' /etc/hosts', Color.cyan)
            system.printLn(' file')
        else:
            if system.run('grep -w ' + site + ' /etc/hosts', True) is not None:
                system.print('Specified site is not present in')
                system.print(' /etc/hosts', Color.cyan)
                system.printLn(' File')
                system.print('Kindly add the site')
                system.printLn(' ' + Feature().site + ' in the /etc/hosts file')

    def __addSiteToProxy(self, actualSite, proxySite):
        try :
            dockerComposeCommand = 'docker-compose -f ' + app.assetDockerComposeFile + ' -p ' + app.name.lower() + '_asset'
            command = dockerComposeCommand + ' exec proxy bash -c "add-listener ' + actualSite + ' ' + proxySite + ' >> /dev/null"'
            system.run(command)
            system.printLn('Your Application should be running at '+ color.red + color.underline + Feature().site + Color.clear)
        except :
            system.printError('Unable to configure proxy. Please check your configurations.')


