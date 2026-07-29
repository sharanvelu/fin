"""Plugin registry — SQLite-cached metadata over the directory-grouped plugs.

The directory layout (``Plugs/App|Asset|Global``) is the source of truth; this
SQLite cache (``~/.fin/registry.db``) lets Fin answer "what plugs exist and of
what type" without importing every plug on every invocation.

The registry also backs the ``fin plugs`` commands:
    list / info / search / install / uninstall

``search`` and ``install`` talk to a remote catalog whose concrete logic is a
later milestone; the methods here define the interface and a local-first
fallback.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fincli.config import Config
from fincli.core.errors import FinError, NotFound
from fincli.plugs.loader import load_all


@dataclass
class PlugRecord:
    """A registry row describing an installed plug."""

    name: str
    version: str
    plug_type: str
    description: str
    commands: str  # comma-separated
    path: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS plugs (
    name        TEXT PRIMARY KEY,
    version     TEXT NOT NULL,
    plug_type   TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    commands    TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL
);
"""


class Registry:
    """SQLite-backed registry of installed plugs."""

    def __init__(self, db_path: Path | None = None):
        Config.ensure_dirs()
        self.db_path = db_path or Config.REGISTRY_DB
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- sync ---------------------------------------------------------------
    def sync(self) -> int:
        """Re-scan the plugs directory and refresh the cache.

        Returns the number of plugs recorded. Loading is graceful: failed
        plugs are simply absent from the cache.
        """
        loaded = load_all()
        self._conn.execute("DELETE FROM plugs")
        for lp in loaded:
            info = lp.instance.info()
            self._conn.execute(
                "INSERT OR REPLACE INTO plugs "
                "(name, version, plug_type, description, commands, path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    info["name"] or lp.path.name,
                    info["version"],
                    info["type"],
                    info["description"],
                    ",".join(info["commands"]),
                    str(lp.path),
                ),
            )
        self._conn.commit()
        return len(loaded)

    # --- queries ------------------------------------------------------------
    def all(self, *, refresh: bool = True) -> list[PlugRecord]:
        if refresh:
            self.sync()
        rows = self._conn.execute(
            "SELECT * FROM plugs ORDER BY plug_type, name"
        ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, name: str, *, refresh: bool = True) -> PlugRecord:
        if refresh:
            self.sync()
        row = self._conn.execute(
            "SELECT * FROM plugs WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise NotFound(f"Plug '{name}' is not installed.")
        return self._row(row)

    def by_type(self, plug_type: str, *, refresh: bool = True) -> list[PlugRecord]:
        if refresh:
            self.sync()
        rows = self._conn.execute(
            "SELECT * FROM plugs WHERE plug_type = ? ORDER BY name",
            (plug_type.upper(),),
        ).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> PlugRecord:
        return PlugRecord(
            name=row["name"],
            version=row["version"],
            plug_type=row["plug_type"],
            description=row["description"],
            commands=row["commands"],
            path=row["path"],
        )

    # --- catalog operations (remote logic deferred) -------------------------
    def search(self, query: str) -> list[dict]:
        """Search the remote plug catalog.

        Catalog logic is a later milestone. For now this raises a clear,
        non-crashing message so the command surface exists and is testable.
        """
        raise FinError(
            f"Plug catalog search for '{query}' is not yet available — "
            "the remote catalog will be wired up in a later release.",
            title="Not Implemented",
        )

    def install(self, name: str, *, repo_url: str | None = None) -> Path:
        """Install a plug into the correct type directory.

        If *repo_url* is given (or *name* looks like a git URL), clone it;
        otherwise defer to the (not-yet-available) catalog. The destination
        type sub-directory is decided after a successful clone by reading the
        plug's declared type.
        """
        url = repo_url or (name if _looks_like_git(name) else None)
        if url is None:
            raise FinError(
                f"Don't know where to fetch plug '{name}'. Provide a git URL, "
                "or wait for the catalog (coming in a later release).",
                title="Not Implemented",
            )
        if shutil.which("git") is None:
            raise FinError("git is required to install plugs but was not found.")

        # Clone into a staging dir under App/ first, then relocate by type.
        Config.ensure_dirs()
        staging_parent = Config.plug_type_dir("APP")
        staging_parent.mkdir(parents=True, exist_ok=True)
        dest = staging_parent / _repo_basename(url)
        if dest.exists():
            raise FinError(f"Plug directory already exists: {dest}")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(dest)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise FinError(f"git clone failed: {exc.stderr.strip()}") from exc

        # Relocate to the correct type dir based on the plug's declared type.
        from fincli.plugs.loader import load_plug_dir
        from fincli.plugs.base import PlugType

        lp = load_plug_dir(dest, PlugType.APP)
        if lp is not None and lp.instance.plug_type != PlugType.APP:
            correct_dir = Config.plug_type_dir(lp.instance.plug_type.value)
            correct_dir.mkdir(parents=True, exist_ok=True)
            final = correct_dir / dest.name
            shutil.move(str(dest), str(final))
            dest = final

        self.sync()
        return dest

    def uninstall(self, name: str) -> Path:
        """Remove an installed plug's directory from disk."""
        record = self.get(name)
        path = Path(record.path)
        if not path.exists():
            raise NotFound(f"Plug '{name}' directory not found at {path}.")
        shutil.rmtree(path)
        self.sync()
        return path


def _looks_like_git(value: str) -> bool:
    return value.startswith(
        ("http://", "https://", "git@", "ssh://")
    ) or value.endswith(".git")


def _repo_basename(url: str) -> str:
    base = url.rstrip("/").split("/")[-1]
    return base[:-4] if base.endswith(".git") else base
