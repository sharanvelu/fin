"""Tests for fincli.core.certs — discovery, tar packing, install flow."""

from __future__ import annotations

import io
import tarfile

import pytest

from fincli.config import Config
from fincli.core import certs
from fincli.plugs.base import ContainerSpec

from conftest import make_fake_container


def _write_certs(**files: str):
    """Create ~/.fin/certs (isolated tmp) with the given name->content files."""
    certs_dir = Config.certs_dir()
    certs_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (certs_dir / name).write_text(content, encoding="utf-8")
    return certs_dir


def _spec(**kw) -> ContainerSpec:
    return ContainerSpec(service="web", image="demo:latest", **kw)


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def test_discover_certs_empty_when_no_dir():
    assert certs.discover_certs() == []


def test_discover_certs_finds_pem_and_crt_ignores_others():
    _write_certs(**{
        "corp.pem": "PEM",
        "root.crt": "CRT",
        "notes.txt": "nope",
        "README.md": "nope",
    })
    names = [p.name for p in certs.discover_certs()]
    assert names == ["corp.pem", "root.crt"]  # sorted, only pem/crt


def test_discover_certs_case_insensitive_suffix():
    _write_certs(**{"upper.PEM": "x", "mixed.Crt": "y"})
    assert len(certs.discover_certs()) == 2


# --------------------------------------------------------------------------- #
# naming + tar
# --------------------------------------------------------------------------- #
def test_dest_name_forces_crt_and_prefix(tmp_path):
    from pathlib import Path
    assert certs._dest_name(Path("/x/corp.pem")) == "fin-corp.crt"
    assert certs._dest_name(Path("/x/root.crt")) == "fin-root.crt"


def test_build_tar_renames_members_and_preserves_content():
    certs_dir = _write_certs(**{"corp.pem": "PEMDATA", "root.crt": "CRTDATA"})
    files = sorted(certs_dir.iterdir())
    blob = certs._build_tar(files)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r") as tar:
        members = {m.name: tar.extractfile(m).read().decode() for m in tar.getmembers()}
    assert members == {"fin-corp.crt": "PEMDATA", "fin-root.crt": "CRTDATA"}


# --------------------------------------------------------------------------- #
# install_certs
# --------------------------------------------------------------------------- #
def test_install_certs_noop_when_no_certs():
    c = make_fake_container()
    certs.install_certs(c, _spec(install_certs=True))
    c.put_archive.assert_not_called()


def test_install_certs_copies_and_refreshes():
    _write_certs(**{"corp.pem": "PEM"})
    c = make_fake_container(name="app-web")
    c.put_archive.return_value = True
    c.exec_run.return_value = (0, b"done")

    certs.install_certs(c, _spec(install_certs=True))

    # tar pushed into the Debian default trust dir
    assert c.put_archive.call_args.args[0] == "/usr/local/share/ca-certificates"
    # the refresh command ran
    update_calls = [call for call in c.exec_run.call_args_list
                    if call.args and call.args[0] == ["update-ca-certificates"]]
    assert len(update_calls) == 1
    assert update_calls[0].kwargs.get("user") == "root"


def test_install_certs_honours_spec_overrides():
    _write_certs(**{"corp.pem": "PEM"})
    c = make_fake_container()
    c.put_archive.return_value = True
    c.exec_run.return_value = (0, b"")

    spec = _spec(
        install_certs=True,
        cert_dir="/etc/pki/ca-trust/source/anchors",
        cert_update_cmd=["update-ca-trust", "extract"],
    )
    certs.install_certs(c, spec)

    assert c.put_archive.call_args.args[0] == "/etc/pki/ca-trust/source/anchors"
    assert any(
        call.args and call.args[0] == ["update-ca-trust", "extract"]
        for call in c.exec_run.call_args_list
    )


def test_install_certs_warns_on_put_archive_failure(capsys):
    _write_certs(**{"corp.pem": "PEM"})
    c = make_fake_container()
    c.put_archive.return_value = False
    certs.install_certs(c, _spec(install_certs=True))
    # update command must NOT run if the copy failed
    assert not any(
        call.args and call.args[0] == ["update-ca-certificates"]
        for call in c.exec_run.call_args_list
    )


def test_install_certs_warns_on_update_failure():
    _write_certs(**{"corp.pem": "PEM"})
    c = make_fake_container()
    c.put_archive.return_value = True
    c.exec_run.return_value = (1, b"boom")
    # Should not raise despite the non-zero refresh.
    certs.install_certs(c, _spec(install_certs=True))


def test_install_certs_never_raises_on_docker_error():
    _write_certs(**{"corp.pem": "PEM"})
    c = make_fake_container()
    c.put_archive.side_effect = RuntimeError("daemon gone")
    # best-effort: swallowed into a warning, no exception
    certs.install_certs(c, _spec(install_certs=True))


# --------------------------------------------------------------------------- #
# ContainerSpec declarative defaults
# --------------------------------------------------------------------------- #
def test_container_spec_cert_defaults():
    spec = ContainerSpec(service="web", image="demo")
    assert spec.install_certs is False
    assert spec.cert_dir == "/usr/local/share/ca-certificates"
    assert spec.cert_update_cmd == ["update-ca-certificates"]
