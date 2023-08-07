class App:
    # Application Vars
    name = 'Fin'

    # Version
    version = 'v2.0'

    # Network
    network = name.lower() + '_network'

    def __init__(self) -> None:
        # Application Vars
        self.name_key = self.name.lower()

    # Get Product Key from Host
    def getProjectKey(self, host) -> str:
        # Filters the hosts part without wildcard (*) and localhost
        hosts = [a for a in host.split('.') if (a != 'localhost' and '*' not in list(a))]
        # Return the remaining host part combined by underscore (_)
        return '_'.join(hosts)

    # Get Container Name from Host
    def getContainerName(self, host) -> str:
        return self.getProjectKey(host) + '_app'

    # Terminate the application
    def terminate(self):
        raise SystemExit
