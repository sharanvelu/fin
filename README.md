# Fin

> Run local dev containers, infinitely extensible via plugs.

**Fin** is a fast, opinionated, plugin-driven CLI for running local-development
Docker containers. Point it at a project, declare a few `FIN_*` variables in your
`.env`, and `fin up` brings up everything that project needs — a routing proxy,
shared databases/caches, and your application container — all on one Docker
network, all reachable by friendly `*.localhost` hostnames.

Fin is the superhero successor to [DockR](https://dockr.in): same muscle memory,
a declarative plugin system, and a single audited path to the Docker daemon.

---

## Table of contents

- [Highlights](#highlights)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [Quickstart (Laravel)](#quickstart-laravel)
- [Command reference](#command-reference)
- [Environment variables](#environment-variables)
- [How it works](#how-it-works)
- [Writing a plug](#writing-a-plug)
- [Building a release](#building-a-release)
- [Troubleshooting](#troubleshooting)
- [Credits](#credits)

---

## Highlights

- **One command up.** `fin up` ensures the proxy, starts enabled shared assets,
  starts your app container, and creates the project database — idempotently.
- **Plugin-driven (plugs).** Apps and services are *plugs*: small declarative
  Python classes that describe containers and contribute commands. Catalog plugs
  cover Laravel, Django, MySQL, PostgreSQL, Redis and MinIO
  (`fin plugs install <name>`); you can write your own. See the official
  [fin-plugs catalog](https://github.com/sharanvelu/fin-plugs) — or run
  `fin plugs search` — for the full, up-to-date list.
- **Automatic routing.** A built-in Traefik proxy routes web-exposed containers
  by hostname (`Host(...)` / wildcard `HostRegexp`) — no port juggling.
- **Shared assets.** One MySQL/Postgres/Redis/MinIO container is shared across
  every project, so multiple apps reuse the same database server.
- **Friendly errors.** No raw tracebacks — Docker problems render as clean Rich
  panels with meaningful exit codes.
- **No Python on the host.** The published Fin is a **prebuilt, standalone
  binary** that embeds its own Python interpreter and `fincli` — you just need
  Docker at runtime. (Developing from source still runs against system Python
  3.11+ with `--user` packages; see [Install from source](#install-from-source-developers).)

## Prerequisites

- **Docker** running locally (Docker Desktop, Colima, Rancher Desktop, or Podman
  with a Docker-compatible socket — Fin auto-detects the common socket paths).
- **git** — used by `fin plugs install <git-url>`. (Optional: catalog installs
  like `fin plugs install laravel` fetch over plain HTTPS and need no git.)

> The prebuilt binary needs **no Python, pip, or virtualenv** on the host.
> Python 3.11+ is only required if you install [from source](#install-from-source-developers).

## Install

Fin ships as a prebuilt, standalone binary per OS/arch. The installer puts the
**binary on your `PATH`**; plugs are installed separately with
`fin plugs install <name>`.

### One-liner (prebuilt binary)

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/sharanvelu/fin/master/install.sh)"
```

The installer:

1. Detects your OS/arch and downloads the matching release tarball
   `fin-<os>-<arch>.tar.gz` (`os` ∈ `macos`/`linux`, `arch` ∈ `arm64`/`x64`)
   from the GitHub Releases of `sharanvelu/fin`.
2. Unpacks it into `~/.local/lib/fin-cli` (created if missing; override with
   `FIN_HOME_DIR`), giving the `~/.local/lib/fin-cli/fin` executable plus its
   `_internal/` runtime. The whole install is user-local — the installer
   never uses `sudo`.
3. Symlinks the `fin` launcher into the first writable directory on your `PATH`
   (tries `/usr/local/bin`, `~/.local/bin`, `~/bin`, `~/.bin`; override with
   `FIN_BIN_DIR`).
4. On macOS, strips the `com.apple.quarantine` attribute so the unsigned binary
   runs without a Gatekeeper prompt.
5. Runs `fin --version` once — the first launch of the unsigned binary is slow
   (~15s while the OS verifies it), so the installer pays that cost up front
   and your first real `fin` command starts instantly.
6. Creates the plugs directory at `~/.fin/plugs` (override with
   `FIN_DATA_DIR`). Plugs themselves are not bundled — install them with
   `fin plugs install <name>`.

Installer environment overrides:

| Variable           | Purpose                                     | Default                            |
| ------------------ | ------------------------------------------- | ---------------------------------- |
| `FIN_VERSION`      | release to install — `latest` = the newest published release (GitHub's `releases/latest` redirect); a version like `0.1.0` pins the immutable `v0.1.0` release | `latest`                         |
| `FIN_HOME_DIR`     | binary install location                     | `$HOME/.local/lib/fin-cli`         |
| `FIN_BIN_DIR`      | where to place the `fin` symlink            | auto-detected writable `PATH` dir  |
| `FIN_DATA_DIR`     | per-user data dir (config, registry, plugs) | `$HOME/.fin`                       |
| `FIN_RELEASE_REPO` | GitHub repo hosting the releases            | `sharanvelu/fin`                   |

### Manual download from Releases

If you'd rather not pipe a script, grab the tarball for your platform from the
[Releases page](https://github.com/sharanvelu/fin/releases) and place it yourself:

```bash
# Pick the artifact for your platform, e.g. fin-macos-arm64.tar.gz
mkdir -p ~/.local/lib/fin-cli ~/.local/bin
tar -C ~/.local/lib/fin-cli --strip-components=1 \
    -xzf fin-macos-arm64.tar.gz                             # → fin + _internal/
xattr -dr com.apple.quarantine ~/.local/lib/fin-cli         # macOS only (unsigned binary)
ln -sf ~/.local/lib/fin-cli/fin ~/.local/bin/fin            # or any writable dir on your PATH

# Install the plugs you need (not bundled in the binary):
fin plugs install laravel

fin --help
```

### Install from source (developers)

Working on Fin itself (or on a plug) uses the Python source path — no prebuilt
binary. This needs **Python 3.11+** on your `PATH`.

```bash
git clone https://github.com/sharanvelu/fin.git
cd fin
python3 -m pip install --user typer rich docker   # runtime deps, no virtualenv

# Then either run the module directly…
python3 -m fincli --help

# …or install the `fin` console script (editable), from pyproject's [project.scripts]:
python3 -m pip install --user -e .
fin --help
```

The repo also ships a `fin` bash launcher at its root: it resolves its own real
location (following symlinks), puts the Fin package on `PYTHONPATH`, and runs
`python3 -m fincli` **from the directory you invoked it in** — so the project's
`.env` and bind mounts work correctly. Symlink it onto your `PATH` if you prefer
it to the console script:

```bash
ln -sf "$PWD/fin" /usr/local/bin/fin
```

For development, plugs still load from the fixed `~/.fin/plugs` directory
(`PLUGS_DIR` is not configurable independently of `FIN_DATA_DIR`). Point it at
your plugs checkout once:

```bash
ln -s <fin-plugs repo>/plugs ~/.fin/plugs
```

## Quickstart (Laravel)

From inside a Laravel project, create or edit `.env`:

```dotenv
# Tell Fin which app plug runs this project, and where to serve it.
FIN_APP=laravel
FIN_SITE=myapp.localhost
FIN_PHP_VERSION=8.3
FIN_COMPOSER_VERSION=2

# Auxiliary plugs to bring up with this project.
FIN_PLUGS=mysql,redis

# Standard Laravel DB config — Fin auto-creates the database in the shared engine.
DB_CONNECTION=mysql
DB_HOST=fin_mysql
DB_PORT=3306
DB_DATABASE=myapp
DB_USERNAME=fin
DB_PASSWORD=password

REDIS_HOST=fin_redis
```

Then:

```bash
fin up
```

Fin starts the Traefik proxy, the shared `fin_mysql` and `fin_redis` containers,
your Laravel container, creates the `myapp` database if it's missing, and prints:

```
✓ myapp is up at http://myapp.localhost
```

Run Laravel tooling inside the container:

```bash
fin artisan migrate
fin composer require some/package
fin tinker
fin bash
```

Tear it down when you're done:

```bash
fin down            # this project's containers
fin down asset      # shared asset containers
fin down all        # everything Fin manages
```

> The shared asset containers connect on their service hostnames: `DB_HOST=fin_mysql`,
> `REDIS_HOST=fin_redis`, `fin_postgres`, `fin_minio`. Credentials are fixed at `fin` / `password`,
> shared across every project on the machine.

> **Custom CA certificates.** Drop `.pem`/`.crt` files into `~/.fin/certs` and Fin
> installs them into opted-in app containers on every `fin up` — each cert is copied
> into the container's trust store and registered with `update-ca-certificates`. Opt
> in per plug with `ContainerSpec(install_certs=True)`; the bundled Laravel plug
> already does. Non-Debian images override `cert_dir` / `cert_update_cmd`.

## Command reference

A sub-command is resolved in this order: **reserved (system) → `FIN_APP` plug →
`FIN_PLUGS` plugs → `GLOBAL` plugs.** Reserved commands always win and are never
delegated to a plug.

### System

| Command | Description |
| ------- | ----------- |
| `fin up` | Ensure the proxy, start enabled assets, start the primary app container, auto-create the DB. Requires `FIN_APP`. Offers to install any missing `FIN_APP`/`FIN_PLUGS` plugs from the catalog first. |
| `fin down [asset\|all] [-f]` | Stop **and remove** containers. No scope = this project; `asset` = shared assets; `all` = everything Fin-managed. `-f`/`--force` forces removal. |
| `fin stop [asset\|all]` | Stop containers without removing them. Same scopes as `down`. |
| `fin config enable\|disable\|get\|list` | Manage which **asset** plugs auto-start with `up`. |
| `fin asset up\|stop\|down` | Manage the shared asset containers independently of any project. |

### Containers

| Command | Description |
| ------- | ----------- |
| `fin ps` (aliases `status`, `containers`) | List running Fin containers. `-a`/`--all` includes stopped ones; `-s`/`--stats` adds live CPU/memory columns (slower). |
| `fin exec <cmd> [args...]` | Exec a command in the current project's primary container. When run from a real terminal, interactive sessions like `fin exec sh` / `fin exec bash` attach stdin so they behave like a normal shell (`exit`/Ctrl-D ends them); piped/non-interactive use streams output. |
| `fin inspect [name]` | Rich JSON inspect of a container (default: the project's primary). |
| `fin logs [name] [--follow/-f] [--tail N] [--since X]` | Tail logs (default: the project's primary). |

### Images

| Command | Description |
| ------- | ----------- |
| `fin images ls` (alias `fin img ls`, also `list`) | List Fin-related images (proxy + every loaded plug's images). |
| `fin images rm <image> [-f]` | Remove an image. |
| `fin images prune` | Remove dangling images (asks for confirmation). |

### Plugs

| Command | Description |
| ------- | ----------- |
| `fin plugs list` (alias `ls`) | List installed plugs and their commands. |
| `fin plugs info <name>` | Show one plug's metadata and path. |
| `fin plugs search <query>` | Search the remote plug catalog by name/description. |
| `fin plugs install <name\|git-url>` | Install a plug by catalog name (e.g. `fin plugs install laravel`) or from a git URL. Refuses if already installed — `uninstall` first. |
| `fin plugs uninstall <name>` | Remove an installed plug from disk. |

### AI agents

Fin can generate instruction files that teach AI coding agents (Claude Code,
Cursor, Codex, GitHub Copilot, …) to run project commands through `fin`
(`fin composer install`, never bare `composer install`). The content is
tailored to the project: command tables are built from the installed plugs'
`commands()` metadata. Commit the generated files so every teammate's agent
picks them up; re-run after changing `FIN_APP`/`FIN_PLUGS` or upgrading plugs.

| Command | Description |
| ------- | ----------- |
| `fin agents list` (alias `ls`) | List supported agents, the file each one writes, and whether it's present. |
| `fin agents install [agent ...\|all]` | Generate instruction files into the current project. Default set: `claude` (`.claude/skills/fin-commands/SKILL.md`), `cursor` (`.cursor/rules/fin-commands.mdc`), `codex` (`AGENTS.md`). More via `all` or by name — see below. |

Supported targets: `claude`, `cursor`, `codex`, `opencode`, `kilocode`,
`kimi`, `antigravity`, `copilot-cli` (the last six all read the cross-agent
`AGENTS.md` natively, so they share one file), `copilot` (VS Code Copilot
Chat & coding agent — `.github/copilot-instructions.md`), `gemini`
(`GEMINI.md`), `codebuddy` (`.codebuddy/rules/fin-commands.md`), and `aider`
(`CONVENTIONS.md` plus a `.aider.conf.yml` with `read: CONVENTIONS.md`,
created only if the conf doesn't already exist).

Fin-owned files (the Claude skill, the Cursor and CodeBuddy rules) are
rewritten whole. Shared files (`AGENTS.md`, `GEMINI.md`, Copilot
instructions, `CONVENTIONS.md`) are only touched inside a
`<!-- fin:agents:begin/end -->` marker block — hand-written content around the
block survives every re-run.

### Laravel plug

Available when `FIN_APP=laravel` (or `laravel` is in `FIN_PLUGS`):

| Command | Description |
| ------- | ----------- |
| `fin artisan ...` (alias `art`) | Run an `artisan` command. |
| `fin composer ...` | Run `composer` in the container. |
| `fin tinker` | Open an interactive Laravel tinker session (stdin attached; `exit`/Ctrl-D ends it). |
| `fin migrate [fresh\|rollback\|refresh] ...` | Run migrations. |
| `fin seed [class]` | Run database seeders. |
| `fin make <type> <name> ...` | Run `artisan make:<type>`. |
| `fin queue [work\|listen\|restart] ...` | Run the queue (default `listen`). |
| `fin bash` (alias `shell`) | Open an interactive shell in the container (stdin attached; `exit`/Ctrl-D ends it). |
| `fin phpunit ...` | Run `./vendor/bin/phpunit`. |
| `fin bin <command> ...` | Run `./vendor/bin/<command>`. |
| `fin php ...` | Run the `php` binary. |

### Help

- `fin --help` / `-h` / `help` — command overview (system commands grouped by
  area, plus plug-contributed commands grouped by plug).
- `fin <command> --help` / `-h`, or `fin help <command>` — detailed help for a
  single command: description, usage, subcommands, options, and examples. Works
  for reserved commands **and** plug commands (plug help also shows the plug's
  required environment variables).

```bash
fin config --help     # subcommands: enable | disable | get | list
fin down --help       # scopes [asset|all] and the -f flag
fin artisan --help    # plug command help, incl. the laravel plug's env spec
```

`fin --version` / `-v` / `version` prints `Fin v<version>`.

## Environment variables

### Project variables (read from `./.env`, or the process environment)

Process environment variables take precedence over the `.env` file, so
`FIN_SITE=other.localhost fin up` works for a one-off override.

| Variable | Meaning |
| -------- | ------- |
| `FIN_APP` (a.k.a. `FIN_PLUG`) | Name of the primary **app** plug for this project (e.g. `laravel`). Required by `fin up`. |
| `FIN_PLUGS` | Comma-separated list of auxiliary plugs to consider/start (e.g. `mysql,redis`). |
| `FIN_SITE` | The host the app is routed at (e.g. `myapp.localhost`). Drives Traefik routing. |
| `FIN_CONTAINER_NAME` | Override the project name (defaults to the cwd basename, lowercased). |
| `FIN_DOCKER_IMAGE` | Override the primary container image. *(Laravel)* defaults to `sharanvelu/laravel-php:<FIN_PHP_VERSION>`. |
| `FIN_OVERRIDE_ASSETS` | Comma-separated assets to start, overriding the persisted enable flags. |
| `FIN_PHP_VERSION` | *(Laravel)* PHP/image tag, e.g. `8.3`, `8.2`, `latest`. Default `latest`. |
| `FIN_COMPOSER_VERSION` | *(Laravel)* Composer major version, `1` or `2`. Default `2`. |
| `DB_CONNECTION`, `DB_DATABASE`, `DB_HOST`, ... | Standard Laravel DB config. `fin up` auto-creates `DB_DATABASE` in the shared MySQL/Postgres engine (`DB_CONNECTION` values `mysql`/`mariadb` and `postgres`/`postgresql`/`pgsql` are recognised). |
| `REDIS_*` | Standard Redis config (parsed alongside `DB_*`). |

### System / installer variables (process environment)

| Variable | Meaning | Default |
| -------- | ------- | ------- |
| `FIN_DATA_DIR` | Per-user data dir (config, registry, certs, plugs). | `~/.fin` |
| `FIN_PROXY_IMAGE` | Traefik image for the proxy. | `traefik:v3.6` |
| `FIN_PYTHON` | Force a specific Python interpreter for the launcher. | auto-detected |
| `DOCKER_HOST` | If set, Fin defers to the Docker SDK's own socket handling. | unset |

> Fixed (not environment-configurable): the network name (`fin`); the registry,
> config, certs, and plugs locations under `~/.fin` (`registry.db`, `config.json`,
> `certs/`, `plugs/`); and the shared-asset credentials (`fin` / `password`,
> database `fin`). Those `~/.fin` paths all move together when `FIN_DATA_DIR` is set.

## How it works

> For the full architecture, see **[ARCHITECTURE.md](ARCHITECTURE.md)** (orientation)
> and **[DESIGN.md](DESIGN.md)** (deep dive).

### The proxy

A single, always-on Traefik container named `fin_proxy` (image `traefik:v3.6`)
runs on the Fin network. It uses Traefik's Docker provider with
`exposedbydefault=false`, so it routes a container **only** when that container
carries Traefik labels. Entrypoints `web` (`:80`) and `websecure` (`:443`) are
published to the host, and the dashboard is available at
`http://traefik.localhost` (`:8080`). `fin up` and `fin asset up` ensure the
proxy is running before anything else.

### Assets

Assets are shared, fixed-name containers (`fin_mysql`, `fin_postgres`,
`fin_redis`, `fin_minio`, …) reused across all projects. Which assets start on
`up` is resolved by:

1. `FIN_OVERRIDE_ASSETS` (comma-separated) — if set, it wins outright.
2. Otherwise, every asset explicitly enabled via `fin config enable <asset>`
   (persisted in `~/.fin/config.json`), **plus** any asset named in `FIN_PLUGS`.

### Labels and routing

Every Fin container carries these labels (the master filter is `FIN_MANAGED=true`):

| Label | Value |
| ----- | ----- |
| `FIN_MANAGED` | always `true` |
| `FIN_TYPE` | `app` \| `asset` \| `global` \| `proxy` |
| `FIN_SERVICE` | `web`, `mysql`, `redis`, `postgres`, `proxy`, ... |
| `FIN_SITE` | the routed URL, or `-` |
| `FIN_PROJECT` | the project name, or `-` for shared containers |

Web-exposed services additionally get Traefik routing labels derived from
`FIN_SITE`: a router `rule` (`Host(`myapp.localhost`)`, or `HostRegexp(...)` for
`*.` wildcards), `entrypoints=web,websecure`, a `service` named `<key>_service`,
and a loadbalancer `server.port` taken from the plug's spec. The router key is
the host with `*.`/`.localhost` stripped and `.`/`-` replaced by `_`
(`my-app.localhost` → `my_app`).

### Command resolution order

```
fin <command> [args...]
  1. reserved (system) commands   ← owned by Fin, never delegated
  2. the FIN_APP / FIN_PLUG plug   ← primary app plug
  3. the FIN_PLUGS plugs           ← auxiliary plugs, in declared order
  4. GLOBAL plugs                  ← every plug declaring PlugType.GLOBAL
```

The first match wins. Plug lookup is lazy and de-duplicated by plug name.

## Writing a plug

A plug is a single Python file in the plugs directory; its type is declared
by the class's `plug_type` attribute, not by where the file sits:

```
<PLUGS_DIR>/
  <name>.py                   # one FinPlug subclass; filename == plug name
```

`PLUGS_DIR` is fixed at `~/.fin/plugs` (it moves with `FIN_DATA_DIR`). The loader
imports each file by path, finds the single class that subclasses
`FinPlug` (**only** `FinPlug` subclasses count), instantiates it, and calls
`setup()`. A bad plug logs a warning and is skipped — it never crashes Fin.

Catalog plugs come from the official
[fin-plugs](https://github.com/sharanvelu/fin-plugs) repository — browse it (or
run `fin plugs search`) for the full, up-to-date list of available plugs.
`fin plugs install <name>` fetches `plugs/<name>.py` from its
master branch over plain HTTPS, and `fin plugs search` reads the generated
`catalog.json` published as an asset of the repo's latest release. Point
`FIN_PLUGS_REPO_RAW` (plug files) and `FIN_PLUGS_CATALOG_URL` (catalog) at a
fork/mirror to install from somewhere else.

**Plugs are declarative.** A plug returns `ContainerSpec` / `PlugCommand`
objects and asks `PlugContext` to exec inside a running container — it must never
call Docker itself. Fin's orchestrator is the sole code path that touches the
daemon.

### Minimal ASSET plug

`<PLUGS_DIR>/memcached.py`:

```python
from __future__ import annotations

from fincli.plugs.base import ContainerSpec, FinPlug, PlugType, PortMapping, VolumeMount


class MemcachedPlug(FinPlug):
    name = "memcached"
    version = "1.0.0"
    plug_type = PlugType.ASSET
    description = "Shared Memcached container."

    def asset_specs(self, env) -> list[ContainerSpec]:
        return [
            ContainerSpec(
                service="memcached",
                image="memcached:1.6-alpine",
                container_name="fin_memcached",   # fixed, shared name
                ports=[PortMapping(container=11211, host=11211)],
                volumes=[VolumeMount(host="fin_asset_memcached", container="/data")],
            )
        ]
```

Enable it to auto-start with `fin config enable memcached`, or list it in
`FIN_PLUGS`.

### Minimal APP plug

`<PLUGS_DIR>/static.py`:

```python
from __future__ import annotations

from fincli.core.env import EnvSpec, EnvVar
from fincli.plugs.base import ContainerSpec, FinPlug, PlugCommand, PlugType, PortMapping
from fincli.plugs.context import PlugContext

WEBROOT = "/usr/share/nginx/html"


class StaticPlug(FinPlug):
    name = "static"
    version = "1.0.0"
    plug_type = PlugType.APP
    description = "Static site served by nginx."

    def env_spec(self) -> EnvSpec:
        # Declare what this plug needs; `fin up` validates it and reports
        # *all* problems at once before doing any work.
        return EnvSpec.of([
            EnvVar("FIN_SITE", required=True,
                   description="hostname the site is served at"),
        ])

    def primary_spec(self, env) -> ContainerSpec:
        image = env.get("FIN_DOCKER_IMAGE") or "nginx:stable-alpine"
        return ContainerSpec(
            service="web",
            image=image,
            name_suffix="web",
            ports=[PortMapping(container=80, host=None)],  # Traefik routes it
            web_exposed=True,
            web_port=80,             # loadbalancer port for the router
            workdir_mount=WEBROOT,   # cwd is bind-mounted here by `up`
        )

    def commands(self):
        return {
            "sh": PlugCommand("sh", _sh, "Open a shell in the container.",
                              aliases=("shell",)),
        }


def _sh(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["sh"], workdir=WEBROOT, interactive=True)
```

Key points:

- **`primary_spec(env)`** (APP) returns the one primary `ContainerSpec`. Set
  `web_exposed=True` + `web_port=...` to get Traefik routing from `FIN_SITE`. Set
  `workdir_mount` and `up` will bind-mount the project directory there.
- **`asset_specs(env)`** (ASSET) returns shared-container specs with a fixed
  `container_name`.
- **`commands()`** maps a name to a `PlugCommand(name, handler, help, aliases)`.
  Handlers receive `(ctx: PlugContext, args: list[str])` and return an exit code.
  Use `ctx.exec([...], workdir=...)` to run inside the primary container; pass
  `interactive=True` for anything the user types into (shells, REPLs) —
  without it an interactive program hangs waiting for input.
- **`env_spec()`** declares required/optional vars, `choices`, types, and
  defaults; `EnvSpec.validate(env)` raises one friendly error listing every
  problem.
- **CA certificates.** Set `install_certs=True` on a `ContainerSpec` and Fin
  installs `~/.fin/certs/*.{pem,crt}` into that container's trust store on every
  `fin up`. Defaults target Debian (`/usr/local/share/ca-certificates` +
  `update-ca-certificates`); override `cert_dir` / `cert_update_cmd` for other
  bases.

After adding a plug, `fin plugs list` re-scans the directory and refreshes the
SQLite registry automatically.

## Building a release

Fin is distributed as a standalone binary built with
[PyInstaller](https://pyinstaller.org/) in **onedir** mode — a directory tree
(`fin/fin` executable + `_internal/`) that embeds a Python interpreter and the
`fincli` package. Onedir is used over onefile because it starts fast (no
per-run extraction to a temp dir). Plugs are **not** bundled: they stay as
uncompiled `.py` loaded at runtime from `~/.fin/plugs`.

Build a tarball for the current platform:

```bash
python3 -m pip install --user pyinstaller typer rich docker   # build + runtime deps
bash packaging/build.sh
# → dist/fin/                    the onedir tree
# → dist/fin-<os>-<arch>.tar.gz  the release artifact
```

`packaging/build.sh` drives PyInstaller against the entry point
`packaging/fin_entry.py` (which calls `fincli.__main__:main`), collecting the
`fincli` and `docker` submodules. The runtime deps (`typer`, `rich`, `docker`)
must be importable so PyInstaller can bundle them.

> **PyInstaller cannot cross-compile** — each `fin-<os>-<arch>.tar.gz` must be
> built on its own native OS/arch. `.github/workflows/build.yml` does this on a
> matrix of runners (`macos-14` arm64, `ubuntu-latest` x64, `ubuntu-24.04-arm`
> arm64), triggered by bumping `version` in `pyproject.toml` on master (which
> makes `tag.yml` create the `v*` tag and dispatch the build), and attaches each
> tarball to the GitHub Release that `install.sh` downloads from.

> **macOS signing.** The published binary is unsigned, so `install.sh` strips the
> `com.apple.quarantine` attribute as a stopgap for local installs. The proper
> fix for a public macOS release is code-signing + notarization.

## Troubleshooting

**"Could not connect to Docker. Is Docker running?"** — Fin auto-detects common
Docker sockets (Docker Desktop, Colima, Rancher Desktop, Podman, and the standard
`/var/run/docker.sock`). Start your Docker engine, or set `DOCKER_HOST`
explicitly to defer to the Docker SDK's own handling. This is a *system* error
and exits with code `2`.

**"No primary app plug configured. Set FIN_APP ..."** — `fin up` needs `FIN_APP`
(or `FIN_PLUG`) set in the project's `.env`.

**"Plugs Not Installed"** — `fin up` detects plugs named in `FIN_APP`/`FIN_PLUGS`
that aren't installed and offers to install them from the catalog; declining
(or a failed install) aborts with the manual `fin plugs install <name>`
commands to run. Check what's installed with `fin plugs list`
(`~/.fin/plugs/<name>.py`).

**The `fin` command isn't found** — the installer warns if its chosen bin
directory isn't on your `PATH`. Add it, e.g. `export PATH="$HOME/.local/bin:$PATH"`.

**Exit codes:** `0` success · `1` user error (bad input, missing env, not found)
· `2` system/Docker error (daemon down, API failure).

## Credits

Fin is the superhero successor to **[DockR](https://dockr.in)** and keeps its
conventions — default `fin` / `password` credentials, the shared-asset model, and
familiar Laravel commands — so existing muscle memory carries straight over.
Built on [Rich](https://rich.readthedocs.io/), the
[Docker SDK for Python](https://docker-py.readthedocs.io/), and
[Traefik](https://traefik.io/). MIT licensed.
