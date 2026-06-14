"""Pre-built Rich table factories for containers and images.

These keep table styling in one place so every command renders consistently.
Rows are status-coloured: green = running, red = exited/dead, yellow = paused/
restarting/created.
"""

from __future__ import annotations

from typing import Any, Iterable

from rich.table import Table


# --- status colouring -------------------------------------------------------
_STATUS_STYLES = {
    "running": "green",
    "paused": "yellow",
    "restarting": "yellow",
    "created": "yellow",
    "exited": "red",
    "dead": "red",
    "removing": "red",
}


def status_style(status: str) -> str:
    """Return a Rich colour name for a container status string."""
    return _STATUS_STYLES.get((status or "").lower(), "white")


def _ports_to_str(container: Any) -> str:
    """Render a container's published ports compactly (e.g. ``8080->80``)."""
    try:
        ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    except Exception:
        return "-"
    parts: list[str] = []
    for container_port, bindings in ports.items():
        if not bindings:
            continue
        for b in bindings:
            host = b.get("HostPort", "")
            if host:
                parts.append(f"{host}->{container_port.split('/')[0]}")
    return ", ".join(sorted(set(parts))) or "-"


def make_container_table(
    containers: Iterable[Any],
    *,
    stats: dict[str, dict[str, str]] | None = None,
    title: str | None = None,
) -> Table:
    """Build a styled table of containers.

    Columns: ID, Name, Image, Service, Status, Ports, CPU%, Mem.

    *stats* optionally maps a container id to a dict with ``cpu`` and ``mem``
    strings; columns are shown as ``-`` when stats are unavailable.
    """
    table = Table(title=title, header_style="bold cyan", expand=False)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Image")
    table.add_column("Service", style="magenta")
    table.add_column("Status")
    table.add_column("Ports")
    table.add_column("CPU%", justify="right")
    table.add_column("Mem", justify="right")

    for c in containers:
        labels = (c.attrs.get("Config", {}) or {}).get("Labels") or {}
        service = labels.get("FIN_SERVICE", "-")
        status = getattr(c, "status", "") or ""
        style = status_style(status)
        image_tags = getattr(getattr(c, "image", None), "tags", None) or []
        image = image_tags[0] if image_tags else "-"
        cpu = mem = "-"
        if stats and c.id in stats:
            cpu = stats[c.id].get("cpu", "-")
            mem = stats[c.id].get("mem", "-")
        table.add_row(
            c.short_id,
            c.name,
            image,
            service,
            f"[{style}]{status}[/{style}]",
            _ports_to_str(c),
            cpu,
            mem,
        )
    return table


def make_image_table(images: Iterable[Any], *, title: str | None = None) -> Table:
    """Build a styled table of images.

    Columns: Repository, Tag, ID, Size, Created.
    """
    table = Table(title=title, header_style="bold cyan", expand=False)
    table.add_column("Repository", style="bold")
    table.add_column("Tag", style="magenta")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("Created")

    for img in images:
        tags = getattr(img, "tags", None) or ["<none>:<none>"]
        size = _human_size(img.attrs.get("Size", 0))
        created = (img.attrs.get("Created", "") or "")[:19].replace("T", " ")
        for tag in tags:
            repo, _, tagname = tag.rpartition(":")
            table.add_row(repo or "<none>", tagname or "<none>", img.short_id, size, created)
    return table


def _human_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable size."""
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"
