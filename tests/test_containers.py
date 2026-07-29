"""Tests for fincli.core.containers — labels, traefik routing, lookup, run."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.core.containers import (
    base_labels,
    ensure_network,
    find_container,
    list_containers,
    managed_filter,
    primary_container_name,
    run_container,
    traefik_host_key,
    traefik_labels,
    traefik_rule,
)
from fincli.core.errors import NotFound

from conftest import make_fake_container


# --------------------------------------------------------------------------- #
# base_labels
# --------------------------------------------------------------------------- #
def test_base_labels_full():
    labels = base_labels(
        fin_type="app", service="web", site="http://app.localhost", project="demo"
    )
    assert labels == {
        "FIN_MANAGED": "true",
        "FIN_TYPE": "app",
        "FIN_SERVICE": "web",
        "FIN_SITE": "http://app.localhost",
        "FIN_PROJECT": "demo",
    }


def test_base_labels_defaults():
    labels = base_labels(fin_type="asset", service="mysql")
    assert labels["FIN_SITE"] == "-"
    assert labels["FIN_PROJECT"] == "-"
    assert labels["FIN_MANAGED"] == "true"


# --------------------------------------------------------------------------- #
# traefik_host_key
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "site,expected",
    [
        ("my-app.localhost", "my_app"),
        ("app.localhost", "app"),
        ("*.example.localhost", "example"),
        ("foo.bar.localhost", "foo_bar"),
        ("plain", "plain"),
        ("  spaced.localhost  ", "spaced"),
    ],
)
def test_traefik_host_key(site, expected):
    assert traefik_host_key(site) == expected


def test_traefik_host_key_empty_fallback():
    # ".localhost" strips to empty -> fallback "app"
    assert traefik_host_key(".localhost") == "app"


# --------------------------------------------------------------------------- #
# traefik_rule
# --------------------------------------------------------------------------- #
def test_traefik_rule_plain_host():
    assert traefik_rule("app.localhost") == "Host(`app.localhost`)"


def test_traefik_rule_wildcard_hostregexp():
    rule = traefik_rule("*.example.localhost")
    assert rule.startswith("HostRegexp(")
    # dots escaped in the suffix
    assert r"example\.localhost" in rule
    assert rule == r"HostRegexp(`^.+\.example\.localhost$`)"


def test_traefik_rule_strips_whitespace():
    assert traefik_rule("  app.localhost  ") == "Host(`app.localhost`)"


# --------------------------------------------------------------------------- #
# traefik_labels
# --------------------------------------------------------------------------- #
def test_traefik_labels_full_dict():
    labels = traefik_labels("my-app.localhost", 80)
    key = "my_app"
    assert labels["traefik.enable"] == "true"
    assert labels[f"traefik.http.routers.{key}.rule"] == "Host(`my-app.localhost`)"
    assert labels[f"traefik.http.routers.{key}.entrypoints"] == Config.PROXY_ENTRYPOINTS
    assert labels[f"traefik.http.routers.{key}.service"] == f"{key}_service"
    assert (
        labels[f"traefik.http.services.{key}_service.loadbalancer.server.port"] == "80"
    )


def test_traefik_labels_wildcard_rule():
    labels = traefik_labels("*.example.localhost", 8080)
    key = "example"
    assert labels[f"traefik.http.routers.{key}.rule"].startswith("HostRegexp(")
    assert (
        labels[f"traefik.http.services.{key}_service.loadbalancer.server.port"]
        == "8080"
    )


def test_traefik_labels_port_is_string():
    labels = traefik_labels("app.localhost", 3000)
    port_key = "traefik.http.services.app_service.loadbalancer.server.port"
    assert labels[port_key] == "3000"
    assert isinstance(labels[port_key], str)


# --------------------------------------------------------------------------- #
# managed_filter
# --------------------------------------------------------------------------- #
def test_managed_filter_base():
    assert managed_filter() == {"label": ["FIN_MANAGED=true"]}


def test_managed_filter_extra():
    f = managed_filter(FIN_TYPE="asset", FIN_PROJECT="demo")
    assert f["label"][0] == "FIN_MANAGED=true"
    assert "FIN_TYPE=asset" in f["label"]
    assert "FIN_PROJECT=demo" in f["label"]


# --------------------------------------------------------------------------- #
# primary_container_name
# --------------------------------------------------------------------------- #
def test_primary_container_name_default():
    assert primary_container_name("demo") == "demo-web"


def test_primary_container_name_custom_service():
    assert primary_container_name("demo", "worker") == "demo-worker"


# --------------------------------------------------------------------------- #
# ensure_network
# --------------------------------------------------------------------------- #
def test_ensure_network_creates_when_absent(patch_docker):
    patch_docker.networks.list.return_value = []
    ensure_network()
    patch_docker.networks.create.assert_called_once_with(
        Config.NETWORK, driver="bridge"
    )


def test_ensure_network_noop_when_present(patch_docker):
    patch_docker.networks.list.return_value = [object()]
    ensure_network()
    patch_docker.networks.create.assert_not_called()


# --------------------------------------------------------------------------- #
# list_containers
# --------------------------------------------------------------------------- #
def test_list_containers_applies_managed_filter(patch_docker):
    patch_docker.containers.list.return_value = ["c1"]
    result = list_containers(all_=True, FIN_TYPE="asset")
    assert result == ["c1"]
    _, kwargs = patch_docker.containers.list.call_args
    assert kwargs["all"] is True
    assert "FIN_MANAGED=true" in kwargs["filters"]["label"]
    assert "FIN_TYPE=asset" in kwargs["filters"]["label"]


# --------------------------------------------------------------------------- #
# find_container
# --------------------------------------------------------------------------- #
def test_find_container_by_name_match(patch_docker):
    c = make_fake_container(name="demo-web")
    patch_docker.containers.list.return_value = [c]
    assert find_container("demo-web") is c


def test_find_container_falls_back_to_get(patch_docker):
    patch_docker.containers.list.return_value = []
    got = make_fake_container(name="byid")
    patch_docker.containers.get.side_effect = None
    patch_docker.containers.get.return_value = got
    assert find_container("byid") is got


def test_find_container_not_found_raises(patch_docker):
    patch_docker.containers.list.return_value = []
    patch_docker.containers.get.side_effect = Exception("no such container")
    with pytest.raises(NotFound):
        find_container("ghost")


# --------------------------------------------------------------------------- #
# run_container
# --------------------------------------------------------------------------- #
def test_run_container_creates_new(patch_docker):
    patch_docker.containers.list.return_value = []  # nothing existing
    patch_docker.networks.list.return_value = [object()]  # network exists
    created = make_fake_container(name="demo-web")
    patch_docker.containers.run.return_value = created

    result = run_container(
        image="demo:latest",
        name="demo-web",
        labels={"FIN_MANAGED": "true"},
        environment={"X": "1"},
        ports={"80/tcp": None},
        volumes={"/host": {"bind": "/c", "mode": "rw"}},
        command=["run"],
    )
    assert result.created is True
    assert result.container is created
    _, kwargs = patch_docker.containers.run.call_args
    assert kwargs["image"] == "demo:latest"
    assert kwargs["name"] == "demo-web"
    assert kwargs["network"] == Config.NETWORK
    assert kwargs["environment"] == {"X": "1"}
    assert kwargs["ports"] == {"80/tcp": None}
    assert kwargs["command"] == ["run"]


def test_run_container_idempotent_existing_running(patch_docker):
    existing = make_fake_container(name="demo-web", status="running")
    patch_docker.containers.list.return_value = [existing]
    result = run_container(image="x", name="demo-web", labels={})
    assert result.created is False
    assert result.container is existing
    existing.start.assert_not_called()
    patch_docker.containers.run.assert_not_called()


def test_run_container_starts_existing_stopped(patch_docker):
    existing = make_fake_container(name="demo-web", status="exited")
    patch_docker.containers.list.return_value = [existing]
    result = run_container(image="x", name="demo-web", labels={})
    assert result.created is False
    existing.start.assert_called_once()


def test_run_container_merges_extra(patch_docker):
    patch_docker.containers.list.return_value = []
    patch_docker.networks.list.return_value = [object()]
    run_container(image="x", name="n", labels={}, extra={"privileged": True})
    _, kwargs = patch_docker.containers.run.call_args
    assert kwargs["privileged"] is True


# --------------------------------------------------------------------------- #
# run_container — failed-run cleanup + friendly errors
# --------------------------------------------------------------------------- #
def test_run_container_port_in_use_cleans_up_and_raises(patch_docker):
    from fincli.core.errors import FinError

    # No container exists when run_container first checks; the cleanup pass then
    # finds the half-created leftover and must force-remove it.
    leftover = make_fake_container(name="demo-web")
    patch_docker.containers.list.side_effect = [
        [],  # initial existence check -> nothing
        [leftover],  # _cleanup_failed lookup -> leftover to remove
    ]
    patch_docker.networks.list.return_value = [object()]
    patch_docker.containers.run.side_effect = Exception(
        "driver failed programming external connectivity: "
        "Bind for 0.0.0.0:80 failed: port is already allocated"
    )

    with pytest.raises(FinError) as excinfo:
        run_container(
            image="demo:latest",
            name="demo-web",
            labels={},
            ports={"80/tcp": 80},
        )

    assert excinfo.value.title == "Port In Use"
    leftover.remove.assert_called_once_with(force=True)


def test_run_container_address_in_use_is_port_in_use(patch_docker):
    from fincli.core.errors import FinError

    patch_docker.containers.list.side_effect = [[], []]
    patch_docker.networks.list.return_value = [object()]
    patch_docker.containers.run.side_effect = Exception("address already in use")

    with pytest.raises(FinError) as excinfo:
        run_container(image="x", name="demo-web", labels={}, ports={"80/tcp": 80})
    assert excinfo.value.title == "Port In Use"


def test_run_container_generic_error_is_start_failed(patch_docker):
    from fincli.core.errors import FinError

    patch_docker.containers.list.side_effect = [[], []]
    patch_docker.networks.list.return_value = [object()]
    patch_docker.containers.run.side_effect = Exception("image not found: boom")

    with pytest.raises(FinError) as excinfo:
        run_container(image="ghost:latest", name="demo-web", labels={})
    assert excinfo.value.title == "Container Start Failed"


def test_run_container_cleanup_swallows_errors(patch_docker):
    # If the cleanup lookup itself raises, the original friendly error must
    # still surface (cleanup is best-effort and never masks the real failure).
    from fincli.core.errors import FinError

    def list_side_effect(*args, **kwargs):
        if list_side_effect.calls == 0:
            list_side_effect.calls += 1
            return []  # initial existence check
        raise Exception("docker list exploded during cleanup")

    list_side_effect.calls = 0
    patch_docker.containers.list.side_effect = list_side_effect
    patch_docker.networks.list.return_value = [object()]
    patch_docker.containers.run.side_effect = Exception("port is already allocated")

    with pytest.raises(FinError) as excinfo:
        run_container(image="x", name="demo-web", labels={}, ports={"80/tcp": 80})
    assert excinfo.value.title == "Port In Use"
