#!/usr/bin/env bash
# The full gate: formatting checks, then the test suite. Run this before
# committing.

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

status=0

"$REPO_ROOT/scripts/lint.sh" || status=1
"$REPO_ROOT/scripts/test.sh" || status=1

if [ "$status" -ne 0 ]; then
  warn "Quality gate failed"
else
  log "Quality gate passed"
fi

exit "$status"
