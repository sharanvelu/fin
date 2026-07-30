# CI/CD architecture

Every PR workflow follows the same **changes → work → gate** pattern:

1. **`changes`** — `dorny/paths-filter` detects which domains the PR touches
   (each filter includes the workflow's own file and the shared setup action,
   so editing CI re-runs CI). On `workflow_dispatch` all outputs are forced to
   `'true'`.
2. **Work jobs** — path-gated with `if: needs.changes.outputs.<domain> == 'true'`;
   PRs that don't touch a domain skip its jobs entirely.
3. **`gate`** — runs `if: always()` and fails iff any needed job failed or was
   cancelled. **Only the gate is a required check** — a skipped work job can
   therefore never wedge a PR, and the required-check list stays stable as work
   jobs are added or renamed.

## Required status checks (branch ruleset on `master`)

| Check                  | Workflow                  | What it runs                                            |
| ---------------------- | ------------------------- | ------------------------------------------------------- |
| `Tests Gate`           | `tests.yml`               | pytest + coverage floor (py 3.11–3.13); CLI smoke vs real Docker |
| `Code Style Gate`      | `code-style.yml`          | `ruff check` + `ruff format --check` (check-only, never rewrites) |
| `Static Analysis Gate` | `static-code-analyze.yml` | mypy; actionlint + zizmor when `.github/**` changes     |
| `Build Check Gate`     | `build-check.yml`         | sdist/wheel + twine check; PyInstaller build when packaging changes |
| `PR Title Lint`        | `pr-title.yml`            | Conventional Commits on the PR title (squash-merge commit message) |
| `Dependency Review`    | `dependency-review.yml`   | blocks newly-introduced vulnerable deps (moderate+)     |

Not required: `codeql.yml` (alerts to the Security tab only).

The ruleset definition lives in [`rulesets/master.json`](rulesets/master.json).
Apply it with:

```bash
gh api repos/sharanvelu/fin/rulesets --input .github/rulesets/master.json
```

Also enable in repo settings: **Allow auto-merge** (for
`dependabot-auto-merge.yml`), **squash merge** as the merge method, and the
**dependency graph** (for `dependency-review.yml`).

## Coverage ratchet

The floor lives in `pyproject.toml` → `[tool.coverage.report] fail_under`.
When coverage grows, raise the floor — never lower it.

## Release flow

```
merge PR bumping version in pyproject.toml
  → tag.yml   validates strict semver, creates tag vX.Y.Z,
              dispatches build.yml at the tag (tags pushed with GITHUB_TOKEN
              never trigger `push: tags:` — dispatch is the exception)
  → build.yml builds the PyInstaller binary natively per OS/arch
              (macos-arm64, linux-x64, linux-arm64; no cross-compiling)
              then publishes the immutable vX.Y.Z GitHub Release AND moves the
              rolling `latest` prerelease (install.sh's default download) to
              the same artifacts
```

Builds run ONLY at v* tags — ordinary pushes to master publish nothing.
`workflow_dispatch` on `build.yml` with `dry_run: true` builds all platforms
without publishing anything.

## Hardening conventions (apply to every workflow)

- `permissions: {}` at workflow level; per-job grants only.
- Third-party actions pinned to full commit SHAs (`# vX.Y.Z` comment).
- `actions/checkout` with `persist-credentials: false`.
- `timeout-minutes` on every job.
- Toolchain setup only via the shared composite action
  [`actions/setup`](actions/setup/action.yml) — one place to bump Python.
- CI is check-only: it never reformats or auto-fixes code.
