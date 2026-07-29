"""Tests for fincli.commands.system — up / down / stop orchestration."""

from __future__ import annotations

import pytest

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import system
from fincli.core.env import ProjectEnv
from fincli.core.errors import FinError

from conftest import make_fake_container


def _env(cwd, **values):
    return ProjectEnv(cwd=cwd, values=dict(values))


# --------------------------------------------------------------------------- #
# up
# --------------------------------------------------------------------------- #
def test_up_requires_fin_app(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    with pytest.raises(FinError) as exc:
        system.up([])
    assert exc.value.title == "Missing FIN_APP"


def test_up_unknown_plug(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system.ProjectEnv,
        "load",
        classmethod(lambda cls: _env(tmp_path, FIN_APP="ghost")),
    )
    monkeypatch.setattr(system, "load_by_name", lambda name: None)
    with pytest.raises(FinError) as exc:
        system.up([])
    assert exc.value.title == "Plug Not Found"


def test_up_wrong_plug_type(monkeypatch, tmp_path):
    from fincli.plugs.base import PlugType

    class FakeLP:
        plug_type = PlugType.ASSET
        instance = object()

    monkeypatch.setattr(
        system.ProjectEnv,
        "load",
        classmethod(lambda cls: _env(tmp_path, FIN_APP="mysql")),
    )
    monkeypatch.setattr(system, "load_by_name", lambda name: FakeLP())
    with pytest.raises(FinError) as exc:
        system.up([])
    assert exc.value.title == "Wrong Plug Type"


def test_up_happy_path(monkeypatch, tmp_path):
    from fincli.plugs.base import ContainerSpec, FinPlug, PlugType

    class MyApp(FinPlug):
        name = "myapp"
        plug_type = PlugType.APP

        def primary_spec(self, env):
            return ContainerSpec(
                service="web", image="demo:latest", workdir_mount="/app"
            )

    class FakeLP:
        plug_type = PlugType.APP
        instance = MyApp()

    calls = {}
    monkeypatch.setattr(
        system.ProjectEnv,
        "load",
        classmethod(
            lambda cls: _env(tmp_path, FIN_APP="myapp", FIN_SITE="app.localhost")
        ),
    )
    monkeypatch.setattr(system, "load_by_name", lambda name: FakeLP())
    monkeypatch.setattr(system, "ensure_proxy", lambda: calls.setdefault("proxy", True))
    monkeypatch.setattr(
        system, "start_assets_for", lambda env: calls.setdefault("assets", []) or []
    )
    monkeypatch.setattr(
        system, "start_primary", lambda spec, env: calls.setdefault("primary", spec)
    )
    monkeypatch.setattr(
        system, "ensure_project_database", lambda env: calls.setdefault("db", True)
    )

    rc = system.up([])
    assert rc == EXIT_OK
    assert calls["proxy"] is True
    assert calls["primary"].image == "demo:latest"


def test_up_validates_env_contract(monkeypatch, tmp_path):
    from fincli.core.env import EnvSpec, EnvVar
    from fincli.plugs.base import FinPlug, PlugType

    class StrictApp(FinPlug):
        name = "strict"
        plug_type = PlugType.APP

        def env_spec(self):
            return EnvSpec.of([EnvVar("FIN_SITE", required=True)])

    class FakeLP:
        plug_type = PlugType.APP
        instance = StrictApp()

    monkeypatch.setattr(
        system.ProjectEnv,
        "load",
        classmethod(lambda cls: _env(tmp_path, FIN_APP="strict")),
    )  # no FIN_SITE
    monkeypatch.setattr(system, "load_by_name", lambda name: FakeLP())
    monkeypatch.setattr(system, "ensure_proxy", lambda: None)
    with pytest.raises(FinError) as exc:
        system.up([])
    assert exc.value.title == "Invalid Configuration"


# --------------------------------------------------------------------------- #
# down / stop
# --------------------------------------------------------------------------- #
def test_down_invalid_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    rc = system.down(["bogus"])
    assert rc == EXIT_USER


def test_down_no_containers(monkeypatch, tmp_path):
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", lambda **kw: [])
    rc = system.down([])
    assert rc == EXIT_OK


def test_down_removes_containers(monkeypatch, tmp_path):
    c1 = make_fake_container(name="demo-web", status="running")
    c2 = make_fake_container(name="demo-worker", status="exited")
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", lambda **kw: [c1, c2])
    rc = system.down([])
    assert rc == EXIT_OK
    c1.remove.assert_called_once()
    c2.remove.assert_called_once()


def test_down_force_flag(monkeypatch, tmp_path):
    c = make_fake_container(name="demo-web", status="exited")
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", lambda **kw: [c])
    system.down(["-f"])
    _, kwargs = c.remove.call_args
    assert kwargs["force"] is True


def test_down_asset_scope_filters(monkeypatch, tmp_path):
    captured = {}

    def fake_list(**kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", fake_list)
    system.down(["asset"])
    assert captured.get("FIN_TYPE") == "asset"


def test_down_all_scope(monkeypatch, tmp_path):
    captured = {}

    def fake_list(**kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", fake_list)
    system.down(["all"])
    assert captured == {"all_": True}


def test_stop_stops_running_only(monkeypatch, tmp_path):
    running = make_fake_container(name="demo-web", status="running")
    stopped = make_fake_container(name="demo-worker", status="exited")
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", lambda **kw: [running, stopped])
    rc = system.stop([])
    assert rc == EXIT_OK
    running.stop.assert_called_once()
    stopped.stop.assert_not_called()


def test_teardown_continues_on_error(monkeypatch, tmp_path):
    bad = make_fake_container(name="bad", status="running")
    bad.remove.side_effect = Exception("cannot remove")
    good = make_fake_container(name="good", status="running")
    monkeypatch.setattr(
        system.ProjectEnv, "load", classmethod(lambda cls: _env(tmp_path))
    )
    monkeypatch.setattr(system, "list_containers", lambda **kw: [bad, good])
    rc = system.down([])
    assert rc == EXIT_OK
    good.remove.assert_called_once()
