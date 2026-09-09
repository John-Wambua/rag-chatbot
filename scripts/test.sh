#!/usr/bin/env bash
# Run the pytest suite. Extra arguments are forwarded to pytest, e.g.
#   ./scripts/test.sh -k search_tools

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

log "pytest"
uv run pytest "$@"
