"""Tests for fincli.core.orchestrator — spec->container, asset selection."""

from __future__ import annotations

import pytest

from fincli.config import Config
from fincli.core import orchestrator as orch
from fincli.core.env import ProjectEnv
from fincli.plugs.base import ContainerSpec, PortMapping, VolumeMount

from conftest import make_fake_container


def _env(tmp_path, **values):
    return ProjectEnv(cwd=tmp_path, values=dict(values))


def test_ports_to_docker():
    out = orch._ports_to_docker([PortMapping(80, 8080), PortMapping(443)])
    assert out == {"80/tcp": 8080, "443/tcp": None}


def test_volumes_to_docker():
    out = orch._volumes_to_docker([VolumeMount("/h", "/c", "ro")])
    assert out == {"/h": {"bind": "/c", "mode": "ro"}}


def test_start_primary_applies_labels_and_mount(monkeypatch, patch_docker, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        from fincli.core.containers import RunResult
        return RunResult(container=make_fake_container(), created=True)

    monkeypatch.setattr(orch, "run_container", fake_run)
    monkeypatch.setattr(orch, "ensure_network", lambda: None)

    spec = ContainerSpec(
        service="web", image="demo:latest", name_suffix="web",
        web_exposed=True, web_port=80, workdir_mount="/app",
    )
    env = _env(tmp_path / "myproj", FIN_SITE="app.localhost")
    (tmp_path / "myproj").mkdir()
    orch.start_primary(spec, env)

    labels = captured["labels"]
    assert labels[Config.LABEL_TYPE] == "app"
    assert labels[Config.LABEL_SERVICE] == "web"
    # traefik labels applied because web_exposed + site present
    assert labels["traefik.enable"] == "true"
    # cwd mounted at workdir_mount
    assert captured["volumes"][str(env.cwd)] == {"bind": "/app", "mode": "rw"}


def test_start_primary_no_traefik_without_site(monkeypatch, patch_docker, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        from fincli.core.containers import RunResult
        return RunResult(container=make_fake_container(), created=False)

    monkeypatch.setattr(orch, "run_container", fake_run)
    monkeypatch.setattr(orch, "ensure_network", lambda: None)
    spec = ContainerSpec(service="web", image="demo", web_exposed=True, web_port=80)
    orch.start_primary(spec, _env(tmp_path))
    assert "traefik.enable" not in captured["labels"]


def test_start_primary_installs_certs_when_opted_in(monkeypatch, patch_docker, tmp_path):
    calls = []
    container = make_fake_container()

    def fake_run(**kwargs):
        from fincli.core.containers import RunResult
        return RunResult(container=container, created=True)

    monkeypatch.setattr(orch, "run_container", fake_run)
    monkeypatch.setattr(orch, "ensure_network", lambda: None)
    monkeypatch.setattr(orch, "install_certs", lambda c, s: calls.append((c, s)))

    spec = ContainerSpec(service="web", image="demo", install_certs=True)
    orch.start_primary(spec, _env(tmp_path))
    assert calls == [(container, spec)]


def test_start_primary_skips_certs_by_default(monkeypatch, patch_docker, tmp_path):
    calls = []

    def fake_run(**kwargs):
        from fincli.core.containers import RunResult
        return RunResult(container=make_fake_container(), created=True)

    monkeypatch.setattr(orch, "run_container", fake_run)
    monkeypatch.setattr(orch, "ensure_network", lambda: None)
    monkeypatch.setattr(orch, "install_certs", lambda c, s: calls.append(s))

    orch.start_primary(ContainerSpec(service="web", image="demo"), _env(tmp_path))
    assert calls == []  # install_certs defaults to False


def test_start_asset_installs_certs_when_opted_in(monkeypatch, patch_docker, tmp_path):
    calls = []

    def fake_run(**kwargs):
        from fincli.core.containers import RunResult
        return RunResult(container=make_fake_container(), created=True)

    monkeypatch.setattr(orch, "run_container", fake_run)
    monkeypatch.setattr(orch, "ensure_network", lambda: None)
    monkeypatch.setattr(orch, "install_certs", lambda c, s: calls.append(s))

    spec = ContainerSpec(service="mysql", image="mysql:8.0",
                         container_name="fin_mysql", install_certs=True)
    orch.start_asset(spec)
    assert calls == [spec]


def test_start_asset_fixed_name(monkeypatch, patch_docker, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        from fincli.core.containers import RunResult
        return RunResult(container=make_fake_container(), created=True)

    monkeypatch.setattr(orch, "run_container", fake_run)
    monkeypatch.setattr(orch, "ensure_network", lambda: None)
    spec = ContainerSpec(service="mysql", image="mysql:8.0", container_name="fin_mysql")
    orch.start_asset(spec)
    assert captured["name"] == "fin_mysql"
    assert captured["labels"][Config.LABEL_TYPE] == "asset"


def test_resolve_enabled_assets_override(monkeypatch, tmp_path):
    from fincli.plugs.base import PlugType

    class FakeInstance:
        name = "mysql"

    class FakeLP:
        plug_type = PlugType.ASSET
        instance = FakeInstance()

    monkeypatch.setattr(orch, "is_asset_enabled", lambda n: False, raising=False)
    import fincli.core.store as store
    monkeypatch.setattr(store, "is_asset_enabled", lambda n: False)
    import fincli.plugs.loader as loader
    monkeypatch.setattr(loader, "load_by_name", lambda n: FakeLP() if n == "mysql" else None)
    monkeypatch.setattr(loader, "load_all", lambda: [])

    env = _env(tmp_path, FIN_OVERRIDE_ASSETS="mysql,ghost")
    result = orch.resolve_enabled_assets(env)
    assert len(result) == 1
    assert result[0].instance.name == "mysql"


def test_resolve_enabled_assets_from_config(monkeypatch, tmp_path):
    from fincli.plugs.base import PlugType

    class FakeInstance:
        name = "redis"

    class FakeLP:
        plug_type = PlugType.ASSET
        instance = FakeInstance()

    import fincli.core.store as store
    import fincli.plugs.loader as loader
    monkeypatch.setattr(store, "is_asset_enabled", lambda n: n == "redis")
    monkeypatch.setattr(loader, "load_all", lambda: [FakeLP()])
    monkeypatch.setattr(loader, "load_by_name", lambda n: None)

    env = _env(tmp_path)
    result = orch.resolve_enabled_assets(env)
    assert [lp.instance.name for lp in result] == ["redis"]


def test_start_assets_for_starts_each(monkeypatch, tmp_path):
    spec = ContainerSpec(service="redis", image="redis:7", container_name="fin_redis")

    class FakeInstance:
        name = "redis"

        def asset_specs(self, env):
            return [spec]

    class FakeLP:
        instance = FakeInstance()

    monkeypatch.setattr(orch, "resolve_enabled_assets", lambda env: [FakeLP()])
    started_specs = []
    monkeypatch.setattr(orch, "start_asset", lambda s: started_specs.append(s) or make_fake_container())
    result = orch.start_assets_for(_env(tmp_path))
    assert len(result) == 1
    assert started_specs == [spec]
