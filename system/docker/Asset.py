from system.App import App
from system.Config import Config
from system.Env import Env
from system.Cli import Cli

from .Container import Container
from .Volume import Volume

class Asset:
    __app = App()
    __cli = Cli()
    __config = Config('assets')
    __env = Env()

    __container = Container()
    __volume = Volume()

    __defaultKeys = {
        'password': 'password',
        'username': __app.name_key,
        'database': __app.name_key,
    }

    def __getDefaultLabels(self, service: str):
        return {
            'com.example.vendor': self.__app.name,
            'com.example.type': 'asset',
            'com.example.host': service.lower() + '.fin',
            'com.example.service': service.capitalize()
        }

    def __shouldStartAsset(self, asset: str):
        asset = asset.strip()
        for i in self.__env.get('OVERRIDE_ASSET', '').split(','):
            if i.strip() == asset:
                return True

        return 'True' == str(self.__config.get(section = asset, option = 'start', default = False))

    def start(self):
        self.startProxy()

        if self.__env.get('SKIP_ASSET') == 'skip':
            self.__cli.printLn(self.__env.getName('SKIP_ASSET') + self.__cli.color.clear + ' is Provided. Skipping Asset startup.', self.__cli.color.cyan)
            if self.__env.get('OVERRIDE_ASSET') is not None:
                self.__cli.printLn(self.__env.getName('OVERRIDE_ASSET') + self.__cli.color.clear + ' is also Provided. This will be omitted.', self.__cli.color.cyan)

            self.__cli.printEmptyLn()
            return None

        self.startMysql()
        self.startPostgres()
        self.startRedis()

    def startProxy(self):
        self.__container.run(
            image = 'sharanvelu/proxy:traefik-v1',
            name = self.__app.name_key + '_proxy',
            volumes = ['/var/run/docker.sock:/var/run/docker.sock'],
            ports = {80:80, 8080:8080, 443:443},
            labels = {'com.example.site':'localhost'}
        )

    def startMysql(self):
        if self.__shouldStartAsset('mysql'):
            name = self.__app.name_key + '_mysql'
            self.__volume.create(name)

            envs = {
                'MYSQL_ROOT_PASSWORD': self.__defaultKeys.get('password'),
                'MYSQL_USER': self.__defaultKeys.get('username'),
                'MYSQL_PASSWORD': self.__defaultKeys.get('password'),
                'MYSQL_DATABASE': self.__defaultKeys.get('database'),
                'MYSQL_ALLOW_EMPTY_PASSWORD': 'yes',
            }

            self.__container.run(
                image = 'ubuntu/mysql',
                name = name,
                volumes = [name + ':/var/lib/mysql'],
                ports = {3306:3306},
                labels = self.__getDefaultLabels('mysql'),
                environment = envs,
                command = ['--default-authentication-plugin=mysql_native_password']
            )

    def startPostgres(self):
        if self.__shouldStartAsset('postgres'):
            name = self.__app.name_key + '_postgres'
            self.__volume.create(name)

            envs = {
                'POSTGRES_USER': self.__defaultKeys.get('username'),
                'POSTGRES_PASSWORD': self.__defaultKeys.get('password'),
                'POSTGRES_DB': self.__defaultKeys.get('database'),
            }

            self.__container.run(
                image = 'postgres',
                name = name,
                volumes = [name + ':/var/lib/postgresql/data'],
                ports = {5432:5432},
                labels = self.__getDefaultLabels('postgres'),
                environment = envs
            )

    def startRedis(self):
        if self.__shouldStartAsset('redis'):
            name = self.__app.name_key + '_redis'
            self.__volume.create(name)

            self.__container.run(
                image = 'redis:alpine',
                name = name,
                volumes = [name + ':/data'],
                ports = {6379:6379},
                labels = self.__getDefaultLabels('redis'),
            )







# # from system.App import App
# from system.Config import Config

# config = Config('assets')

# print(config.set('assetsa', {'asd':'asd'}))
# print(config.get('assets', 'mysql'))



# raise SystemExit
