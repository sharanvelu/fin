# Custom imports
from helpers.Application import Application
from helpers.Color import Color
from helpers.Command import Output
from helpers.Docker import Asset, Docker
from helpers.Env import Env
from helpers.System import System


class Database:
    app = Application()
    asset = Asset()
    docker = Docker()
    env = Env()
    output = Output()
    system = System()

    baseCommand = 'docker-compose -f ' + app.assetDockerComposeFile + ' -p ' + asset.projectName

    def createDB(self):
        if self.env.pure('DB_CONNECTION', None) == 'mysql':
            if self.asset.canStartAsset('mysql'):
                self.output.process('Checking for database ' + Color.cyan + \
                    self.env.pure('DB_DATABASE') + Color.clear + ' presence in Mysql')
                self.output.emptyLn()

            self.__createMysqlDB(self.env.pure('DB_DATABASE'))

        if self.env.pure('DB_CONNECTION', None) == 'pgsql':
            if self.asset.canStartAsset('postgres'):
                self.output.process('Checking for database ' + Color.cyan + \
                    self.env.pure('DB_DATABASE') + Color.clear + ' presence in Postgres')
                self.output.emptyLn()

            self.__createPostgresDB(self.env.pure('DB_DATABASE'))

    def __createMysqlDB(self, database):
        subCommand = self.baseCommand + ' exec mysql bash -c "MYSQL_PWD=' + self.asset.password + ' mysql -u root -e '
        if self.system.run(subCommand + '\\"show databases;\\" | grep -w ' + database + '"', True) is None:
            self.output.process('Creating Database ' + Color.cyan + database + Color.clear)
            self.system.run(subCommand + '\\"create database ' + database + '\\" >> /dev/null"')
            self.system.run(subCommand + '\\"GRANT ALL PRIVILEGES ON *.* TO \'' + self.asset.username + '\'@\'%\'\\" >> /dev/null"')
            self.output.printLn('Database ' + Color.cyan + database + Color.clear + ' created successfully.')
        else:
            self.output.printLn('Database ' + Color.cyan + database + Color.clear + ' already exists. Skipping...')

    def __createPostgresDB(self, database):
        subCommand = self.baseCommand + ' exec postgres bash -c "psql -U ' + self.asset.username + ' '
        if self.system.run(subCommand + '-l | grep -w ' + database + '"', True) is None:
            self.output.process('Creating Database ' + Color.cyan + database + Color.clear)
            self.system.run(subCommand + '-d ' + self.asset.database + ' -c \\"create database ' + database + '\\" >> /dev/null"')
            # self.system.run(subCommand + '\\"GRANT ALL PRIVILEGES ON *.* TO \'' + self.asset.username + '\'@\'%\'\\" >> /dev/null"')
            self.output.printLn('Database ' + Color.cyan + database + Color.clear + ' created successfully.')
        else:
            self.output.printLn('Database ' + Color.cyan + database + Color.clear + ' already exists. Skipping...')