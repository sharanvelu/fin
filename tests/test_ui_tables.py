"""Tests for fincli.ui.tables — status colouring, port rendering, table factories."""

from __future__ import annotations

import pytest
from rich.table import Table

from fincli.ui import tables
from fincli.ui.tables import (
    make_container_table,
    make_image_table,
    status_style,
    _human_size,
    _ports_to_str,
)

from conftest import make_fake_container, make_fake_image


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
