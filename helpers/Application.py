# Custom Import
import os
from helpers.System import System


class Application:
    system = System()

    # Application Vars
    name = 'Fin'

    # todo : change the lines
    # home = '/usr/local/lib'
    home = os.getenv('APPLICATION_HOME')

    # Version
    version = 'v2.0'

    # Directories
    configDir = system.home + '/.config/' + name.lower()
    binDir = home + 'bin'

    # Files
    assetDockerComposeFile = home + '/docker-compose-asset.yml'
    serverDockerComposeFile = home + '/docker-compose-server.yml'
