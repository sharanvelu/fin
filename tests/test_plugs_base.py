"""Tests for fincli.plugs.base — FinPlug, PlugType, ContainerSpec, PortMapping."""

from __future__ import annotations

from fincli.core.env import EnvSpec, ProjectEnv
from fincli.plugs.base import (
    ContainerSpec,
    FinPlug,
    PlugCommand,
    PlugType,
    PortMapping,
    VolumeMount,
)


def test_plugtype_values():
    assert PlugType.APP.value == "APP"
    assert PlugType.ASSET.value == "ASSET"
    assert PlugType.GLOBAL.value == "GLOBAL"
    assert PlugType("APP") is PlugType.APP


def test_portmapping_as_docker_with_host():
    pm = PortMapping(container=80, host=8080)
    assert pm.as_docker() == ("80/tcp", 8080)


def test_portmapping_as_docker_random_host():
    pm = PortMapping(container=80)
    assert pm.as_docker() == ("80/tcp", None)


def test_portmapping_udp_protocol():
    pm = PortMapping(container=53, host=53, protocol="udp")
    assert pm.as_docker() == ("53/udp", 53)


def test_volumemount_defaults():
    v = VolumeMount(host="/h", container="/c")
    assert v.mode == "rw"


def test_containerspec_defaults():
    spec = ContainerSpec(service="web", image="demo:latest")
    assert spec.name_suffix == "web"
    assert spec.container_name is None
    assert spec.environment == {}
    assert spec.ports == []
    assert spec.volumes == []
    assert spec.web_exposed is False
    assert spec.web_port is None


def test_base_plug_defaults():
    p = FinPlug()
    assert p.name == ""
    assert p.version == "0.0.0"
    assert p.plug_type is PlugType.GLOBAL
    assert isinstance(p.env_spec(), EnvSpec)
    assert p.primary_spec(ProjectEnv(cwd=__import__("pathlib").Path("/x"))) is None
    assert p.asset_specs(ProjectEnv(cwd=__import__("pathlib").Path("/x"))) == []
    assert p.commands() == {}


def test_plug_info():
    class MyPlug(FinPlug):
        name = "myplug"
        version = "2.1.0"
        plug_type = PlugType.APP
        description = "desc"

        def commands(self):
            return {
                "foo": PlugCommand("foo", lambda c, a: 0),
                "bar": PlugCommand("bar", lambda c, a: 0),
            }

    info = MyPlug().info()
    assert info["name"] == "myplug"
    assert info["version"] == "2.1.0"
    assert info["type"] == "APP"
    assert info["description"] == "desc"
    assert set(info["commands"]) == {"foo", "bar"}


def test_setup_hook_is_noop_by_default():
    # Should not raise.
    FinPlug().setup()


def test_plugcommand_fields():
    def handler(ctx, args):
        return 0

    cmd = PlugCommand("artisan", handler, "Run artisan", aliases=("art",))
    assert cmd.name == "artisan"
    assert cmd.handler is handler
    assert cmd.help == "Run artisan"
    assert cmd.aliases == ("art",)
