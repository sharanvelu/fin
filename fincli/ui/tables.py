"""Pre-built Rich table factories for containers and images.

These keep table styling in one place so every command renders consistently.
Rows are status-coloured: green = running, red = exited/dead, yellow = paused/
restarting/created.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from rich.console import Group
from rich.rule import Rule
from rich.table import Table

from fincli.config import Config


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


def _parse_docker_time(value: str) -> datetime | None:
    """Parse a docker RFC3339 timestamp (e.g. ``StartedAt``) defensively.

    Returns ``None`` on any parsing failure (including the docker "zero time"
    ``0001-01-01T00:00:00Z`` used for never-started containers).
    """
    if not value or value.startswith("0001-01-01"):
        return None
    try:
        text = value.strip()
        # Trim fractional seconds to microsecond precision for fromisoformat.
        if "." in text:
            head, _, tail = text.partition(".")
            frac = ""
            tz = ""
            for ch in tail:
                if ch.isdigit():
                    frac += ch
                else:
                    tz = tail[len(frac):]
                    break
            text = head + "." + frac[:6] + tz
        text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _format_uptime(delta_seconds: float) -> str:
    """Render a coarse uptime like docker's ``Up 10 seconds`` / ``Up 3 hours``."""
    secs = int(delta_seconds)
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"Up {secs} second{'s' if secs != 1 else ''}"
    mins = secs // 60
    if mins < 60:
        return f"Up {mins} minute{'s' if mins != 1 else ''}"
    hours = mins // 60
    if hours < 24:
        return f"Up {hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"Up {days} day{'s' if days != 1 else ''}"


def uptime_status(container: Any) -> str:
    """Build a human status string from ``container.attrs['State']``.

    For a running container this is ``Up 10 seconds`` (computed from
    ``StartedAt``) plus a ``(health: ...)`` suffix when a Health block exists.
    On any error or when uptime cannot be computed it falls back to the
    capitalised ``State.Status``, or ``-`` if nothing is available.
    """
    try:
        state = (container.attrs or {}).get("State") or {}
    except Exception:
        return "-"
    if not isinstance(state, dict):
        return "-"

    fallback = (state.get("Status") or "").capitalize() or "-"

    base = fallback
    try:
        if (state.get("Status") or "").lower() == "running":
            started = _parse_docker_time(state.get("StartedAt", ""))
            if started is not None:
                now = datetime.now(timezone.utc)
                base = _format_uptime((now - started).total_seconds())
    except Exception:
        base = fallback

    try:
        health = state.get("Health")
        if isinstance(health, dict):
            hstatus = health.get("Status")
            if hstatus:
                base = f"{base} (health: {hstatus})"
    except Exception:
        pass

    return base or "-"


# --- grouping ---------------------------------------------------------------
#: Section order for grouped output: (header, predicate over FIN_TYPE value).
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("App Containers", "app"),
    ("Asset Containers", "asset"),
    ("Other Containers", "other"),
)


def _container_labels(container: Any) -> dict[str, str]:
    """Read a container's labels defensively."""
    try:
        return (container.attrs.get("Config", {}) or {}).get("Labels") or {}
    except Exception:
        return {}


def _section_key(container: Any) -> str:
    """Map a container to its section key: ``app`` / ``asset`` / ``other``."""
    fin_type = (_container_labels(container).get(Config.LABEL_TYPE) or "").lower()
    if fin_type == "app":
        return "app"
    if fin_type == "asset":
        return "asset"
    return "other"


#: Single source of truth for the grouped-table columns: (header, column kwargs).
_COLUMN_DEFS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("ID", {"style": "dim", "no_wrap": True}),
    ("Name", {"style": "bold"}),
    ("Service", {"style": "magenta"}),
    ("Site", {}),
    ("State", {}),
    ("Status", {}),
    ("Ports", {}),
    # ("CPU%", {"justify": "right"}),
    # ("Mem", {"justify": "right"}),
)


def _row_plain(container: Any, stats: dict[str, dict[str, str]] | None) -> list[str]:
    """Return the nine plain-text cell values for a container (no markup).

    The same plain values drive both width calculation and rendering; the State
    cell gets its colour applied via markup, so its visible width still matches.
    """
    labels = _container_labels(container)
    status = getattr(container, "status", "") or ""
    cpu = mem = "-"
    cid = getattr(container, "id", None)
    row_stats: dict[str, str] | None = None
    if stats and isinstance(cid, str):
        row_stats = stats.get(cid)
    if row_stats:
        cpu = row_stats.get("cpu", "-")
        mem = row_stats.get("mem", "-")
    return [
        getattr(container, "short_id", "") or "",
        getattr(container, "name", "") or "",
        labels.get(Config.LABEL_SERVICE, "-") or "-",
        labels.get(Config.LABEL_SITE, "-") or "-",
        status.capitalize() or "-",
        uptime_status(container),
        _ports_to_str(container),
        # cpu,
        # mem,
    ]


def _shared_column_widths(
    containers: list[Any], stats: dict[str, dict[str, str]] | None
) -> list[int]:
    """Max visible width per column across *all* containers (incl. headers).

    Applying one width per column to every section makes the grouped tables
    render with identical column — and therefore overall — widths, so they
    line up exactly.
    """
    widths = [len(header) for header, _ in _COLUMN_DEFS]
    for c in containers:
        for i, value in enumerate(_row_plain(c, stats)):
            widths[i] = max(widths[i], len(str(value)))
    return widths


def make_grouped_container_tables(
    containers: Iterable[Any],
    *,
    stats: dict[str, dict[str, str]] | None = None,
) -> list[tuple[str, Table]]:
    """Group *containers* by FIN_TYPE into ordered (header, Table) sections.

    Sections are returned in the order App, Asset, Other and only included
    when they contain at least one container. Each table carries the columns
    ID, Name, Service, Site, State, Status, Ports, CPU%, Mem — and every
    section shares one set of column widths so the tables align perfectly.
    """
    containers = list(containers)
    buckets: dict[str, list[Any]] = {"app": [], "asset": [], "other": []}
    for c in containers:
        buckets[_section_key(c)].append(c)

    widths = _shared_column_widths(containers, stats)

    sections: list[tuple[str, Table]] = []
    for header, key in _SECTIONS:
        members = buckets[key]
        if members:
            sections.append(
                (header, _build_container_table(members, stats=stats, widths=widths))
            )
    return sections


def render_grouped_containers(
    containers: Iterable[Any],
    *,
    stats: dict[str, dict[str, str]] | None = None,
) -> Group:
    """Return a Rich renderable: red section rules followed by their tables."""
    parts: list[Any] = []
    for header, table in make_grouped_container_tables(containers, stats=stats):
        parts.append(Rule(f"[bold red]{header}[/bold red]", style="red"))
        parts.append(table)
    return Group(*parts)


def _build_container_table(
    containers: Iterable[Any],
    *,
    stats: dict[str, dict[str, str]] | None = None,
    widths: list[int] | None = None,
) -> Table:
    """Build one grouped-section table.

    Columns: ID, Name, Service, Site, State, Status, Ports, CPU%, Mem. When
    *widths* is given, each column is pinned to that width so multiple section
    tables align; otherwise columns auto-size to their own content.
    """
    table = Table(header_style="bold cyan", expand=False)
    for i, (header, opts) in enumerate(_COLUMN_DEFS):
        col_opts = dict(opts)
        if widths is not None:
            col_opts["width"] = widths[i]
        table.add_column(header, **col_opts)

    for c in containers:
        values = _row_plain(c, stats)
        style = status_style(getattr(c, "status", "") or "")
        # Colour the State cell (index 4) without changing its visible width.
        values[4] = f"[{style}]{values[4]}[/{style}]"
        table.add_row(*values)
    return table


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
