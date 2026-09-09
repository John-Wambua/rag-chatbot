#!/usr/bin/env bash
# Read-only counterpart to format.sh: reports files that need formatting and
# exits non-zero if any do. This is the check to run in CI or pre-commit.

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

status=0

if have_prettier; then
  log "Prettier --check (front-end: HTML / CSS / JS)"
  prettier --check "${FRONTEND_GLOBS[@]}" || status=1
fi

log "isort --check-only (Python import order)"
uv run isort --check-only --diff . || status=1

log "black --check (Python formatting)"
uv run black --check --diff . || status=1

if [ "$status" -ne 0 ]; then
  warn "Formatting issues found - run ./scripts/format.sh to fix them"
else
  log "All formatting checks passed"
fi

exit "$status"
