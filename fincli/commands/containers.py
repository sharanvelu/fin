"""Container inspection commands: ps/status, exec, inspect, logs.

All operate only on Fin-managed containers (filtered by the FIN_MANAGED label).
``exec``/``inspect``/``logs`` default to the *current project's* primary
container when no explicit name is given.
"""

from __future__ import annotations

import json

from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands import reserved
from fincli.core.containers import find_container, find_primary, list_containers
from fincli.core.env import ProjectEnv
from fincli.ui.console import console, error, info
from fincli.ui.spinners import fin_spinner
from fincli.ui.tables import render_grouped_containers


def _read_stats(containers) -> dict[str, dict[str, str]]:
    """Best-effort single-shot CPU%/Mem for running containers."""
    stats: dict[str, dict[str, str]] = {}
    for c in containers:
        if c.status != "running":
            continue
        try:
            s = c.stats(stream=False)
            stats[c.id] = {"cpu": _cpu_percent(s), "mem": _mem_usage(s)}
        except Exception:  # noqa: BLE001 - stats are non-essential
            continue
    return stats


def _cpu_percent(s: dict) -> str:
    try:
        cpu = s["cpu_stats"]; pre = s["precpu_stats"]
        cpu_delta = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        sys_delta = cpu["system_cpu_usage"] - pre.get("system_cpu_usage", 0)
        ncpus = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or [1])
        if sys_delta > 0 and cpu_delta > 0:
            return f"{(cpu_delta / sys_delta) * ncpus * 100:.1f}"
    except (KeyError, TypeError, ZeroDivisionError):
        pass
    return "-"


def _mem_usage(s: dict) -> str:
    try:
        usage = s["memory_stats"]["usage"]
        for unit in ("B", "KB", "MB", "GB"):
            if usage < 1024:
                return f"{usage:.0f}{unit}"
            usage /= 1024
        return f"{usage:.0f}TB"
    except (KeyError, TypeError):
        return "-"


@reserved(
    "ps",
    help="List Fin containers (-a for all, -s for CPU/Mem stats).",
    aliases=("status", "containers"),
    group="Containers",
    usage="fin ps [-a] [-s]",
    options=(
        ("-a, --all", "Include stopped containers, not just running ones."),
        ("-s, --stats", "Collect and show live CPU% and Mem."),
    ),
    examples=("fin ps", "fin ps -a", "fin ps -s"),
)
def ps(args: list[str]) -> int:
    show_all = "-a" in args or "--all" in args
    with_stats = "-s" in args or "--stats" in args
    label = "all" if show_all else "running"
    spinner_msg = (
        f"Getting {label} containers (with stats)..."
        if with_stats
        else f"Getting {label} containers..."
    )
    with fin_spinner(spinner_msg):
        containers = list_containers(all_=show_all)
        if not containers:
            info("No Fin containers." + ("" if show_all else " (try 'fin ps -a')"))
            return EXIT_OK
        # Stats are only collected (and the CPU%/Mem columns only shown) when
        # -s/--stats is given — the per-container stats call is slow.
        stats = _read_stats(containers) if with_stats else None
        grouped_containers = render_grouped_containers(containers, stats=stats)

    console.print(grouped_containers)
    return EXIT_OK


@reserved(
    "exec",
    help="Exec a command in the current project's primary container.",
    group="Containers",
    usage="fin exec <command> [args...]",
    examples=("fin exec php -v", "fin exec ls -la"),
)
def exec_cmd(args: list[str]) -> int:
    if not args:
        error("Usage: fin exec <command> [args...]", title="Invalid Argument")
        return EXIT_USER
    env = ProjectEnv.load()
    container = find_primary(env.project_name)
    if container.status != "running":
        error(f"'{container.name}' is not running. Run 'fin up' first.", title="Not Running")
        return EXIT_USER
    # Run through the interactive helper: when fin is attached to a real TTY it
    # gives commands like `fin exec sh` / `fin exec bash` a proper session
    # (stdin attached, `exit` works); otherwise it transparently streams output.
    from fincli.core.interactive import interactive_exec

    return interactive_exec(container, args)


@reserved(
    "inspect",
    help="Show rich JSON inspect for a container (default: primary).",
    group="Containers",
    usage="fin inspect [container]",
    examples=("fin inspect", "fin inspect fin_mysql"),
)
def inspect(args: list[str]) -> int:
    env = ProjectEnv.load()
    if args and not args[0].startswith("-"):
        container = find_container(args[0])
    else:
        container = find_primary(env.project_name)
    console.print_json(json.dumps(container.attrs, default=str))
    return EXIT_OK


@reserved(
    "logs",
    help="Tail logs (--follow, --tail N, --since X). Default: primary.",
    group="Containers",
    usage="fin logs [container] [--follow] [--tail N] [--since X]",
    options=(
        ("--follow, -f", "Stream new log lines as they arrive."),
        ("--tail N", "Show only the last N lines."),
        ("--since X", "Show logs since a timestamp or relative time."),
    ),
    examples=("fin logs", "fin logs --follow", "fin logs myapp-web --tail 100"),
)
def logs(args: list[str]) -> int:
    env = ProjectEnv.load()
    follow = "--follow" in args or "-f" in args
    tail = "all"
    since = None
    name = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--tail" and i + 1 < len(args):
            tail = args[i + 1]; i += 2; continue
        if a == "--since" and i + 1 < len(args):
            since = args[i + 1]; i += 2; continue
        if not a.startswith("-") and name is None:
            name = a
        i += 1

    container = find_container(name) if name else find_primary(env.project_name)

    kwargs = {"stream": follow, "follow": follow, "tail": int(tail) if str(tail).isdigit() else "all"}
    if since:
        kwargs["since"] = since

    if follow:
        for line in container.logs(**kwargs):
            console.file.write(line.decode("utf-8", errors="replace"))
            console.file.flush()
    else:
        out = container.logs(**{k: v for k, v in kwargs.items() if k != "stream"})
        console.file.write(out.decode("utf-8", errors="replace"))
        console.file.flush()
    return EXIT_OK
