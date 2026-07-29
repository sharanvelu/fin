"""Auto-create the project database inside the running asset DB container.

On ``fin up`` Fin reads the project's ``DB_*`` env and, if the target database
does not yet exist in the shared engine, creates it. Only MySQL and Postgres
are handled; other ``DB_CONNECTION`` values are skipped silently.

The create runs *inside* the asset container via ``exec_run`` (no host DB
client needed), using the asset credentials from :class:`Config`.
"""

from __future__ import annotations

from fincli.config import Config
from fincli.core.containers import find_container
from fincli.core.env import ProjectEnv
from fincli.core.wait import mysql_ready, postgres_ready, wait_for_ready
from fincli.ui.console import info, success, warning

# DB_CONNECTION values mapped to the asset container that serves them.
_MYSQL_CONNS = {"mysql", "mariadb"}
_PGSQL_CONNS = {"pgsql", "postgres", "postgresql"}


def ensure_project_database(env: ProjectEnv) -> None:
    """Create ``DB_DATABASE`` in the relevant engine if it's missing."""
    connection = (env.get("DB_CONNECTION") or "").lower()
    database = env.get("DB_DATABASE")

    if not database:
        return  # nothing to create
    if connection in _MYSQL_CONNS:
        _ensure_mysql_database(database)
    elif connection in _PGSQL_CONNS:
        _ensure_postgres_database(database)
    # Other connections (sqlite, etc.) need no shared-container action.


def _container_or_warn(name: str, engine: str):
    try:
        container = find_container(name)
    except Exception:
        warning(
            f"{engine} asset container '{name}' is not running; skipping DB creation."
        )
        return None
    if container.status != "running":
        warning(
            f"{engine} asset container '{name}' is not running; skipping DB creation."
        )
        return None
    return container


def _ensure_mysql_database(database: str) -> None:
    container = _container_or_warn("fin_mysql", "MySQL")
    if container is None:
        return
    # A freshly-started engine reports "running" before it accepts connections.
    # Wait for it to answer a ping; skip gracefully (no raise) if it never does.
    if not wait_for_ready(container, check=mysql_ready, description="MySQL"):
        warning(
            f"MySQL is not accepting connections yet; "
            f"skipping creation of database '{database}'."
        )
        return
    sql = (
        f"CREATE DATABASE IF NOT EXISTS `{database}`; "
        f"GRANT ALL PRIVILEGES ON *.* "
        f"TO '{Config.ASSET_USERNAME}'@'%'; FLUSH PRIVILEGES;"
    )
    # Pass argv directly (no `sh -c`) so backticks in the SQL are NOT treated
    # as shell command substitution. The password goes via the exec env.
    result = container.exec_run(
        ["mysql", "-u", "root", "-e", sql],
        demux=False,
        environment={"MYSQL_PWD": Config.ASSET_PASSWORD},
    )
    if result.exit_code == 0:
        success(f"Database [bold]{database}[/bold] is ready [dim](MySQL)[/dim]")
    else:
        warning(
            f"Could not ensure MySQL database '{database}': "
            f"{result.output.decode('utf-8', 'replace').strip()}"
        )


def _ensure_postgres_database(database: str) -> None:
    container = _container_or_warn("fin_postgres", "Postgres")
    if container is None:
        return
    if not wait_for_ready(container, check=postgres_ready, description="Postgres"):
        warning(
            f"Postgres is not accepting connections yet; "
            f"skipping creation of database '{database}'."
        )
        return
    # Postgres has no CREATE DATABASE IF NOT EXISTS; guard with a check.
    check = f"SELECT 1 FROM pg_database WHERE datname = '{database}'"
    exists = container.exec_run(
        [
            "psql",
            "-U",
            Config.ASSET_USERNAME,
            "-tAc",
            check,
            Config.ASSET_DEFAULT_DATABASE,
        ],
        demux=False,
    )
    if exists.exit_code == 0 and b"1" in (exists.output or b""):
        info(f"Database [bold]{database}[/bold] already exists (Postgres).")
        return
    create = container.exec_run(
        [
            "psql",
            "-U",
            Config.ASSET_USERNAME,
            "-d",
            Config.ASSET_DEFAULT_DATABASE,
            "-c",
            f'CREATE DATABASE "{database}"',
        ],
        demux=False,
    )
    if create.exit_code == 0:
        success(f"Database [bold]{database}[/bold] created (Postgres).")
    else:
        warning(
            f"Could not create Postgres database '{database}': "
            f"{create.output.decode('utf-8', 'replace').strip()}"
        )
