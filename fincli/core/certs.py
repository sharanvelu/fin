"""Install user-provided CA certificates into running containers.

Fin lets you drop trusted CA certs into ``~/.fin/certs`` (``Config.certs_dir()``)
— the same per-user root that already holds ``config.json`` and ``registry.db``.
Any ``.pem`` / ``.crt`` file found there is copied into a container that *opted
in* (``ContainerSpec.install_certs``) and the distro's CA-refresh command is run
so the app inside trusts them.

This is **core** code: the sole Docker-touching path for cert installation.
Plugs only *declare* that they want certs (and, for non-Debian images, where the
trust store lives) on their :class:`~fincli.plugs.base.ContainerSpec`; the
orchestrator calls :func:`install_certs` after starting such a container. Copying
uses the Docker SDK (``put_archive`` + ``exec_run``) — never the docker CLI.

Distro note: the spec defaults target Debian/Ubuntu (and Alpine), where trusted
certs live in ``/usr/local/share/ca-certificates`` and are refreshed with
``update-ca-certificates`` — and where **only files ending in ``.crt`` are
ingested**. So every discovered cert is copied in with a ``.crt`` extension
regardless of its source name. RHEL-family images override ``cert_dir`` /
``cert_update_cmd`` on the spec.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from typing import Any

from fincli.config import Config
from fincli.ui.console import success, warning

#: Certificate file extensions Fin recognises in the certs directory.
_CERT_SUFFIXES = (".pem", ".crt")


def discover_certs() -> list[Path]:
    """Return the cert files (``*.pem`` / ``*.crt``) in ``~/.fin/certs``, sorted.

    Empty list when the directory is absent or holds no certs.
    """
    certs_dir = Config.certs_dir()
    if not certs_dir.is_dir():
        return []
    return [
        p
        for p in sorted(certs_dir.iterdir())
        if p.is_file() and p.suffix.lower() in _CERT_SUFFIXES
    ]


def _dest_name(cert: Path) -> str:
    """Destination filename inside the container's trust dir.

    Forced to ``.crt`` (Debian's ``update-ca-certificates`` ignores every other
    extension) and prefixed with ``fin-`` so Fin-managed certs are identifiable
    and never collide with the image's own bundle.
    """
    return f"fin-{cert.stem}.crt"


def _build_tar(certs: list[Path]) -> bytes:
    """Pack *certs* into an in-memory tar for ``put_archive``.

    Each entry is renamed via :func:`_dest_name` and made world-readable so the
    container's CA tooling can read it.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for cert in certs:
            data = cert.read_bytes()
            member = tarfile.TarInfo(name=_dest_name(cert))
            member.size = len(data)
            member.mode = 0o644
            tar.addfile(member, io.BytesIO(data))
    return buf.getvalue()


def _exec_result(result: Any) -> tuple[int, bytes]:
    """Normalise ``exec_run``'s return into ``(exit_code, output_bytes)``.

    docker-py returns an ``ExecResult`` namedtuple ``(exit_code, output)``; the
    output is ``bytes`` (or a stream, which we don't ask for here).
    """
    exit_code, output = result[0], result[1]
    if not isinstance(output, (bytes, bytearray)):
        output = b""
    return exit_code, bytes(output)


def install_certs(container: Any, spec: Any) -> None:
    """Copy the user's CA certs into *container* and refresh its trust store.

    No-ops quietly when ``~/.fin/certs`` is empty. Best-effort and never raises:
    a cert problem must not fail ``fin up`` — issues surface as warnings.
    """
    certs = discover_certs()
    if not certs:
        return

    cert_dir = getattr(spec, "cert_dir", "/usr/local/share/ca-certificates")
    update_cmd = getattr(spec, "cert_update_cmd", ["update-ca-certificates"])

    try:
        # Ensure the trust dir exists (minimal images may lack it), push the
        # certs in as a tar, then refresh the store — all as root, which both
        # the trust dir and the refresh tool require.
        container.exec_run(["mkdir", "-p", cert_dir], user="root")
        if not container.put_archive(cert_dir, _build_tar(certs)):
            warning(f"Could not copy certificates into '{container.name}'.")
            return
        exit_code, output = _exec_result(container.exec_run(update_cmd, user="root"))
        if exit_code == 0:
            success(
                f"Installed {len(certs)} CA certificate(s) into "
                f"[bold]{container.name}[/bold]"
            )
        else:
            detail = output.decode("utf-8", "replace").strip()
            warning(
                f"Copied certs into '{container.name}' but "
                f"'{' '.join(update_cmd)}' failed: {detail}"
            )
    except Exception as exc:  # noqa: BLE001 - certs are best-effort
        warning(f"Could not install certificates into '{container.name}': {exc}")
