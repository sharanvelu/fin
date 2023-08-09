from system.App import App
from system.Config import Config
from system.Env import Env
from system.Cli import Cli

from .Container import Container
from .Volume import Volume


class Asset:
    __app = App()
    __cli = Cli()
    __config = Config("assets")
    __env = Env()

    __container = Container()
    __volume = Volume()

    __defaultKeys = {
        "password": "password",
        "username": __app.name_key,
        "database": __app.name_key,
    }

    def __get_default_labels(self, service: str):
        return {
            "com.example.vendor": self.__app.name,
            "com.example.type": "asset",
            "com.example.host": service.lower() + ".fin",
            "com.example.service": service.capitalize(),
        }

    def __should_start_asset(self, asset: str):
        asset = asset.strip()
        for i in self.__env.get("OVERRIDE_ASSET", "").split(","):
            if i.strip() == asset:
                return True

        return "True" == str(
            self.__config.get(section=asset, option="start", default=False)
        )

    def start(self):
        self.start_proxy()

        if self.__env.get("SKIP_ASSET") == "skip":
            self.__cli.print_ln(
                self.__env.get_name("SKIP_ASSET")
                + self.__cli.color.clear
                + " is Provided. Skipping Asset startup.",
                self.__cli.color.cyan,
            )
            if self.__env.get("OVERRIDE_ASSET") is not None:
                self.__cli.print_ln(
                    self.__env.get_name("OVERRIDE_ASSET")
                    + self.__cli.color.clear
                    + " is also Provided. This will be omitted.",
                    self.__cli.color.cyan,
                )

            self.__cli.print_empty_ln()
            return None

        self.start_mysql()
        self.start_postgres()
        self.start_redis()

    def start_proxy(self):
        self.__container.run(
            image="sharanvelu/proxy:traefik-v1",
            name=self.__app.name_key + "_proxy",
            volumes=["/var/run/docker.sock:/var/run/docker.sock"],
            ports={80: 80, 8080: 8080, 443: 443},
            labels={"com.example.site": "localhost"},
        )

    def start_mysql(self):
        if self.__should_start_asset("mysql"):
            name = self.__app.name_key + "_mysql"
            self.__volume.create(name)

            envs = {
                "MYSQL_ROOT_PASSWORD": self.__defaultKeys.get("password"),
                "MYSQL_USER": self.__defaultKeys.get("username"),
                "MYSQL_PASSWORD": self.__defaultKeys.get("password"),
                "MYSQL_DATABASE": self.__defaultKeys.get("database"),
                "MYSQL_ALLOW_EMPTY_PASSWORD": "yes",
            }

            self.__container.run(
                image="ubuntu/mysql",
                name=name,
                volumes=[name + ":/var/lib/mysql"],
                ports={3306: 3306},
                labels=self.__get_default_labels("mysql"),
                environment=envs,
                command=["--default-authentication-plugin=mysql_native_password"],
            )

    def start_postgres(self):
        if self.__should_start_asset("postgres"):
            name = self.__app.name_key + "_postgres"
            self.__volume.create(name)

            envs = {
                "POSTGRES_USER": self.__defaultKeys.get("username"),
                "POSTGRES_PASSWORD": self.__defaultKeys.get("password"),
                "POSTGRES_DB": self.__defaultKeys.get("database"),
            }

            self.__container.run(
                image="postgres",
                name=name,
                volumes=[name + ":/var/lib/postgresql/data"],
                ports={5432: 5432},
                labels=self.__get_default_labels("postgres"),
                environment=envs,
            )

    def start_redis(self):
        if self.__should_start_asset("redis"):
            name = self.__app.name_key + "_redis"
            self.__volume.create(name)

            self.__container.run(
                image="redis:alpine",
                name=name,
                volumes=[name + ":/data"],
                ports={6379: 6379},
                labels=self.__get_default_labels("redis"),
            )


# # from system.App import App
# from system.Config import Config

# config = Config('assets')

# print(config.set('assets', {'asd':'asd'}))
# print(config.get('assets', 'mysql'))


# raise SystemExit
