# Custom Import
from helpers.System import System

system = System()

class Application:
    # Application Vars
    name = "Fin"

    # Home
    systemHome = system.env('SYSTEM_HOME')
    # home = systemHome + '/' + name.lower()
    home = system.env('APPLICATION_HOME')

    # Version
    version = "v2.0"

    # Directories
    configDir = systemHome + '/.config/' + name.lower()
    binDir = home + 'bin'

    # Files
    dockerComposeFile = home + '/docker-compose-asset.yml'
