#!/usr/bin/env bash
# Rewrite every source file in place: front-end via Prettier, Python via
# isort + black. Safe to run repeatedly; it is idempotent.

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if have_prettier; then
  log "Prettier (front-end: HTML / CSS / JS)"
  prettier --write "${FRONTEND_GLOBS[@]}"
fi

log "isort (Python import order)"
uv run isort .

log "black (Python formatting)"
uv run black .

log "Formatting complete"
