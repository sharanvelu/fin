"""Project environment loading and FIN_* validation.

``fin`` reads the ``.env`` file in the directory the user invoked it from and
exposes the ``FIN_``-prefixed variables (plus the standard Laravel ``DB_*`` /
``REDIS_*`` vars that asset wiring needs).

Two things live here:

* :class:`ProjectEnv` — a thin, parsed view of the current project's env and
  working directory.
* :class:`EnvSpec` / :class:`EnvVar` — a declarative way for each command (and
  plug) to state which env vars it requires, their supported values, and types,
  with a single :meth:`EnvSpec.validate` that raises a friendly error listing
  every problem at once.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from fincli.core.errors import FinError

FIN_PREFIX = "FIN_"


# --------------------------------------------------------------------------- #
# .env parsing
# --------------------------------------------------------------------------- #
def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``.env`` file into a dict.

    Supports ``KEY=value``, ``export KEY=value``, ``#`` comments, blank lines,
    and surrounding single/double quotes. Values are returned verbatim
    otherwise (no variable interpolation — matching dotenv's simple mode).
    """
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip a single layer of matching quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            result[key] = value
    return result


@dataclass
class ProjectEnv:
    """Parsed view of the current project's environment.

    Attributes:
        cwd: The directory ``fin`` was invoked from (the project root).
        values: Merged env values — ``.env`` file overlaid by ``FIN_*``,
            ``DB_*`` and ``REDIS_*`` process env vars (those win, so
            ``FIN_SITE=… fin up`` works; other process vars are not overlaid).
    """

    cwd: Path
    values: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, cwd: Path | None = None) -> "ProjectEnv":
        """Load ``.env`` from *cwd* (defaults to the real current directory)."""
        cwd = (cwd or Path.cwd()).resolve()
        merged = parse_env_file(cwd / ".env")
        # FIN_*/DB_*/REDIS_*-prefixed process vars take precedence over .env.
        for k, v in os.environ.items():
            if k.startswith(FIN_PREFIX) or k.startswith(("DB_", "REDIS_")):
                merged[k] = v
        return cls(cwd=cwd, values=merged)

    # --- accessors ----------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def require(self, key: str) -> str:
        """Return a value or raise a :class:`FinError` if missing/empty."""
        val = self.values.get(key)
        if not val:
            raise FinError(
                f"Required environment variable [bold]{key}[/bold] is not set "
                f"in {self.cwd / '.env'}."
            )
        return val

    def fin_vars(self) -> dict[str, str]:
        """Return only the ``FIN_``-prefixed variables."""
        return {k: v for k, v in self.values.items() if k.startswith(FIN_PREFIX)}

    @property
    def project_name(self) -> str:
        """Container-safe project name derived from the cwd basename.

        Lowercased, spaces → hyphens. ``FIN_CONTAINER_NAME`` overrides it.
        """
        override = self.values.get("FIN_CONTAINER_NAME")
        base = override or self.cwd.name
        return base.strip().lower().replace(" ", "-")

    @property
    def plugs(self) -> list[str]:
        """The comma-separated ``FIN_PLUGS`` list (auxiliary plugs)."""
        raw = self.values.get("FIN_PLUGS", "")
        return [p.strip() for p in raw.split(",") if p.strip()]

    @property
    def app_plug(self) -> str | None:
        """The primary app plug name from ``FIN_APP`` (a.k.a. ``FIN_PLUG``)."""
        return self.values.get("FIN_APP") or self.values.get("FIN_PLUG")

    @property
    def additional_hosts(self) -> list[str]:
        """The comma-separated ``FIN_ADDITIONAL_HOSTS`` list.

        Extra hosts routed to the primary container alongside ``FIN_SITE``
        (which stays required for routing — these only add to it).
        """
        raw = self.values.get("FIN_ADDITIONAL_HOSTS", "")
        return [d.strip() for d in raw.split(",") if d.strip()]


# --------------------------------------------------------------------------- #
# Declarative env specs (per-command / per-plug requirements)
# --------------------------------------------------------------------------- #
@dataclass
class EnvVar:
    """Declares a single environment variable requirement.

    Args:
        name: The variable name (e.g. ``FIN_SITE``).
        required: Whether the variable must be present and non-empty.
        choices: Optional whitelist of accepted values.
        value_type: Optional type for coercion/validation — ``str``, ``int``,
            or ``bool`` (``0/1/true/false/yes/no``).
        default: Value used when not set (only for non-required vars).
        description: Human-readable purpose, shown in errors and help.
    """

    name: str
    required: bool = False
    choices: Sequence[str] | None = None
    value_type: type = str
    default: str | None = None
    description: str = ""

    def check(self, raw: str | None) -> str | None:
        """Validate a raw value; return an error string or None if OK."""
        if raw is None or raw == "":
            if self.required:
                return f"[bold]{self.name}[/bold] is required" + (
                    f" — {self.description}" if self.description else ""
                )
            return None
        if self.choices and raw not in self.choices:
            allowed = ", ".join(self.choices)
            return f"[bold]{self.name}[/bold]={raw!r} is invalid (allowed: {allowed})"
        if self.value_type is int:
            try:
                int(raw)
            except ValueError:
                return f"[bold]{self.name}[/bold]={raw!r} must be an integer"
        elif self.value_type is bool:
            if raw.lower() not in _BOOL_TRUE | _BOOL_FALSE:
                return f"[bold]{self.name}[/bold]={raw!r} must be a boolean (0/1/true/false)"
        return None


_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


def as_bool(raw: str | None, default: bool = False) -> bool:
    """Interpret an env string as a boolean."""
    if raw is None:
        return default
    return raw.strip().lower() in _BOOL_TRUE


@dataclass
class EnvSpec:
    """A collection of :class:`EnvVar` requirements for a command or plug."""

    variables: list[EnvVar] = field(default_factory=list)

    def add(self, *vars_: EnvVar) -> "EnvSpec":
        self.variables.extend(vars_)
        return self

    def validate(self, env: ProjectEnv | Mapping[str, str]) -> None:
        """Validate *env* against all declared variables.

        Collects *all* problems and raises a single :class:`FinError` listing
        them, so the user can fix everything in one pass.
        """
        values = env.values if isinstance(env, ProjectEnv) else dict(env)
        problems: list[str] = []
        for var in self.variables:
            err = var.check(values.get(var.name))
            if err:
                problems.append(err)
        if problems:
            bullet = "\n".join(f"  • {p}" for p in problems)
            raise FinError(
                "Environment validation failed:\n" + bullet,
                title="Invalid Configuration",
            )

    def resolved(self, env: ProjectEnv | Mapping[str, str]) -> dict[str, str]:
        """Return values with defaults applied (after a successful validate)."""
        values = env.values if isinstance(env, ProjectEnv) else dict(env)
        out: dict[str, str] = {}
        for var in self.variables:
            val = values.get(var.name)
            if (val is None or val == "") and var.default is not None:
                val = var.default
            if val is not None:
                out[var.name] = val
        return out

    @classmethod
    def of(cls, variables: Iterable[EnvVar]) -> "EnvSpec":
        return cls(list(variables))
