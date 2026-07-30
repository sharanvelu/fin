# Fin — Design

This document is the architecture deep-dive for Fin. For usage, see
[README.md](README.md); for working in the codebase as an agent, see
[AGENTS.md](AGENTS.md).

---

## 1. Layered architecture

Fin is organised as strict layers. Dependencies point downward; the UI layer is
the only place that produces terminal output, and the orchestrator is the only
place that mutates the Docker daemon.

```
        ┌─────────────────────────────────────────────────────────┐
        │  fincli/__main__.py        entrypoint + argv dispatch     │
        │  fincli/resolver.py        reserved → APP → PLUGS → GLOBAL │
        └─────────────────────────────────────────────────────────┘
                     │                              │
                     ▼                              ▼
        ┌───────────────────────┐      ┌──────────────────────────┐
        │  fincli/commands       │      │  fincli/plugs             │
        │  reserved system cmds  │      │  base · loader · registry │
        │  up · down · stop · ps │      │  context                  │
        │  exec · logs · images  │      │  (declarative plug API)   │
        │  config · asset · plugs│      └──────────────────────────┘
        └───────────────────────┘                  │
                     │            ┌─────────────────┘
                     ▼            ▼
        ┌─────────────────────────────────────────────────────────┐
        │  fincli/core                                              │
        │  orchestrator  proxy  database  containers  env  store    │
        │  docker_client (singleton)   errors                       │
        └─────────────────────────────────────────────────────────┘
                     │                              │
                     ▼                              ▼
        ┌───────────────────────┐      ┌──────────────────────────┐
        │  fincli/ui             │      │  Docker SDK (docker-py)   │
        │  console · tables ·    │      │  + Traefik proxy          │
        │  spinners (ONLY printer)│     └──────────────────────────┘
        └───────────────────────┘

        fincli/app.py    tool identity (singleton) + exit codes
        fincli/config.py system configuration (paths, labels, network)
```

## 2. Module responsibilities

### Entry / routing

- **`fincli/__main__.py`** — the console-script entrypoint (`main()`). Does its
  own argv dispatch rather than running a pure Typer app, because resolution is
  dynamic (a sub-command may be reserved *or* contributed by a runtime-discovered
  plug). Handles `--help`/`--version`, loads the project env, calls `resolve`,
  runs the result, and returns an exit code via `SystemExit`. The whole dispatch
  is wrapped by `@handle_errors`.
- **`fincli/resolver.py`** — implements the resolution algorithm (§5). Produces a
  `Resolution(kind, run, source)` whose `run` is a zero-arg callable.

### App / config

- **`fincli/app.py`** — `App` singleton holding identity (`name`, `version`,
  `release_date`, `network`, `tagline`) and lifecycle helpers (`terminate`,
  `banner`). Defines the exit-code constants `EXIT_OK=0`, `EXIT_USER=1`,
  `EXIT_SYSTEM=2`.
- **`fincli/config.py`** — `Config`, the central holder of *system*
  configuration: the network name, filesystem paths (`DATA_DIR`, `PLUGS_DIR`,
  `REGISTRY_DB`, `CONFIG_FILE`, `certs_dir()`), shared asset credentials, label
  keys, and proxy settings. Only two values read the environment at
  class-definition time — `FIN_DATA_DIR` and `FIN_PROXY_IMAGE`. The rest are
  fixed: the network name (`fin`), the `DATA_DIR`-relative `PLUGS_DIR` /
  `REGISTRY_DB` / `CONFIG_FILE` / `certs_dir()` (so they all move with
  `FIN_DATA_DIR`), and the shared-asset credentials (`fin` / `password`). Tests
  `monkeypatch` the attributes, not the env.

### Core (`fincli/core`)

- **`docker_client.py`** — `DockerService`, a lazily-initialised **singleton**
  wrapping `docker.from_env()`. Auto-detects the Docker socket across Docker
  Desktop, Colima, Rancher Desktop, Podman, and the standard Linux/WSL path
  (deferring to `DOCKER_HOST` when set). `ping()`s on creation to fail fast, and
  raises `DockerUnavailable` instead of leaking a traceback. `get_docker()` is
  the accessor.
- **`env.py`** — `ProjectEnv` (parsed `.env` + selected process env, with process
  env winning) and the declarative `EnvSpec`/`EnvVar` validation primitives.
- **`containers.py`** — the single source of truth for labels, Traefik routing
  labels, the managed-container filter, network creation, container lookup, and
  the `run_container` helper. Built on `get_docker()`.
- **`orchestrator.py`** — turns plug `ContainerSpec`s into running containers.
  This is where Fin acts *on behalf of* plugs (§4).
- **`proxy.py`** — starts/ensures the built-in Traefik proxy (not a plug).
- **`database.py`** — auto-creates the project's `DB_DATABASE` inside the shared
  MySQL/Postgres asset container via `exec_run` (no host DB client needed).
- **`certs.py`** — installs the user's CA certs from `~/.fin/certs` into any
  container whose `ContainerSpec` opted in (`install_certs`), via `put_archive`
  plus the distro's trust-store refresh command. Best-effort: it never fails
  `fin up`.
- **`store.py`** — tiny JSON store at `~/.fin/config.json` tracking which assets
  auto-start.
- **`errors.py`** — `FinError` hierarchy and the `@handle_errors` decorator that
  renders everything as Rich panels with the right exit code.

### UI (`fincli/ui`) — the only printer

- **`console.py`** — the one shared `Console` (+ a stderr console for
  errors/warnings) and the message helpers `success`/`error`/`warning`/`info`/
  `hint`/`confirm`. **Nothing outside `fincli/ui` calls `print()` directly.**
- **`tables.py`** — Rich table factories for containers and images, with
  consistent status colouring.
- **`spinners.py`** — `fin_spinner(...)` context manager for long operations.

### Plugs (`fincli/plugs`)

- **`base.py`** — the `FinPlug` base class and the declarative value objects
  `ContainerSpec`, `PortMapping`, `VolumeMount`, `PlugCommand`, plus the
  `PlugType` enum (`APP`/`ASSET`/`GLOBAL`).
- **`loader.py`** — `importlib`-based discovery over the directory-grouped tree;
  finds the single `FinPlug` subclass per package, instantiates it, calls
  `setup()`, and degrades gracefully on failure.
- **`registry.py`** — the SQLite cache + the `fin plugs` operations.
- **`context.py`** — `PlugContext`, the execution context handed to plug command
  handlers; exposes `exec(...)` to run inside the primary container. Pass
  `interactive=True` for commands that open a session the user types into
  (`bash`, `tinker`, REPLs); this delegates to **`core/interactive.py`**, which
  attaches the local stdin to a container TTY and proxies both directions until
  the shell exits (so `exit`/Ctrl-D ends it cleanly), falling back to streamed
  output when there is no local TTY. One-shot commands leave it `False`.

### Commands (`fincli/commands`)

Reserved system commands, each registered with the `@reserved` decorator into
`RESERVED_COMMANDS` (by name + alias) and `RESERVED_CANONICAL` (for help). They
read information from plugs but never let a plug perform Docker actions.

## 3. The declarative-plug principle

A plug **describes**; it never **acts**. Concretely:

- A plug returns `ContainerSpec`/`PlugCommand` objects from `primary_spec`,
  `asset_specs`, and `commands`. It never imports `docker`, never calls
  `containers.run`, never touches the daemon.
- The orchestrator (and `PlugContext.exec`) are the *only* code paths that talk
  to Docker. The orchestrator attaches the standard Fin labels, wires Traefik
  routing, mounts the project directory, and calls `run_container`.

**Why.** This gives a single, auditable Docker code path. Labels, network
membership, naming, and routing are applied uniformly regardless of which plug
described the container — a third-party plug cannot forget a label, escape the
`fin` network, or skip the `FIN_MANAGED` marker that teardown relies on. Plugs
stay trivially testable (they're pure functions returning data) and safe to load
from untrusted-ish sources. Only classes subclassing `FinPlug` are recognised, so
incidental classes in a plug module are ignored.

## 4. Orchestrator flow for `fin up`

`fin up` (in `commands/system.py`) is a reserved command that reads from the app
plug and drives core:

```
fin up
 ├─ ProjectEnv.load()                         # .env in cwd + process FIN_*/DB_*/REDIS_*
 ├─ require FIN_APP (a.k.a. FIN_PLUG)         # else FinError "Missing FIN_APP"
 ├─ load_by_name(FIN_APP)                     # must exist and be PlugType.APP
 ├─ plug.env_spec().validate(env)             # reports ALL problems at once
 ├─ ensure_proxy()                            # idempotent traefik:v3.6 (fin_proxy)
 ├─ start_assets_for(env)                     # resolve_enabled_assets → start_asset(...)
 │     ├─ FIN_OVERRIDE_ASSETS wins, else
 │     └─ persisted enabled assets ∪ assets named in FIN_PLUGS
 ├─ spec = plug.primary_spec(env)             # the ContainerSpec to run
 ├─ start_primary(spec, env)                  # labels + Traefik + cwd bind-mount + run
 │     └─ install_certs(container, spec)      # if spec.install_certs: copy ~/.fin/certs + refresh trust store
 ├─ ensure_project_database(env)              # CREATE DATABASE in shared engine if missing
 └─ success("<project> is up at http://<FIN_SITE>")
```

`start_primary` derives the container name `<project>-<name_suffix>` (or the
spec's explicit name), sets `FIN_TYPE=app`, attaches Traefik labels when the spec
is `web_exposed` with a `web_port` and `FIN_SITE` is set, appends a bind mount of
`env.cwd → spec.workdir_mount`, and calls `run_container`. `run_container` is
idempotent: an existing container is reused (started if stopped) rather than
recreated.

`start_asset` is the shared-container variant: fixed name (`fin_<service>` or the
spec's `container_name`), `FIN_TYPE=asset`, `FIN_PROJECT=-`.

When a spec sets `install_certs`, both `start_primary` and `start_asset` then call
`install_certs(container, spec)` (`core/certs.py`): it tars any
`~/.fin/certs/*.{pem,crt}`, `put_archive`s them into the spec's `cert_dir`, and
runs `cert_update_cmd` — Debian defaults, overridable per plug. It runs on every
`fin up` (idempotent) and is best-effort, so a cert problem never fails the up.

## 5. Command resolution algorithm

`resolve(name, args, env)` in `resolver.py`:

1. `load_reserved()` imports every reserved-command module so they self-register.
2. If `name` is in `RESERVED_COMMANDS` (name *or* alias) → run it directly. This
   is the highest priority and is never delegated.
3. Otherwise build the plug lookup order via `_plug_lookup_order(env)`:
   1. `FIN_APP`/`FIN_PLUG` (the primary app plug),
   2. each `FIN_PLUGS` entry, in declared order,
   3. every loaded `GLOBAL` plug.
   The list is lazy (plugs loaded on demand) and de-duplicated by plug name.
4. For each plug, `_find_plug_command` looks up the command by name then by
   alias. The first match wins and is wrapped with a fresh `PlugContext`.
5. No match → `None`, which the entrypoint renders as "Unknown command"
   (`EXIT_USER`).

## 6. Labels and Traefik routing

### Label schema (`core/containers.base_labels`)

| Label (`Config.*`) | Key | Values |
| ------------------ | --- | ------ |
| `LABEL_MANAGED` | `FIN_MANAGED` | always `true` — the master filter for listing/teardown |
| `LABEL_TYPE` | `FIN_TYPE` | `app` / `asset` / `global` / `proxy` |
| `LABEL_SERVICE` | `FIN_SERVICE` | `web`, `mysql`, `redis`, `postgres`, `proxy`, ... |
| `LABEL_SITE` | `FIN_SITE` | the routed URL, or `-` |
| `LABEL_PROJECT` | `FIN_PROJECT` | project name (cwd basename), or `-` for shared |

`managed_filter(**extra)` builds a Docker `filters={"label": [...]}` dict always
scoped to `FIN_MANAGED=true`, so every list/teardown operation is precisely
constrained to Fin-managed containers.

### Traefik routing (`core/containers.traefik_labels`)

For a web-exposed service with a `site` and a `port`, Fin derives a label-safe
router **key** (`traefik_host_key`: strip `*.` and `.localhost`, replace `.`/`-`
with `_`; `my-app.localhost` → `my_app`) and emits:

```
traefik.enable=true
traefik.http.routers.<key>.rule=Host(`my-app.localhost`)      # or HostRegexp(...) for *.
traefik.http.routers.<key>.entrypoints=web,websecure
traefik.http.routers.<key>.service=<key>_service
traefik.http.services.<key>_service.loadbalancer.server.port=<port>
```

Wildcard hosts (`*.example.localhost`) become a `HostRegexp(`^.+\.example\.localhost$`)`
rule. The proxy itself (`fin_proxy`) runs Traefik with the Docker provider
(`exposedbydefault=false`, watching network `fin`), the `web`/`websecure`
entrypoints, and the dashboard at `traefik.localhost`. Because routing is
label-driven, starting any correctly-labelled container is sufficient to route
it — the proxy needs no per-project configuration.

## 7. The registry: SQLite over flat plug files

The **plugs on disk are the source of truth** — flat `PLUGS_DIR/<name>.py`
files, one per plug. A plug's type comes from its declared `plug_type`, never
from its location. The SQLite cache at
`~/.fin/registry.db` exists only so Fin can answer "what plugs exist, of what
type, with what commands" without importing every plug on every invocation.

- `Registry.sync()` re-scans the tree (`load_all`), wipes the table, and inserts
  one row per successfully-loaded plug (`name`, `version`, `plug_type`,
  `description`, `commands`, `path`). It runs implicitly on `all`/`get`/`by_type`
  (via `refresh=True`) and after install/uninstall, so the cache never drifts
  meaningfully from disk. Failed plugs are simply absent.
- `install(<name>)` fetches `plugs/<name>.py` from the fin-plugs repo over plain
  HTTPS (raw.githubusercontent.com; base URL `Config.PLUGS_REPO_RAW`, overridable
  via `FIN_PLUGS_REPO_RAW`), validates it loads as a `FinPlug` whose declared name
  matches, and writes it to `PLUGS_DIR/<name>.py`. `install(<git-url>)`
  clones into a temp dir, requires exactly one loadable plug file (repo root
  or `plugs/`), and installs it the same flat way.
- `search(query)` filters the generated `catalog.json` that the fin-plugs
  release workflow publishes as an asset of each release
  (`Config.PLUGS_CATALOG_URL`, default the repo's `releases/latest/download`
  URL) by name/description and flags installed entries.

One file per plug (rather than package dirs grouped by type) makes the install
URL deterministic from the name alone — `<repo raw>/plugs/<name>.py` — so
installs need no git binary, no GitHub API, and no listing round-trip; the
trade-off is that a plug can never grow beyond a single module. SQLite is
chosen over a JSON blob because it gives indexed by-type/by-name queries for
free and is a stdlib dependency.

## 8. Error handling and the exit-code contract

End users never see a Python traceback. Command code raises `FinError` (or
subclasses `DockerUnavailable`, `NotFound`) for expected failures; the
`@handle_errors` decorator on the top-level dispatch catches:

1. `FinError` → render `exc.message` in a panel titled `exc.title`, exit
   `exc.exit_code`.
2. Docker SDK `NotFound` → "Not Found" panel, `EXIT_USER`.
3. Docker SDK `APIError` → "Docker API Error" panel, `EXIT_SYSTEM`.
4. Docker SDK `DockerException` → "Docker Unavailable" panel, `EXIT_SYSTEM`.
5. `KeyboardInterrupt` → "Cancelled", `EXIT_USER`.

| Code | Meaning |
| ---- | ------- |
| `0` (`EXIT_OK`) | success |
| `1` (`EXIT_USER`) | user error — bad input, missing env, not-found by user fault |
| `2` (`EXIT_SYSTEM`) | system/Docker error — daemon down, API failure |

`EnvSpec.validate` embodies the "report everything at once" philosophy: it
collects *all* failing variables and raises one `FinError` listing each as a
bullet, so a misconfigured `.env` is fixed in a single pass.

## 9. Key design decisions and trade-offs

- **Hand-rolled dispatch over pure Typer.** Resolution must blend static reserved
  commands with plug commands discovered at runtime; a fixed Typer command tree
  can't express that. Typer/Rich still power `--help` and styling. *Trade-off:*
  Fin owns more argv handling itself.
- **Declarative plugs + single Docker path.** Plugs return data; only core
  mutates Docker. Buys uniform labelling/routing and auditability at the cost of
  some indirection (a plug can't do anything truly custom at the daemon level
  without extending core).
- **Singletons for `DockerService`, `App`, `Config`.** One client, one identity,
  one config — natural for a CLI. *Trade-off:* tests must reset the
  `DockerService` singleton between cases (handled by an autouse fixture).
- **Ship a standalone binary; keep source dev friction low.** End users install a
  prebuilt PyInstaller **onedir** binary (see §10) that embeds its own interpreter
  — no Python, pip, or virtualenv on the host, matching DockR's "just works" feel.
  Developers still run the source directly against system Python 3.11+ with a
  `--user` pip install and the `PYTHONPATH`-setting `fin` launcher (no virtualenv).
  *Trade-off:* binaries must be built per OS/arch (PyInstaller can't
  cross-compile), and an unsigned macOS binary needs a quarantine-strip until it
  is notarized.
- **Shared, fixed-name assets.** One `fin_mysql`/`fin_redis`/`fin_postgres`
  across all projects mirrors DockR and avoids N database servers. *Trade-off:*
  projects share an engine (isolated by database, not by container).
- **SQLite cache over a directory source of truth.** Fast queries without giving
  up the filesystem as canonical state; the cache is rebuildable at any time.
- **Graceful plug loading.** One broken plug warns and is skipped rather than
  taking down the whole CLI.

## 10. Distribution and packaging

Fin is delivered two ways, and a full install always has **two parts**: the
`fin` binary on `PATH` and the plugs in `~/.fin/plugs`.

- **Prebuilt binary (end users).** `packaging/build.sh` freezes the CLI with
  PyInstaller in **onedir** mode against `packaging/fin_entry.py` (which calls
  `fincli.__main__:main`), producing `dist/fin/` (a `fin` executable plus
  `_internal/`) and a `fin-<os>-<arch>.tar.gz`. The binary embeds its own Python
  interpreter and the whole `fincli` package, so the host needs **no Python** —
  only Docker at runtime. Onedir is preferred over onefile for fast startup (no
  per-run extraction). PyInstaller **cannot cross-compile**, so
  `.github/workflows/build.yml` builds on a matrix of native runners
  (`macos-14`/arm64, `ubuntu-latest`/x64, `ubuntu-24.04-arm`/arm64)
  on `v*` tag pushes (dispatched by `tag.yml` when the version in
  `pyproject.toml` changes on master) and attaches the tarballs to the
  GitHub Release.
  `install.sh` detects OS/arch, downloads the matching tarball from
  `sharanvelu/fin` Releases, unpacks it to `~/.local/lib/fin-cli` (created if
  missing; entirely user-local, never sudo), symlinks the launcher onto
  `PATH`, strips the macOS quarantine attribute (unsigned binary; the proper
  fix is notarization), runs `fin --version` once to absorb the slow first
  launch of the unsigned binary, and creates the plugs directory at
  `~/.fin/plugs`.
- **From source (developers).** The `fin = fincli.__main__:main` console script in
  `pyproject.toml` and the repo-root `fin` bash launcher both run the module
  against system Python — no freezing step.

**Plugs are never bundled.** They stay uncompiled `.py` under
`~/.fin/plugs/{App,Asset,Global}` and are imported at runtime by the loader (§7),
regardless of whether Fin itself is the binary or the source. Users install
them with `fin plugs install <name>`; developers symlink their checkout there.
