#!/usr/bin/env bash
#
# Fin installer — installs a prebuilt, standalone `fin` binary.
#
# No Python, pip, or virtualenv is required on the host: the binary embeds its
# own interpreter. Docker is still needed at runtime. Plugs are installed
# separately into ~/.fin/plugs via `fin plugs install <name>`.
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/sharanvelu/fin/master/install.sh)"
#
# What it does (entirely user-local — never uses sudo):
#   1. Detects OS/arch and downloads the matching release tarball.
#   2. Unpacks it to ${FIN_HOME_DIR:-$HOME/.local/lib/fin-cli}, creating the
#      directory if needed.
#   3. Symlinks the `fin` launcher into the first writable PATH directory.
#   4. Runs `fin --version` once so the slow first launch of the unsigned
#      binary happens here, not on the user's first command.
#   5. Creates the plugs directory at ~/.fin/plugs.
#
# Configurable via environment variables:
#   FIN_VERSION       release to install ("latest" or e.g. 0.1.0)  (default: latest)
#   FIN_HOME_DIR      install location                             (default: $HOME/.local/lib/fin-cli)
#   FIN_BIN_DIR       where to place the `fin` symlink             (default: auto-detected)
#   FIN_DATA_DIR      per-user data dir (config, registry, plugs)  (default: $HOME/.fin)
#   FIN_RELEASE_REPO  GitHub repo hosting the releases             (default: sharanvelu/fin)

set -euo pipefail

FIN_VERSION="${FIN_VERSION:-latest}"
FIN_VERSION="${FIN_VERSION#v}"   # tolerate a leading "v" (release tags are vX.Y.Z)
FIN_HOME_DIR="${FIN_HOME_DIR:-$HOME/.local/lib/fin-cli}"
FIN_DATA_DIR="${FIN_DATA_DIR:-$HOME/.fin}"
FIN_RELEASE_REPO="${FIN_RELEASE_REPO:-sharanvelu/fin}"

# --- pretty output ----------------------------------------------------------
c_green=$'\033[0;32m'; c_red=$'\033[0;31m'; c_yellow=$'\033[0;33m'
c_cyan=$'\033[0;36m'; c_reset=$'\033[0m'
info()  { printf "%sℹ%s %s\n" "$c_cyan"   "$c_reset" "$1"; }
ok()    { printf "%s✓%s %s\n" "$c_green"  "$c_reset" "$1"; }
warn()  { printf "%s⚠%s %s\n" "$c_yellow" "$c_reset" "$1"; }
die()   { printf "%s✗%s %s\n" "$c_red"    "$c_reset" "$1" >&2; exit 1; }

# --- prerequisites ----------------------------------------------------------
# A downloader and tar are all we need (no Python).
if command -v curl >/dev/null 2>&1; then
  DL() { curl -fsSL "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
  DL() { wget -qO "$2" "$1"; }
else
  die "Need curl or wget to download Fin."
fi
command -v tar >/dev/null 2>&1 || die "tar is required but not installed."

# --- detect OS/arch (must match packaging/build.sh labels) ------------------
case "$(uname -s)" in
  Darwin) OS=macos ;;
  Linux)  OS=linux ;;
  *) die "Unsupported OS: $(uname -s)" ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64)  ARCH=x64 ;;
  *) die "Unsupported architecture: $(uname -m)" ;;
esac
ARTIFACT="fin-${OS}-${ARCH}.tar.gz"

# --- resolve the download URL -----------------------------------------------
# "latest" uses GitHub's native /releases/latest/ redirect, which always points
# at the newest full (non-pre, non-draft) release — every v* release qualifies.
# A specific version installs the immutable v* release directly.
if [ "$FIN_VERSION" = "latest" ]; then
  URL="https://github.com/${FIN_RELEASE_REPO}/releases/latest/download/${ARTIFACT}"
else
  URL="https://github.com/${FIN_RELEASE_REPO}/releases/download/v${FIN_VERSION}/${ARTIFACT}"
fi

# --- download + unpack ------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
info "Downloading $ARTIFACT ($FIN_VERSION)…"
DL "$URL" "$TMP/$ARTIFACT" || die "Download failed: $URL"

# The install is entirely user-local: never escalate to sudo. If the target
# isn't creatable/writable, fail with a hint instead of prompting for a password.
info "Installing into $FIN_HOME_DIR"
mkdir -p "$FIN_HOME_DIR" 2>/dev/null \
  || die "Cannot create $FIN_HOME_DIR (this installer never uses sudo). Set FIN_HOME_DIR to a writable location."
[ -w "$FIN_HOME_DIR" ] \
  || die "$FIN_HOME_DIR is not writable (this installer never uses sudo). Set FIN_HOME_DIR to a writable location."
rm -rf "$FIN_HOME_DIR/fin"                 # clean previous install (idempotent)
tar -C "$FIN_HOME_DIR" -xzf "$TMP/$ARTIFACT"
[ -x "$FIN_HOME_DIR/fin/fin" ] || die "Unexpected archive layout (missing fin/fin)."

# macOS: strip the quarantine flag so the unsigned binary runs without a
# Gatekeeper prompt. (The proper fix for a public release is notarization.)
if [ "$OS" = "macos" ]; then
  xattr -dr com.apple.quarantine "$FIN_HOME_DIR/fin" 2>/dev/null || true
fi
ok "Fin binary installed."

# --- choose a bin directory on PATH -----------------------------------------
pick_bin_dir() {
  if [ -n "${FIN_BIN_DIR:-}" ]; then echo "$FIN_BIN_DIR"; return; fi
  local candidates=("/usr/local/bin" "$HOME/.local/bin" "$HOME/bin" "$HOME/.bin")
  for d in "${candidates[@]}"; do
    case ":$PATH:" in
      *":$d:"*) if [ -d "$d" ] && [ -w "$d" ]; then echo "$d"; return; fi ;;
    esac
  done
  for d in "${candidates[@]}"; do
    if [ -d "$d" ] && [ -w "$d" ]; then echo "$d"; return; fi
    case "$d" in
      "$HOME"/*) mkdir -p "$d" 2>/dev/null && echo "$d" && return ;;
    esac
  done
  # Last resort: a user-owned bin dir we can always create (never sudo).
  echo "$HOME/.local/bin"
}

BIN_DIR="$(pick_bin_dir)"
LINK_PATH="$BIN_DIR/fin"
TARGET="$FIN_HOME_DIR/fin/fin"

info "Linking $LINK_PATH -> $TARGET"
mkdir -p "$BIN_DIR" 2>/dev/null || true
if [ -d "$BIN_DIR" ] && [ -w "$BIN_DIR" ]; then
  ln -sf "$TARGET" "$LINK_PATH"
else
  die "$BIN_DIR is not writable (this installer never uses sudo). Set FIN_BIN_DIR to a writable directory on your PATH."
fi
ok "Linked fin into $BIN_DIR"

# --- warm-up first run -------------------------------------------------------
# The binary is not code-signed, so the OS verifies it on first launch — which
# can take ~15s (macOS Gatekeeper scan of the unpacked runtime). Run it once
# here so the user's first real `fin` command starts instantly.
info "Warming up fin…"
if "$TARGET" --version >/dev/null 2>&1; then
  ok "Fin Warmed-up."
else
  warn "Warm-up run failed; your first manual run of fin may be slow."
fi

# --- plugs directory ----------------------------------------------------------
# Plugs live in ~/.fin/plugs as flat <name>.py files. They are NOT part of the
# binary; install them with `fin plugs install <name>`.
mkdir -p "$FIN_DATA_DIR/plugs"

# --- PATH hint --------------------------------------------------------------
case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) warn "$BIN_DIR is not on your PATH. Add this to your shell profile:"
     warn "  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo
ok  "Fin installed. Run: ${c_cyan}fin --help${c_reset}"
info "Requires a running Docker engine. Install plugs with: fin plugs install <name>"
