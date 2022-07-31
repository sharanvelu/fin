import os

# Custom Import
from helpers.Application import Application
from helpers.Color import Color
from helpers.Command import Output
from helpers.System import System


class Env:
    applicationName = Application().name

    def getName(self, name):
        return name if name.startswith(self.applicationName.upper() + '_') else (self.applicationName.upper() + '_' + name)

    # Get .env Variables from Bash Scripts
    # Project ENV's are loaded within the Bash script and loaded here.
    def env(self, key, default=None):
        return os.getenv(self.getName(key), default)

    # SetEnv for docker compose files.
    # Equivalent to 'export' in 'bash'
    def setEnv(self, key, value):
        os.environ[self.getName(key)] = str(value)

    # Put Required Env into OS environments
    def setEnvs(self, envs):
        # docker = Docker()
        # asset = Asset()

        # envs = {
        #     'CONTAINER_NAME': docker.containerName,
        #     'FIN_ASSET_USERNAME': asset.username,
        #     'FIN_ASSET_PASSWORD': asset.password,
        #     'FIN_ASSET_DEFAULT_DATABASE': asset.database,
        #     'FIN_NETWORK': docker.network,
        #     'FIN_COMPOSER_CACHE_VOLUME': docker.composerCacheVolume,
        #     'PROJECT_ROOT_DIR': docker.projectDir,
        #     'FIN_DOCKER_IMAGE': docker.image,
        # }

        for env in envs:
            self.setEnv(env, envs[env])

        # Features
        # 'FIN_COMPOSER_CACHE_VOLUME': self.docker.composerCacheVolume,
        # self.setEnv('FIN_COMPOSER_VERSION', laravel.composerVersion)
        # self.setEnv('FIN_SITE', docker.site)
