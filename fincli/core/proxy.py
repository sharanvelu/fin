"""The built-in Traefik proxy — always available, not a plug.

Routing is driven entirely by container labels (the Docker provider), so once
the proxy is running, starting any web-exposed container with Traefik labels is
enough to route it. The proxy reads the Docker socket to watch for those labels.
"""

from __future__ import annotations

from typing import Any

from fincli.config import Config
from fincli.core.containers import base_labels, ensure_network, run_container, traefik_labels
from fincli.ui.console import success
from fincli.ui.spinners import fin_spinner

#: Traefik static-config command flags.
_PROXY_COMMAND = [
    "--entrypoints.web.address=:80",
    "--entrypoints.websecure.address=:443",
    "--providers.docker=true",
    "--providers.docker.exposedbydefault=false",
    f"--providers.docker.network={Config.NETWORK}",
    "--api.dashboard=true",
    "--api.insecure=true",
    "--log.level=INFO",
]


def is_proxy_running() -> bool:
    """Return True if the proxy container exists and is running."""
    from fincli.core.docker_client import get_docker

    client = get_docker().client
    matches = client.containers.list(all=True, filters={"name": f"^{Config.PROXY_CONTAINER}$"})
    return bool(matches) and matches[0].status == "running"


def ensure_proxy() -> Any:
    """Start the Traefik proxy container if not already running (idempotent)."""
    ensure_network()
    labels = base_labels(
        fin_type="proxy", service="proxy", site="http://traefik.localhost", project="-"
    )
    # The dashboard itself is routed at traefik.localhost → :8080.
    labels.update(traefik_labels("traefik.localhost", 8080))

    with fin_spinner("Ensuring proxy (traefik)…"):
        result = run_container(
            image=Config.PROXY_IMAGE,
            name=Config.PROXY_CONTAINER,
            labels=labels,
            ports={"80/tcp": 80, "443/tcp": 443, "8080/tcp": 8080},
            volumes={
                "/var/run/docker.sock": {
                    "bind": "/var/run/docker.sock",
                    "mode": "ro",
                }
            },
            command=_PROXY_COMMAND,
        )
    if result.created:
        success("Started [bold]fin_proxy[/bold] [dim](traefik) — dashboard at http://traefik.localhost[/dim]")
    return result.container
