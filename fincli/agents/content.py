"""The canonical, agent-agnostic instruction content for a project.

One markdown body is built here from the project's resolved plugs;
``targets.py`` renders it into each agent's file format. The plug command
tables are generated from ``FinPlug.commands()`` metadata in resolution order
(``FIN_APP`` first, then ``FIN_PLUGS``), so the generated docs always match
what ``fin`` actually accepts in this project.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fincli.core.env import ProjectEnv
from fincli.plugs.loader import load_by_name


@dataclass
class CommandDoc:
    """One plug-contributed command, as documented to the agent."""

    name: str
    help: str
    plug: str


@dataclass
class AgentContent:
    """The rendered canonical content plus the pieces targets may need."""

    body: str
    description: str
    commands: list[CommandDoc] = field(default_factory=list)


#: Host-command equivalents shown as before → after examples, keyed by the fin
#: command that replaces them. Only rows whose fin command the project's plugs
#: actually contribute are rendered.
_HOST_EXAMPLES: dict[str, tuple[str, str]] = {
    "composer": ("composer install", "fin composer install"),
    "artisan": ("php artisan migrate", "fin artisan migrate"),
    "php": ("php -v", "fin php -v"),
    "npm": ("npm install", "fin npm install"),
    "yarn": ("yarn install", "fin yarn install"),
    "node": ("node script.js", "fin node script.js"),
    "manage": ("python manage.py migrate", "fin manage migrate"),
    "python": ("python script.py", "fin python script.py"),
    "pip": ("pip install -r requirements.txt", "fin pip install -r requirements.txt"),
}

#: Reserved commands worth teaching agents about, in display order.
_CORE_COMMAND_NAMES: tuple[str, ...] = ("up", "down", "stop", "ps", "exec", "logs")


def project_commands(env: ProjectEnv) -> list[CommandDoc]:
    """Collect plug-contributed commands in resolution order (FIN_APP first).

    Duplicate names keep the first occurrence, mirroring how the resolver
    dispatches. Plugs that fail to load are skipped (the loader already
    warned).
    """
    docs: list[CommandDoc] = []
    seen: set[str] = set()
    names: list[str] = []
    if env.app_plug:
        names.append(env.app_plug)
    names.extend(p for p in env.plugs if p not in names)
    for plug_name in names:
        lp = load_by_name(plug_name)
        if lp is None:
            continue
        for cmd in lp.instance.commands().values():
            if cmd.name in seen:
                continue
            seen.add(cmd.name)
            docs.append(CommandDoc(name=cmd.name, help=cmd.help, plug=lp.name))
    return docs


def _core_commands() -> list[tuple[str, str]]:
    """Return (usage, help) for the core reserved commands, from the registry."""
    # Local import: fincli.commands imports command modules that import this
    # package, so binding at call time keeps module import order simple.
    from fincli.commands import RESERVED_CANONICAL, load_reserved

    load_reserved()
    out: list[tuple[str, str]] = []
    for name in _CORE_COMMAND_NAMES:
        cmd = RESERVED_CANONICAL.get(name)
        if cmd is not None:
            out.append((cmd.usage or f"fin {name}", cmd.help))
    return out


def _cell(text: str) -> str:
    """Escape pipes so command usages like ``[asset|all]`` don't split cells."""
    return text.replace("|", "\\|")


def _table(header: tuple[str, str], rows: list[tuple[str, str]]) -> list[str]:
    lines = [f"| {header[0]} | {header[1]} |", "|---|---|"]
    lines.extend(f"| {_cell(left)} | {_cell(right)} |" for left, right in rows)
    return lines


def build_content(env: ProjectEnv) -> AgentContent:
    """Build the canonical instruction content for the project at *env*."""
    docs = project_commands(env)
    return AgentContent(
        body=_render_body(docs),
        description=_render_description(docs),
        commands=docs,
    )


def _render_description(docs: list[CommandDoc]) -> str:
    """One line telling an agent when these instructions apply."""
    base = (
        "Run project commands through the Fin CLI instead of directly on the "
        "host — this project's app runs in Docker containers managed by Fin "
        "(detect it via FIN_* variables in .env; if containers are down, run "
        "'fin up' first and wait for it to finish)."
    )
    names = [d.name for d in docs][:8]
    if names:
        return (
            f"{base} Use whenever running {', '.join(names)}, or any app or "
            "package-manager command in this repository."
        )
    return f"{base} Use whenever running any app or package-manager command in this repository."


def _render_body(docs: list[CommandDoc]) -> str:
    lines: list[str] = [
        "## Working in this Fin project",
        "",
        "This project's app runs inside Docker containers managed by the Fin "
        "CLI. App tooling (package managers, framework CLIs, language "
        "runtimes) is not wired to this project on the host — run every "
        "project command through `fin`, which executes it inside the right "
        "container.",
        "",
        "### Detect Fin and make sure it is running",
        "",
        "1. **Detect** — a project uses Fin when its `.env` contains `FIN_*` "
        "variables. `FIN_APP` (alias `FIN_PLUG`) names the app plug whose "
        "commands are listed below; `FIN_PLUGS` lists auxiliary plugs that "
        "may contribute more commands.",
        "2. **Check** — before the first project command, run `fin ps` to see "
        "whether this project's containers are running.",
        "3. **Start if down** — if the containers are not running, or any "
        "`fin` command fails because a container is down or missing, run "
        "`fin up` and wait for it to complete (it starts the proxy, the "
        "shared services, and the app container, and creates the database). "
        "Do not start containers with `docker` directly.",
        "4. **Run** — once `fin up` succeeds, run the required command "
        "through `fin` (tables below, or `fin exec <command…>`).",
    ]

    doc_names = {d.name for d in docs}
    examples = [ex for name, ex in _HOST_EXAMPLES.items() if name in doc_names]
    if examples:
        lines += ["", "### Instead of host commands, run", ""]
        lines += _table(
            ("Instead of", "Run"),
            [(f"`{host}`", f"`{fin}`") for host, fin in examples],
        )

    if docs:
        lines += ["", "### Commands provided by this project's Fin plugs", ""]
        lines += _table(
            ("Command", "What it does"),
            [(f"`fin {d.name} …`", d.help or "-") for d in docs],
        )

    core = _core_commands()
    if core:
        lines += ["", "### Core Fin commands", ""]
        lines += _table(
            ("Command", "What it does"),
            [(f"`{usage}`", help_ or "-") for usage, help_ in core],
        )

    lines += [
        "",
        "### Rules",
        "",
        "- Never run app or package-manager commands directly on the host.",
        "- Prefer the dedicated `fin <command>` when one exists (tables above).",
        "- If a `fin` command fails because the container is not running, run "
        "`fin up`, wait for it to finish, then re-run the command.",
        "- For anything else, run it inside the app container: `fin exec <command…>`.",
        "- Do not manage this project's containers with `docker` or `docker compose` "
        "directly — Fin owns them. Use `fin up` / `fin down`.",
        "- `fin <command> --help` shows usage for any command.",
    ]
    return "\n".join(lines) + "\n"
