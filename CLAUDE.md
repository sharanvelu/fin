# CLAUDE.md

Fin (`fincli` package) is a Python 3.11+ CLI that manages local-development
Docker containers — a plugin-driven successor to [DockR](https://dockr.in). You
`cd` into a project, set `FIN_*` vars in `.env`, and `fin up` ensures a built-in
Traefik proxy, starts shared assets (MySQL/Redis/Postgres/MinIO), starts the app
container, and auto-creates its database. Apps/services are **plugs**:
declarative classes that describe containers and contribute commands but never
touch Docker themselves — Fin's orchestrator does that on their behalf.

## Most important conventions

- **All terminal output goes through `fincli/ui`** (`console.success/error/...`).
  Never call bare `print()` outside `fincli/ui`.
- **Only `fincli/core` touches Docker**, via the `docker` Python SDK
  (`get_docker().client`, `core/containers.py`, the orchestrator,
  `PlugContext.exec`). **No `subprocess` calls to the docker CLI.**
- **Plugs are declarative.** They return `ContainerSpec`/`PlugCommand`; only
  classes subclassing `FinPlug` count. They never import `docker`.
- **No virtualenv** — from source, Fin runs against system Python with `--user`
  packages. End users instead install a prebuilt PyInstaller binary (embeds its
  own interpreter; no host Python) — built by `packaging/build.sh`, installed by
  `install.sh`. Plugs are never bundled: they live as `.py` in `~/.fin/plugs`.
- **Errors render, never crash.** Raise `FinError`/`DockerUnavailable`/`NotFound`;
  `@handle_errors` renders Rich panels. Exit codes: `0` ok, `1` user error, `2`
  system/Docker error.
- **Command resolution:** reserved (system) → `FIN_APP` plug → `FIN_PLUGS` plugs
  → `GLOBAL` plugs.

## Build / test / run

```bash
python3 -m pip install --user typer rich docker   # runtime deps (no venv)
ln -s <fin-plugs checkout>/plugs ~/.fin/plugs     # dev: plugs load from ~/.fin/plugs (PLUGS_DIR); source lives in the separate fin-plugs repo
python3 -m pytest                                 # run the test suite
python3 -m fincli --help                          # run the CLI from source
fin up                                            # in a project dir with a FIN_* .env

python3 -m pip install --user pyinstaller         # build tooling
bash packaging/build.sh                           # build the release binary (per OS/arch)
```

## More detail

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — orientation map: layered design,
  component responsibilities, request flow, and key invariants.
- **[AGENTS.md](AGENTS.md)** — project layout, conventions, how to add a command
  vs a plug, the env-spec pattern, test fixtures, and gotchas.
- **[DESIGN.md](DESIGN.md)** — the deep dive: layer diagram, the declarative-plug
  principle, the `fin up` orchestrator flow, label/Traefik schema, registry
  rationale, and the error/exit-code contract.
- **[README.md](README.md)** — install, quickstart, full command/env reference,
  and the plugin authoring guide.
