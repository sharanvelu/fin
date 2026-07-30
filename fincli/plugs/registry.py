"""Plugin registry — SQLite-cached metadata over the installed plugs.

The plugs on disk (flat ``PLUGS_DIR/<name>.py`` files) are the source of
truth; this SQLite cache (``~/.fin/registry.db``) lets Fin answer "what plugs
exist and of what type" without importing every plug on every invocation.

The registry also backs the ``fin plugs`` commands:
    list / info / search / install / uninstall

``search`` and ``install`` talk to the remote catalog repo over plain HTTPS
(see :mod:`fincli.plugs.catalog`).
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
                    info["name"] or lp.path.stem,
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

    # --- catalog operations ---------------------------------------------------
    def search(self, query: str) -> list[dict]:
        """Search the remote plug catalog by name/description.

        Each returned entry is a catalog dict (name, type, version,
        description, commands, file) plus an ``installed`` flag comparing
        against the local registry.
        """
        from fincli.plugs import catalog

        results = catalog.search_catalog(query)
        installed = {r.name for r in self.all()}
        for entry in results:
            entry["installed"] = entry.get("name") in installed
        return results

    def install(self, name: str, *, repo_url: str | None = None) -> Path:
        """Install a single-file plug into ``PLUGS_DIR/<name>.py``.

        A plain name fetches the plug from the official catalog repo; a git
        URL clones the repo and installs the one plug file it contains.
        """
        url = repo_url or (name if _looks_like_git(name) else None)
        if url is None:
            return self._install_from_catalog(name)
        return self._install_from_git(url)

    def _install_from_catalog(self, name: str) -> Path:
        """Fetch ``plugs/<name>.py`` from the catalog repo into PLUGS_DIR."""
        from fincli.plugs import catalog

        catalog.validate_name(name)
        self._refuse_if_installed(name)
        source = catalog.fetch_plug_source(name)
        lp = self._validate_source(name, source)
        if lp.instance.name != name:
            raise FinError(
                f"The downloaded plug declares name '{lp.instance.name}', "
                f"expected '{name}' — refusing to install it.",
                title="Invalid Plug",
            )
        return self._place(name, source)

    def _install_from_git(self, url: str) -> Path:
        """Clone a plug repo and install the one ``<name>.py`` plug in it.

        Plug files are looked for in the clone's root and in its ``plugs/``
        sub-directory; the repo must contain exactly one loadable plug.
        """
        import tempfile

        from fincli.plugs import catalog
        from fincli.plugs.loader import load_plug_file

        if shutil.which("git") is None:
            raise FinError("git is required to install plugs but was not found.")

        with tempfile.TemporaryDirectory(prefix="fin-plug-git-") as tmp:
            clone = Path(tmp) / "repo"
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", url, str(clone)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise FinError(f"git clone failed: {exc.stderr.strip()}") from exc

            candidates = [
                py
                for base in (clone, clone / "plugs")
                if base.is_dir()
                for py in sorted(base.glob("*.py"))
                if not py.name.startswith((".", "_"))
            ]
            plugs = [lp for lp in map(load_plug_file, candidates) if lp is not None]
            if not plugs:
                raise FinError(
                    f"No loadable Fin plug found in {url} (looked for "
                    "<name>.py at the repo root and under plugs/).",
                    title="Invalid Plug",
                )
            if len(plugs) > 1:
                names = ", ".join(sorted(lp.instance.name for lp in plugs))
                raise FinError(
                    f"{url} contains multiple plugs ({names}) — install them "
                    "individually by name from the catalog instead.",
                    title="Invalid Plug",
                )
            lp = plugs[0]
            name = catalog.validate_name(lp.instance.name)
            self._refuse_if_installed(name)
            return self._place(name, lp.path.read_text(encoding="utf-8"))

    def _refuse_if_installed(self, name: str) -> None:
        """Raise FinError if *name* already exists on disk or in the cache."""
        dest = Config.PLUGS_DIR / f"{name}.py"
        existing = str(dest) if dest.exists() else None
        if existing is None:
            try:
                existing = self.get(name).path
            except NotFound:
                return
        raise FinError(
            f"Plug '{name}' is already installed at {existing}. "
            f"Run 'fin plugs uninstall {name}' first to reinstall."
        )

    @staticmethod
    def _validate_source(name: str, source: str):
        """Load *source* from a scratch dir; raise unless it is a real plug."""
        import tempfile

        from fincli.plugs.loader import load_plug_file

        with tempfile.TemporaryDirectory(prefix="fin-plug-") as tmp:
            staged = Path(tmp) / f"{name}.py"
            staged.write_text(source, encoding="utf-8")
            lp = load_plug_file(staged)
        if lp is None:
            raise FinError(
                f"The downloaded file for '{name}' is not a loadable Fin "
                "plug — refusing to install it.",
                title="Invalid Plug",
            )
        return lp

    def _place(self, name: str, source: str) -> Path:
        """Write the validated plug source to PLUGS_DIR and re-sync."""
        Config.ensure_dirs()
        Config.PLUGS_DIR.mkdir(parents=True, exist_ok=True)
        dest = Config.PLUGS_DIR / f"{name}.py"
        dest.write_text(source, encoding="utf-8")
        self.sync()
        return dest

    def uninstall(self, name: str) -> Path:
        """Remove an installed plug file from disk."""
        record = self.get(name)
        path = Path(record.path)
        if not path.is_file():
            raise NotFound(f"Plug '{name}' not found on disk at {path}.")
        path.unlink()
        self.sync()
        return path


def _looks_like_git(value: str) -> bool:
    return value.startswith(
        ("http://", "https://", "git@", "ssh://")
    ) or value.endswith(".git")
