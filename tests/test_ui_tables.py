"""Tests for fincli.ui.tables — status colouring, port rendering, table factories."""

from __future__ import annotations

import pytest
from rich.table import Table

from datetime import datetime, timedelta, timezone

from rich.console import Group

from fincli.ui import tables
from fincli.ui.tables import (
    make_container_table,
    make_grouped_container_tables,
    make_image_table,
    render_grouped_containers,
    status_style,
    uptime_status,
    _human_size,
    _ports_to_str,
)

from conftest import make_fake_container, make_fake_image


def _typed(fin_type, **kw):
    """Make a fake container labelled with a FIN_TYPE (plus any extra labels)."""
    labels = {"FIN_TYPE": fin_type}
    labels.update(kw.pop("labels", {}))
    return make_fake_container(labels=labels, **kw)


@pytest.mark.parametrize(
    "status,style",
    [
        ("running", "green"),
        ("RUNNING", "green"),
        ("exited", "red"),
        ("dead", "red"),
        ("paused", "yellow"),
        ("created", "yellow"),
        ("weird", "white"),
        ("", "white"),
    ],
)
def test_status_style(status, style):
    assert status_style(status) == style


def test_ports_to_str_empty():
    c = make_fake_container()
    c.attrs = {"NetworkSettings": {"Ports": {}}}
    assert _ports_to_str(c) == "-"


def test_ports_to_str_renders():
    c = make_fake_container()
    c.attrs = {
        "NetworkSettings": {
            "Ports": {"80/tcp": [{"HostPort": "8080"}], "443/tcp": [{"HostPort": "8443"}]}
        }
    }
    out = _ports_to_str(c)
    assert "8080->80" in out
    assert "8443->443" in out


def test_ports_to_str_handles_none_bindings():
    c = make_fake_container()
    c.attrs = {"NetworkSettings": {"Ports": {"80/tcp": None}}}
    assert _ports_to_str(c) == "-"


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "0.0B"),
        (512, "512.0B"),
        (1024, "1.0KB"),
        (1048576, "1.0MB"),
        (1073741824, "1.0GB"),
    ],
)
def test_human_size(n, expected):
    assert _human_size(n) == expected


def test_make_container_table_returns_table():
    c = make_fake_container(name="demo-web", status="running",
                            labels={"FIN_SERVICE": "web"})
    c.attrs = {"Config": {"Labels": {"FIN_SERVICE": "web"}}, "NetworkSettings": {"Ports": {}}}
    table = make_container_table([c], title="Test")
    assert isinstance(table, Table)
    assert table.row_count == 1


def test_make_container_table_with_stats():
    c = make_fake_container(name="demo-web", status="running")
    c.attrs = {"Config": {"Labels": {}}, "NetworkSettings": {"Ports": {}}}
    table = make_container_table([c], stats={c.id: {"cpu": "1.2", "mem": "50MB"}})
    assert table.row_count == 1


# --------------------------------------------------------------------------- #
# uptime_status
# --------------------------------------------------------------------------- #
def test_uptime_status_running_seconds():
    started = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f000Z"
    )
    c = make_fake_container(status="running")
    c.attrs = {"State": {"Status": "running", "StartedAt": started}}
    out = uptime_status(c)
    assert out.startswith("Up ")
    assert "second" in out or "minute" in out


def test_uptime_status_health_suffix():
    started = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f000Z"
    )
    c = make_fake_container(status="running")
    c.attrs = {
        "State": {
            "Status": "running",
            "StartedAt": started,
            "Health": {"Status": "starting"},
        }
    }
    assert "(health: starting)" in uptime_status(c)


def test_uptime_status_falls_back_to_status():
    c = make_fake_container(status="exited")
    c.attrs = {"State": {"Status": "exited"}}
    assert uptime_status(c) == "Exited"


def test_uptime_status_defensive_on_missing_state():
    c = make_fake_container()
    c.attrs = {}
    assert uptime_status(c) == "-"


def test_uptime_status_bad_started_at_falls_back():
    c = make_fake_container(status="running")
    c.attrs = {"State": {"Status": "running", "StartedAt": "not-a-date"}}
    # Unparseable StartedAt -> fall back to capitalised status, no crash.
    assert uptime_status(c) == "Running"


# --------------------------------------------------------------------------- #
# grouped tables
# --------------------------------------------------------------------------- #
def test_grouped_tables_three_sections_in_order():
    app = _typed("app", name="myapp-web", id="app000000001")
    asset = _typed("asset", name="fin_redis", id="asset0000001")
    other = _typed("proxy", name="fin_proxy", id="proxy0000001")
    sections = make_grouped_container_tables([asset, other, app])
    headers = [h for h, _ in sections]
    assert headers == ["App Containers", "Asset Containers", "Other Containers"]


def test_grouped_tables_skip_empty_sections():
    app = _typed("app", name="myapp-web", id="app000000001")
    sections = make_grouped_container_tables([app])
    assert [h for h, _ in sections] == ["App Containers"]
    assert sections[0][1].row_count == 1


def test_grouped_tables_share_column_widths():
    # Sections have very different content widths; every section's columns must
    # still be pinned to one shared width so the tables line up.
    app = _typed("app", name="a-really-long-application-name-web", id="app000000001",
                 labels={"FIN_SERVICE": "web", "FIN_SITE": "http://strt.localhost"})
    asset = _typed("asset", name="fin_mysql", id="asset0000001",
                   labels={"FIN_SERVICE": "mysql"})
    other = _typed("proxy", name="fin_proxy", id="proxy0000001",
                   labels={"FIN_SERVICE": "proxy"})
    sections = make_grouped_container_tables([app, asset, other])
    assert len(sections) == 3
    width_sets = [tuple(col.width for col in table.columns) for _, table in sections]
    # All columns carry an explicit width, and every table shares the same set.
    assert all(w is not None for w in width_sets[0])
    assert width_sets[0] == width_sets[1] == width_sets[2]


def test_grouped_unknown_type_goes_to_other():
    # No FIN_TYPE label at all -> Other.
    c = make_fake_container(name="mystery", labels={"FIN_SERVICE": "x"})
    sections = make_grouped_container_tables([c])
    assert [h for h, _ in sections] == ["Other Containers"]


def test_grouped_global_type_goes_to_other():
    c = _typed("global", name="fin_dns", id="glob00000001")
    sections = make_grouped_container_tables([c])
    assert [h for h, _ in sections] == ["Other Containers"]


def test_grouped_table_default_omits_stats_columns():
    # Without stats, CPU%/Mem columns are not shown (they're only collected and
    # displayed with `fin ps -s`).
    app = _typed("app", name="myapp-web", id="app000000001")
    _, table = make_grouped_container_tables([app])[0]
    headers = [col.header for col in table.columns]
    assert headers == ["ID", "Name", "Service", "Site", "State", "Status", "Ports"]
    assert "CPU%" not in headers and "Mem" not in headers


def test_grouped_table_with_stats_includes_stats_columns():
    app = _typed("app", name="myapp-web", id="app000000001", status="running")
    _, table = make_grouped_container_tables(
        [app], stats={app.id: {"cpu": "1.0", "mem": "5MB"}}
    )[0]
    headers = [col.header for col in table.columns]
    assert headers == ["ID", "Name", "Service", "Site", "State", "Status",
                       "Ports", "CPU%", "Mem"]


def test_grouped_table_empty_stats_dict_still_shows_columns():
    # `-s` with stopped containers → empty dict, but columns still appear ("-").
    app = _typed("app", name="myapp-web", id="app000000001", status="exited")
    _, table = make_grouped_container_tables([app], stats={})[0]
    headers = [col.header for col in table.columns]
    assert "CPU%" in headers and "Mem" in headers


def test_grouped_table_uses_service_and_site_labels():
    app = _typed(
        "app", name="myapp-web", id="app000000001",
        labels={"FIN_SERVICE": "web", "FIN_SITE": "http://strt.localhost"},
    )
    app.attrs = {
        "Config": {"Labels": {
            "FIN_TYPE": "app",
            "FIN_SERVICE": "web",
            "FIN_SITE": "http://strt.localhost",
        }},
        "NetworkSettings": {"Ports": {}},
        "State": {"Status": "running"},
    }
    _, table = make_grouped_container_tables([app])[0]
    assert table.row_count == 1


def test_render_grouped_returns_group():
    app = _typed("app", name="myapp-web", id="app000000001")
    asset = _typed("asset", name="fin_redis", id="asset0000001")
    out = render_grouped_containers([app, asset])
    assert isinstance(out, Group)
    # Two sections -> a Rule + a Table each = 4 renderables.
    assert len(out.renderables) == 4


def test_render_grouped_with_stats():
    app = _typed("app", name="myapp-web", id="app000000001", status="running")
    out = render_grouped_containers([app], stats={app.id: {"cpu": "1.0", "mem": "5MB"}})
    assert isinstance(out, Group)


def test_make_image_table_returns_table():
    img = make_fake_image(tags=["demo:1.0"], size=1048576)
    table = make_image_table([img], title="Images")
    assert isinstance(table, Table)
    assert table.row_count == 1


def test_make_image_table_untagged():
    img = make_fake_image(tags=[])
    table = make_image_table([img])
    # one row for <none>:<none>
    assert table.row_count == 1
