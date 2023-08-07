from .Container import Container
from system.App import App as Application

class App:
    __container = Container()
    __app = Application()

    def __init__(self) -> None:
        pass

    def __getProxyRule(self, host: str) -> str:
        # If the Host doesn't needs any wildcard, then we can return the host with Host() rule
        if '*' not in host:
            return 'Host(`'+ host + '`)'

        hosts = []
        for i in host.split('.'):
            if '*' not in i:
                hosts.append(i)
            else:
                hosts.append(i.replace('*', '{subdomain:[a-z0-9]+}'))

        return 'HostRegexp(`' + '.'.join(hosts) + '`)'

    def __getProxyLabels(self, host: str, containerPort: int = 80) -> dict:
        hostKey = self.__app.getProjectKey(host)
        secureKey = hostKey + '_secure'
        proxyRule = self.__getProxyRule(host)
        return {
            # HTTP
            "traefik.http.routers." + hostKey + ".rule": proxyRule,
            "traefik.http.routers." + hostKey + ".service": hostKey + "_service",
            "traefik.http.services." + hostKey + "_service.loadbalancer.server.port": str(containerPort),
            # HTTPS
            "traefik.http.routers." + secureKey + ".tls": "true",
            "traefik.http.routers." + secureKey + ".rule": proxyRule,
            "traefik.http.routers." + secureKey + ".service": secureKey + "_service",
            "traefik.http.services." + secureKey + "_service.loadbalancer.server.port": str(containerPort),
        }
    
    def __getAppContainerLabels(self, host: str) -> dict:
        return {
            "com.example.vendor": self.__app.name,
            "com.example.type": "application",
            "com.example.host": host,
            "com.example.service": "Application"
        }

    def __prepareLabels(self, host: str, labels: dict = {}, containerPort: int = 80) -> dict:
        labels.update(self.__getProxyLabels(host, containerPort))
        labels.update(self.__getAppContainerLabels(host))
        return labels


    def run(self, host: str, image: str, labels: dict = {}, envs: dict = {}, containerPort: int = 80, volumes: list = [], ports:dict = {}) -> None:
        self.__container.run(
            image = image,
            name = self.__app.getContainerName(host),
            volumes = volumes,
            labels = self.__prepareLabels(host, labels, containerPort),
            environment = envs,
            ports=ports
        )
