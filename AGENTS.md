# AGENTS.md — working in the Fin codebase

Guide for AI coding agents. Read [DESIGN.md](DESIGN.md) for the full
architecture and [README.md](README.md) for user-facing behaviour.

## What Fin is

Fin (`fincli` package) is a Python 3.11+ CLI that runs local-dev Docker
containers. Apps and services are **plugs** — declarative classes that describe
containers and contribute commands. A built-in Traefik proxy routes web
containers by hostname.

## Project layout

```
fin                       bash launcher (source/dev path; sets PYTHONPATH, execs python -m fincli)
install.sh                installer for END USERS: downloads a prebuilt binary from Releases, symlinks it, creates ~/.fin/plugs
packaging/build.sh        builds the standalone binary (PyInstaller onedir) → dist/fin-<os>-<arch>.tar.gz
packaging/fin_entry.py    PyInstaller entry point (calls fincli.__main__:main)
.github/workflows/            CI: PR gates (tests, code-style, static-analysis, build-check, pr-title, dependency-review) + codeql, dependabot auto-merge, run cleanup, release (tag.yml → build.yml); see .github/CI.md
pyproject.toml            packaging; [project.scripts] fin = fincli.__main__:main; deps: typer, rich, docker; dev: pytest, pytest-mock, pytest-cov + pinned ruff/mypy
fincli/
  __main__.py             entrypoint + argv dispatch (main())
  resolver.py             reserved → FIN_APP → FIN_PLUGS → GLOBAL
  help.py                 command overview + per-command help pages
  app.py                  App singleton; EXIT_OK/EXIT_USER/EXIT_SYSTEM
  config.py               Config: paths, network, label keys, asset creds, catalog URLs (read from env)
  core/
    docker_client.py      DockerService singleton + get_docker()
    env.py                ProjectEnv, EnvSpec/EnvVar validation
    containers.py         labels, traefik labels, run_container, lookup
    orchestrator.py       ContainerSpec → running container (the ONLY Docker mutator)
    proxy.py              built-in traefik:v3.6 (fin_proxy)
    database.py           auto-create DB_DATABASE in shared engine
    wait.py               engine readiness probes (mysql_ready, postgres_ready)
    interactive.py        TTY exec sessions (PlugContext.exec(interactive=True))
    certs.py              install ~/.fin/certs into opted-in containers
    store.py              ~/.fin/config.json asset enable flags
    errors.py             FinError + @handle_errors decorator
  ui/                     console, tables, spinners — the ONLY place that prints
  agents/                 `fin agents` content: per-agent instruction-file renderers + installer
  plugs/
    base.py               FinPlug, ContainerSpec, PlugCommand, PlugType
    loader.py             importlib discovery of flat PLUGS_DIR/<name>.py files
    registry.py           SQLite cache (~/.fin/registry.db) + install/uninstall/search ops
    catalog.py            remote fin-plugs catalog client (catalog.json + plug files over HTTPS)
    context.py            PlugContext.exec(...) inside primary container
  commands/               reserved system commands (@reserved decorator)
tests/                    pytest suite + conftest fixtures
```

At runtime plugs load from `PLUGS_DIR`, which is fixed at `~/.fin/plugs` (it moves
with `FIN_DATA_DIR`). Plug source is **not in this repo** — it lives in the
separate [fin-plugs](https://github.com/sharanvelu/fin-plugs) repo. Users install
plugs with `fin plugs install <name>`; for development, symlink that checkout's
`plugs/` dir there once: `ln -s <fin-plugs checkout>/plugs ~/.fin/plugs`. (This
keeps the tool binary/install immutable while plugs live in the writable user
data dir.)

## Conventions (do not violate)

- **All output goes through `fincli/ui`.** Use `success`/`error`/`warning`/
  `info`/`hint`/`confirm` from `fincli.ui.console`, or the Rich `console`.
  **Never call bare `print()` outside `fincli/ui`.** (`ui.console.print` is a
  deliberate Rich passthrough; that's the exception.)
- **Never call Docker except through core.** Use `get_docker().client`,
  `core/containers.py` helpers, the orchestrator, or `PlugContext.exec`. **No
  `subprocess` calls to the `docker` CLI** — use the Python SDK. (The one
  `subprocess` use in `registry.py` is for `git clone`, not Docker.)
- **Plugs are declarative.** A plug returns `ContainerSpec`/`PlugCommand` and
  asks `PlugContext` to exec. A plug must never import `docker` or call
  `run_container`. Only classes subclassing `FinPlug` are recognised.
- **No virtualenv.** In development, Fin runs against system Python with
  user-site packages. Do not add venv-creation steps or assume `.venv` (a stray
  `.venv/` is gitignored). (End users don't need Python at all — they get a
  PyInstaller binary that embeds its own interpreter; see `packaging/build.sh`.)
- **Errors render, never crash.** Raise `FinError` (or `DockerUnavailable`/
  `NotFound`) for expected failures; `@handle_errors` turns them into panels with
  the right exit code. Don't print tracebacks or `sys.exit()` raw integers from
  command bodies — return an exit code, or raise.
- **Exit codes:** `0` ok, `1` user error, `2` system/Docker error
  (`fincli.app.EXIT_OK/EXIT_USER/EXIT_SYSTEM`).
- Modules use `from __future__ import annotations`; imports of `docker` and Rich
  are often local to keep import-time light and tests hermetic.

## How to add a reserved (system) command

1. In a module under `fincli/commands/` (existing ones group by area), write a
   handler `def my_cmd(args: list[str]) -> int:` and decorate it:
   ```python
   from fincli.commands import reserved

   @reserved("mycmd", help="...", aliases=("mc",), group="Containers")
   def my_cmd(args: list[str]) -> int:
       ...
       return EXIT_OK
   ```
2. Ensure the module is imported by `load_reserved()` in
   `fincli/commands/__init__.py` (add it to the import list if it's a new module).
3. The command now wins over any plug command of the same name.

## How to add a plug (vs a command)

Add a plug when behaviour is app- or service-specific; add a reserved command
when it's a core Fin capability. To add a plug:

1. Create `<PLUGS_DIR>/<name>.py` with one class subclassing `FinPlug` (set
   `name`, `version`, `plug_type`, `description`). The declared `plug_type`
   decides whether it's APP/ASSET/GLOBAL — never the file's location.
2. APP plugs implement `primary_spec(env) -> ContainerSpec`; ASSET plugs
   implement `asset_specs(env) -> list[ContainerSpec]` with a fixed
   `container_name`. Add `commands()` returning `{name: PlugCommand(...)}`.
3. Declare requirements with `env_spec()` (see below). Handlers take
   `(ctx: PlugContext, args)` and call `ctx.exec([...], workdir=...)`.
4. To trust the user's CA certs (`~/.fin/certs`), set `install_certs=True` on the
   `ContainerSpec` (Debian defaults; override `cert_dir` / `cert_update_cmd` for
   other bases). The orchestrator installs them on every `fin up`.
5. `fin plugs list` re-syncs the SQLite registry from disk. See
   `plugs/laravel.py` and `plugs/mysql.py` in the fin-plugs repo for full
   examples.

## The env-spec validation pattern

`env.py` provides declarative validation. A plug or command builds an `EnvSpec`
and validates it; the user gets *all* problems at once:

```python
from fincli.core.env import EnvSpec, EnvVar

def env_spec(self) -> EnvSpec:
    return EnvSpec.of([
        EnvVar("FIN_SITE", required=True, description="hostname served at"),
        EnvVar("FIN_COMPOSER_VERSION", choices=("1", "2"), default="2"),
        EnvVar("SOME_PORT", value_type=int),
    ])

# in `fin up`: plug.env_spec().validate(env)   → raises one FinError listing
#              every failing variable as a bullet.
```

`EnvVar.check` validates required-ness, `choices`, and `value_type`
(`str`/`int`/`bool`). `EnvSpec.resolved(env)` returns values with defaults
applied. Use `as_bool(...)` for boolean env strings.

## Running tests

```bash
python3 -m pytest          # full suite (pyproject sets -q, testpaths=tests)
python3 -m pytest tests/test_orchestrator.py -k up    # focused run
```

Tests are hermetic: they never touch a real daemon, `~/.fin`, or any real
plugs directory. Key fixtures in `tests/conftest.py`:

- `mock_docker_client` — a `MagicMock` shaped like the docker SDK client
  (empty container/image/network lists, truthy `ping`, `containers.run`
  returning a fake container).
- `patch_docker` — patches `DockerService._create_client` so
  `get_docker().client` returns the mock; returns it for assertions.
- `make_fake_container` / `make_fake_image` (also as `fake_container` /
  `fake_image` fixtures) — build SDK-shaped mocks.
- `write_plug` / `plug_factory` — write a minimal flat `<name>.py` `FinPlug`
  file into a temp `PLUGS_DIR`.

## Gotchas

- **`DockerService` is a singleton.** A cached `_client` leaks across tests if not
  reset. The autouse `reset_docker_singleton` fixture clears
  `DockerService._instance`/`_client` before and after every test; `patch_docker`
  also resets `_instance`. If you instantiate `DockerService` directly in a test,
  expect the autouse fixture to clear it.
- **`Config` paths are read from env at class-definition (import) time.** Setting
  `FIN_DATA_DIR` *after* `fincli.config` is imported has no effect — tests
  `monkeypatch.setattr(Config, "DATA_DIR", ...)` instead (see the autouse
  `isolate_config` fixture, which also re-points `CONFIG_FILE`, `REGISTRY_DB`,
  and `PLUGS_DIR`).
- **`ProjectEnv` reads the real cwd.** `ProjectEnv.load()` parses `.env` from
  `Path.cwd()`; pass an explicit `cwd=` in tests. Process env (`FIN_*`,
  `DB_*`, `REDIS_*`) overrides the file.
- **Plug discovery scans flat `<name>.py` files** directly under PLUGS_DIR;
  the plug's declared `plug_type` decides its type. Only `FinPlug`
  subclasses defined in the module count. A broken plug warns and is skipped, it
  doesn't crash the run — so a "missing" plug is often an import error in a
  warning, not a hard failure.
- **`@handle_errors` raises `SystemExit`.** It catches `FinError` and Docker SDK
  exceptions; don't wrap command bodies in broad `except` that swallows
  `FinError` before it reaches the decorator.
