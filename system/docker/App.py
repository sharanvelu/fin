from system.App import App as Application

from system.docker.Container import Container


class App:
    __container = Container()
    __app = Application()

    def __init__(self) -> None:
        pass

    def __get_proxy_rule(self, host: str) -> str:
        # If the Host doesn't need any wildcard, then we can return the host with Host() rule
        if "*" not in host:
            return "Host(`" + host + "`)"

        hosts = []
        for i in host.split("."):
            if "*" not in i:
                hosts.append(i)
            else:
                hosts.append(i.replace("*", "{subdomain:[a-z0-9]+}"))

        return "HostRegexp(`" + ".".join(hosts) + "`)"

    def __generate_proxy_labels_for_host(self, host: str, container_port: int = 80) -> dict:
        host_key = self.__app.get_project_key(host)
        secure_key = host_key + "_secure"
        proxy_rule = self.__get_proxy_rule(host)
        return {
            # HTTP
            "traefik.http.routers." + host_key + ".rule": proxy_rule,
            "traefik.http.routers." + host_key + ".service": host_key + "_service",
            "traefik.http.services." + host_key + "_service.loadbalancer.server.port": str(container_port),
            # HTTPS
            "traefik.http.routers." + secure_key + ".tls": "true",
            "traefik.http.routers." + secure_key + ".rule": proxy_rule,
            "traefik.http.routers." + secure_key + ".service": secure_key + "_service",
            "traefik.http.services." + secure_key + "_service.loadbalancer.server.port": str(container_port),
        }

    def __get_proxy_labels(self, host: str, container_port: int = 80, additional_hosts: list = []) -> dict:
        proxy_labels = self.__generate_proxy_labels_for_host(host, container_port)

        for additional_host in additional_hosts:
            proxy_labels.update(self.__generate_proxy_labels_for_host(additional_host, container_port))

        return proxy_labels

    def __get_app_container_labels(self, host: str) -> dict:
        return {
            "com.example.vendor": self.__app.name,
            "com.example.type": "application",
            "com.example.host": host,
            "com.example.service": "Application",
        }

    def __prepare_labels(self, host: str, labels: dict = {}, container_port: int = 80, additional_hosts: list = []) -> dict:
        labels.update(self.__get_proxy_labels(host, container_port, additional_hosts))
        labels.update(self.__get_app_container_labels(host))

        return labels

    def __process_additional_hosts(self, additional_hosts: {list, None}):
        if additional_hosts is None:
            return []

        processed_hosts = []
        for host in additional_hosts.split(','):
            processed_hosts.append(host.strip())

        return processed_hosts

    def run(
            self,
            host: str,
            image: str,
            labels: dict = {},
            envs: dict = {},
            container_port: int = 80,
            volumes: list = [],
            ports: dict = {},
            additional_hosts: list = []
    ) -> None:
        additional_hosts = self.__process_additional_hosts(additional_hosts)

        self.__container.run(
            image=image,
            name=self.__app.get_container_name(host),
            volumes=volumes,
            labels=self.__prepare_labels(host, labels, container_port, additional_hosts),
            environment=envs,
            ports=ports,
        )
