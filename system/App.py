class App:
    # Application Vars
    name = "Fin"

    # Version
    version = "v2.0"

    # Version
    release_date = "2024-01-01"

    # Network
    network = name.lower() + "_network"

    # Info URL to fetch information from Server
    info_url = "https://fin.dockr.in/cli"

    def __init__(self) -> None:
        # Application Vars
        self.name_key = self.name.lower()

    # Get Product Key from Host
    def get_project_key(self, host) -> str:
        # Filters the hosts part without wildcard (*) and localhost
        hosts = [a for a in host.split(".") if (a != "localhost" and "*" not in list(a))]
        # Return the remaining host part combined by underscore (_)
        return "_".join(hosts)

    # Get Container Name from Host
    def get_container_name(self, host) -> str:
        return self.get_project_key(host) + "_app"

    # Terminate the application
    def terminate(self):
        raise SystemExit

    # Terminate the application
    def debug_mode(self):
        return True
