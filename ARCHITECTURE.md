# Fin — Architecture

A high-level map of how Fin is put together. For the in-depth rationale,
orchestrator flow, label schema, and design trade-offs, see
**[DESIGN.md](DESIGN.md)** — this document is the orientation; DESIGN.md is the
deep dive.

Fin is a plugin-driven CLI that runs local-development Docker containers. You
`cd` into a project, declare a few `FIN_*` variables in `.env`, and `fin up`
brings up a routing proxy, shared databases/caches, and your application
container — all on one Docker network, reachable by `*.localhost` hostnames.

## Layered design

Dependencies point **downward**. Two invariants hold the whole system together:

1. **The UI layer (`fincli/ui`) is the only place that prints.** Nothing else
   writes to the terminal.
2. **The core orchestrator is the only place that mutates the Docker daemon.**
   Plugs never touch Docker — they only describe what they need.

```
        ┌────────────────────────────────────────────────────────────┐
        │  fincli/__main__.py        entrypoint + argv dispatch      │
        │  fincli/resolver.py        reserved → APP → PLUGS → GLOBAL │
        │  fincli/help.py            overview + per-command help     │
        └────────────────────────────────────────────────────────────┘
                     │                              │
                     ▼                              ▼
        ┌────────────────────────┐      ┌────────────────────────────┐
        │  fincli/commands       │      │  fincli/plugs              │
        │  reserved system cmds  │      │  base · loader · registry  │
        │  up · down · stop · ps │      │  context                   │
        │  exec · logs · images  │      │  (declarative plug API)    │
        │  config · asset · plugs│      └────────────────────────────┘
        └────────────────────────┘                  │
                     │            ┌─────────────────┘
                     ▼            ▼
        ┌────────────────────────────────────────────────────────────┐
        │  fincli/core                                               │
        │  orchestrator  proxy  database  containers  interactive    │
        │  env  store  wait  docker_client (singleton)  errors       │
        └────────────────────────────────────────────────────────────┘
                     │                              │
                     ▼                              ▼
        ┌─────────────────────────┐      ┌───────────────────────────┐
        │  fincli/ui              │      │  Docker SDK (docker-py)   │
        │  console · tables ·     │      │  + Traefik proxy          │
        │  spinners (ONLY printer)│      └───────────────────────────┘
        └─────────────────────────┘

        fincli/app.py    tool identity (singleton) + exit codes (0/1/2)
        fincli/config.py system configuration (paths, labels, network, creds)
```

## Component responsibilities

| Layer | Module(s) | Responsibility |
| ----- | --------- | -------------- |
| Entry / routing | `__main__.py`, `resolver.py`, `help.py` | Console entrypoint and its own argv dispatch; resolve a command **reserved → `FIN_APP` → `FIN_PLUGS` → `GLOBAL`**; render overview and per-command help. |
| Reserved commands | `commands/` | System commands Fin owns and never delegates: `up`, `down`, `stop`, `ps`/`status`, `exec`, `inspect`, `logs`, `images`, `config`, `asset`, `plugs`. |
| Plugin system | `plugs/base.py`, `loader.py`, `registry.py`, `context.py` | `FinPlug` base class (only its subclasses count); importlib loader with graceful failure; SQLite-cached registry over the `App/Asset/Global` directory tree; `PlugContext` that lets a plug command exec inside the primary container. |
| Core | `core/orchestrator.py`, `proxy.py`, `database.py`, `containers.py`, `interactive.py`, `env.py`, `store.py`, `wait.py`, `docker_client.py`, `errors.py` | The only code that touches Docker. Turns plug `ContainerSpec`s into running containers; ensures the Traefik proxy; creates the project DB; builds labels + Traefik routing; runs interactive exec sessions; parses `.env` and validates `FIN_*`; persists asset toggles; waits for asset readiness; wraps the Docker SDK as a singleton; renders friendly errors. |
| UI | `ui/console.py`, `tables.py`, `spinners.py` | The single Rich `Console`; status-coloured container/image table factories; the `fin_spinner` context manager. The only printer. |
| Identity / config | `app.py`, `config.py` | `App` singleton (name, version, network, `terminate()`); exit codes `0`/`1`/`2`; system configuration — paths, label keys, network name, shared-asset credentials, proxy image. |

## Request flow (`fin <command>`)

```
fin up                     (in a project dir)
  │
  ├─ __main__: load .env (FIN_* + DB_*/REDIS_*) from the cwd
  ├─ resolver: "up" is reserved → run commands/system.up
  │
  └─ commands/system.up  (reads info from the plug; never lets it act)
        ├─ load the FIN_APP plug, validate its env_spec  (all errors at once)
        ├─ core/proxy.ensure_proxy()        → Traefik container (idempotent)
        ├─ core/orchestrator.start_assets_for(env)
        │     → enabled ASSET plugs' containers (fin_mysql, fin_redis, …)
        ├─ core/orchestrator.start_primary(plug.primary_spec(env), env)
        │     → mounts cwd → spec.workdir_mount, applies FIN_* + Traefik labels
        └─ core/database.ensure_project_database(env)
              → waits for readiness, then CREATE DATABASE if missing
```

A **plug command** (e.g. `fin artisan migrate`) resolves past the reserved set
to the `FIN_APP` plug, whose handler receives a `PlugContext` and calls
`ctx.exec([...])` — which execs inside the project's primary container. Sessions
that read stdin (`bash`, `tinker`, `fin exec sh`) use `ctx.exec(...,
interactive=True)`, attaching a TTY so `exit` ends them cleanly.

## Key invariants

- **Plugs are declarative.** A plug returns `ContainerSpec` / `PlugCommand`
  objects and asks `PlugContext` to exec — it must never import `docker` or call
  the daemon. The orchestrator is the single audited Docker path.
- **One Docker network (`fin`)** created lazily on first `up`; every container
  carries `FIN_MANAGED=true` plus `FIN_TYPE` / `FIN_SERVICE` / `FIN_SITE` /
  `FIN_PROJECT`, so listing and teardown filter precisely.
- **No virtualenv.** The `fin` launcher runs system Python 3.11+ via
  `python3 -m fincli`.
- **No raw tracebacks.** Docker/usage errors render as Rich panels; exit codes
  are `0` success, `1` user error, `2` system/Docker error.

## Where to go next

- **[DESIGN.md](DESIGN.md)** — module-by-module detail, the orchestrator flow,
  the exact Traefik label format, the registry rationale, and design trade-offs.
- **[README.md](README.md)** — install, quickstart, full command and env-var
  reference, and the plug-authoring guide.
- **[AGENTS.md](AGENTS.md)** — conventions for working in the codebase.
