#!/usr/bin/env bash
# Shared helpers for the quality scripts. Not meant to be run directly.

set -euo pipefail

# Repo root, regardless of where the script was invoked from.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Pinned so every machine and CI run formats identically.
PRETTIER_VERSION="3.6.2"

# Front-end sources Prettier owns. Kept explicit so the scripts never
# wander into docs/, uv.lock, or backend Python.
FRONTEND_GLOBS=("frontend/**/*.html" "frontend/**/*.css" "frontend/**/*.js")

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*" >&2; }

# Prettier is optional tooling: Node is not a dependency of this project, so
# the scripts degrade to a warning instead of failing the whole run.
have_prettier() {
  if ! command -v npx >/dev/null 2>&1; then
    warn "npx not found - skipping front-end formatting (install Node to enable it)"
    return 1
  fi
  return 0
}

prettier() {
  npx --yes "prettier@${PRETTIER_VERSION}" "$@"
}
