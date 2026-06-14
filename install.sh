#!/usr/bin/env bash
#
# Fin installer.
#
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/<org>/<repo>/main/install.sh)"
#
# What it does:
#   1. Verifies prerequisites (git, a Python 3.11+ interpreter).
#   2. Clones (or updates) the Fin repo into ${FIN_HOME_DIR:-$HOME/.fin-cli}.
#   3. Symlinks the `fin` launcher into the first writable PATH directory
#      (/usr/local/bin, ~/bin, ~/.bin, ~/.local/bin ...).
#   4. Installs Python dependencies (typer, rich, docker) for the user.
#
# Configurable via environment variables:
#   FIN_REPO_URL   git URL to clone           (default: the public Fin repo)
#   FIN_USE_BRANCH branch/tag to check out    (default: main)
#   FIN_HOME_DIR   install location           (default: $HOME/.fin-cli)
#   FIN_BIN_DIR    where to place the symlink  (default: auto-detected)

set -euo pipefail

FIN_REPO_URL="${FIN_REPO_URL:-https://github.com/your-org/fin.git}"
FIN_USE_BRANCH="${FIN_USE_BRANCH:-main}"
FIN_HOME_DIR="${FIN_HOME_DIR:-$HOME/.fin-cli}"

# --- pretty output ----------------------------------------------------------
c_green=$'\033[0;32m'; c_red=$'\033[0;31m'; c_yellow=$'\033[0;33m'
c_cyan=$'\033[0;36m'; c_reset=$'\033[0m'
info()  { printf "%sℹ%s %s\n" "$c_cyan"   "$c_reset" "$1"; }
ok()    { printf "%s✓%s %s\n" "$c_green"  "$c_reset" "$1"; }
warn()  { printf "%s⚠%s %s\n" "$c_yellow" "$c_reset" "$1"; }
die()   { printf "%s✗%s %s\n" "$c_red"    "$c_reset" "$1" >&2; exit 1; }

# --- prerequisites ----------------------------------------------------------
command -v git >/dev/null 2>&1 || die "git is required but not installed."

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ver="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
    major="${ver%%.*}"; minor="${ver##*.}"
    if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON_BIN="$candidate"; break
    fi
  fi
done
[ -n "$PYTHON_BIN" ] || die "Python 3.11+ is required but was not found."
ok "Using Python: $($PYTHON_BIN --version 2>&1)"

# --- clone or update --------------------------------------------------------
if [ -d "$FIN_HOME_DIR/.git" ]; then
  info "Updating existing install at $FIN_HOME_DIR"
  git -C "$FIN_HOME_DIR" fetch --quiet origin "$FIN_USE_BRANCH"
  git -C "$FIN_HOME_DIR" checkout --quiet "$FIN_USE_BRANCH"
  git -C "$FIN_HOME_DIR" pull --quiet --ff-only origin "$FIN_USE_BRANCH" || warn "Could not fast-forward; continuing."
else
  info "Cloning Fin into $FIN_HOME_DIR"
  git clone --quiet --branch "$FIN_USE_BRANCH" "$FIN_REPO_URL" "$FIN_HOME_DIR" \
    || die "git clone failed (repo: $FIN_REPO_URL, branch: $FIN_USE_BRANCH)."
fi
chmod +x "$FIN_HOME_DIR/fin"
ok "Fin source ready."

# --- install python dependencies (user scope, no venv) ----------------------
info "Installing Python dependencies (typer, rich, docker)…"
if "$PYTHON_BIN" -m pip install --user --quiet --upgrade typer rich docker; then
  ok "Dependencies installed."
else
  warn "Could not install dependencies automatically. Run:"
  warn "  $PYTHON_BIN -m pip install --user typer rich docker"
fi

# --- choose a bin directory on PATH -----------------------------------------
pick_bin_dir() {
  if [ -n "${FIN_BIN_DIR:-}" ]; then echo "$FIN_BIN_DIR"; return; fi
  local candidates=("/usr/local/bin" "$HOME/.local/bin" "$HOME/bin" "$HOME/.bin")
  # Prefer a candidate that is already on PATH and writable.
  for d in "${candidates[@]}"; do
    case ":$PATH:" in
      *":$d:"*)
        if [ -d "$d" ] && [ -w "$d" ]; then echo "$d"; return; fi
        ;;
    esac
  done
  # Otherwise, the first writable candidate (creating ~/ ones as needed).
  for d in "${candidates[@]}"; do
    if [ -d "$d" ] && [ -w "$d" ]; then echo "$d"; return; fi
    case "$d" in
      "$HOME"/*) mkdir -p "$d" 2>/dev/null && echo "$d" && return ;;
    esac
  done
  # Last resort: /usr/local/bin via sudo.
  echo "/usr/local/bin"
}

BIN_DIR="$(pick_bin_dir)"
LINK_PATH="$BIN_DIR/fin"
TARGET="$FIN_HOME_DIR/fin"

info "Linking $LINK_PATH -> $TARGET"
if [ -w "$BIN_DIR" ] || [ ! -e "$BIN_DIR" ]; then
  mkdir -p "$BIN_DIR" 2>/dev/null || true
  ln -sf "$TARGET" "$LINK_PATH"
else
  warn "$BIN_DIR is not writable; using sudo for the symlink."
  sudo mkdir -p "$BIN_DIR"
  sudo ln -sf "$TARGET" "$LINK_PATH"
fi
ok "Linked fin into $BIN_DIR"

# --- PATH hint --------------------------------------------------------------
case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) warn "$BIN_DIR is not on your PATH. Add this to your shell profile:"
     warn "  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo
ok  "Fin installed. Run: ${c_cyan}fin --help${c_reset}"
info "Project plugs live in: $FIN_HOME_DIR/plugs (configurable in fincli/config.py)"
