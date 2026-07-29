#!/usr/bin/env bash
#
# Build a standalone `fin` binary with PyInstaller (onedir) and package a
# release tarball. The target host needs NO Python — the binary embeds its own
# interpreter + fincli. Plugs are loaded at runtime from ~/.fin/plugs (they are
# NOT bundled; see install.sh, which seeds them from the fin-plugs repo).
#
# Output:
#   dist/fin/                      the onedir tree (executable + _internal/)
#   dist/fin-<os>-<arch>.tar.gz    the release artifact (top-level fin/ dir)
#
# Usage:  bash packaging/build.sh
# Env:    FIN_VERSION  version label for logging (default: from pyproject.toml)
#
# Note: PyInstaller cannot cross-compile — run this on each target OS/arch
# (see .github/workflows/build.yml for the CI matrix).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- version (informational; never abort the build over it) -----------------
# `sed -n …p` exits 0 even when nothing matches, so this is pipefail-safe.
VERSION="${FIN_VERSION:-$(sed -nE 's/^version = "([^"]+)".*/\1/p' pyproject.toml | head -1)}"
VERSION="${VERSION:-dev}"

# --- normalise os/arch into a stable artifact label -------------------------
case "$(uname -s)" in
  Darwin) OS=macos ;;
  Linux)  OS=linux ;;
  *) echo "build.sh: unsupported OS '$(uname -s)'" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64)  ARCH=x64 ;;
  *) echo "build.sh: unsupported arch '$(uname -m)'" >&2; exit 1 ;;
esac
ARTIFACT="fin-${OS}-${ARCH}.tar.gz"

echo "==> Building fin v${VERSION} for ${OS}-${ARCH}"

# --- prerequisites ----------------------------------------------------------
python3 -m PyInstaller --version >/dev/null 2>&1 || {
  echo "build.sh: PyInstaller not found." >&2
  echo "  Install with: python3 -m pip install --user pyinstaller" >&2
  exit 1
}

# --- clean previous outputs -------------------------------------------------
rm -rf build dist/fin "dist/${ARTIFACT}"

# --- build (onedir; the fast, no-per-run-extraction form) -------------------
# --collect-submodules fincli: bundle EVERY fincli submodule, even ones only
#   imported at runtime by external plug files (which do `from fincli... import`).
# --collect-submodules docker + --copy-metadata docker: the Docker SDK and the
#   importlib.metadata version lookup it performs.
python3 -m PyInstaller \
  --name fin \
  --paths "$REPO_ROOT" \
  --collect-submodules fincli \
  --collect-submodules docker \
  --copy-metadata docker \
  --distpath dist \
  --workpath build \
  --specpath build \
  --noconfirm \
  packaging/fin_entry.py

# --- package the onedir tree (top-level fin/ inside the tarball) ------------
tar -C dist -czf "dist/${ARTIFACT}" fin

echo "==> Wrote dist/${ARTIFACT} ($(du -h "dist/${ARTIFACT}" | cut -f1 | tr -d ' '))"
echo "==> Run locally: dist/fin/fin --help"
