# Custom Import

from helpers.Application import Application
from helpers.Docker import Docker, Env, Proxy
from helpers.System import System


class Laravel:
    image = ''
    phpVersion = ''
    composerVersion = ''
    composerCacheVersion = ''

    def checkComposerCacheVolume():
        print('')
