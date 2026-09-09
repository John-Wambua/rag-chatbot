# Code Quality Tooling

Added an enforced formatting layer and a set of dev scripts that wrap it. The
front-end (`frontend/index.html`, `frontend/style.css`, `frontend/script.js`) is
formatted by **Prettier**; the Python backend is formatted by **black** with
**isort** for import order. One command formats everything, one checks it, one
gate runs the checks plus the test suite.

## New files

| File | Purpose |
| --- | --- |
| `.prettierrc.json` | Prettier config — the front-end formatting rules |
| `.prettierignore` | Keeps Prettier out of `docs/`, `uv.lock`, `node_modules/`, `.venv/`, `backend/chroma_db/` |
| `scripts/_common.sh` | Shared helpers: repo-root `cd`, pinned Prettier version, front-end globs, logging, graceful `npx` fallback. Sourced, not executed |
| `scripts/format.sh` | Rewrites all sources in place: Prettier → isort → black |
| `scripts/lint.sh` | Read-only check of the same three; prints diffs and exits non-zero if anything is unformatted |
| `scripts/test.sh` | `uv run pytest`, extra args forwarded (`./scripts/test.sh -k search_tools`) |
| `scripts/quality.sh` | The full gate: `lint.sh` then `test.sh` |

## Front-end formatter config

`.prettierrc.json`, chosen to match the existing hand-written style rather than
fight it:

- `printWidth: 100`, overridden to `120` for `*.html` — the markup has long
  `data-question` attributes and deeply nested sidebar sections that read worse
  when hard-wrapped.
- `tabWidth: 2`, spaces. The old files used 4 spaces; 2 is Prettier's default
  for web assets and keeps the nested `details`/`aside` markup from marching off
  the right edge.
- `singleQuote: true` for JS — `script.js` already used single quotes
  throughout, so this was a no-op there.
- `semi: true`, `bracketSpacing: true`, `arrowParens: "always"`,
  `trailingComma: "es5"`, `endOfLine: "lf"`.
- `htmlWhitespaceSensitivity: "css"` so Prettier respects inline vs. block
  display and does not introduce stray text nodes inside `<button>` / `<span>`.

Prettier is pinned to **3.6.2** in `scripts/_common.sh` and invoked via
`npx --yes prettier@3.6.2`, so no `package.json` or `node_modules/` is committed
and every machine formats identically. Node is not a project dependency: if
`npx` is missing the scripts print a warning and skip the front-end step instead
of failing, so the Python half still works on a Node-less machine.

## Front-end files reformatted

All three files were rewritten by Prettier. The changes are formatting only —
verified by stripping all whitespace and diffing the results character by
character, and `node --check frontend/script.js` parses clean.

- **`frontend/style.css`** (759 lines) — whitespace-only: 4-space → 2-space
  indentation, consistent one-declaration-per-line, blank-line normalization.
  No selector, property, or value changed.
- **`frontend/script.js`** (262 lines) — 2-space indentation, collapsed
  duplicate blank lines, aligned trailing comments. The only non-whitespace
  deltas are Prettier's `arrowParens` (`button =>` → `(button) =>`) and three
  added trailing commas in multi-line calls. Both are semantically inert.
- **`frontend/index.html`** (85 lines) — 2-space indentation, attributes broken
  one-per-line where the tag exceeds 120 columns, void elements self-closed
  (`<meta ... />`), `<!DOCTYPE html>` lowercased to `<!doctype html>`. One
  content-level equivalence: the MCP `data-question` attribute used `&quot;`
  entities inside a double-quoted attribute; Prettier switched the attribute to
  single quotes and the entities to literal `"`. The rendered attribute value is
  identical.

**Cache-busting bumped to `v=14`.** `style.css` and `script.js` both changed, so
per the repo convention `index.html` now references `style.css?v=14` and
`script.js?v=14` (was `v=13`).

## Backend formatting (same toolchain, one command)

`black` and `isort` were added as dev dependencies (`uv add --dev black isort`,
so `uv.lock` stays authoritative) and configured in `pyproject.toml`:

- `[tool.black]` — `line-length = 88`, `target-version = ["py313"]`, excluding
  `.venv` and `chroma_db`.
- `[tool.isort]` — `profile = "black"` so the two never disagree,
  `skip_gitignore = true`, and `known_first_party` listing the nine `backend/`
  modules. Without that list isort classifies `config`, `models`,
  `search_tools`, etc. as third-party (they are imported bare, since pytest adds
  `backend/` to `pythonpath`) and shuffles them into the wrong block.

The initial run reformatted 14 Python files and re-sorted imports in 13.

## Other changes

- `CLAUDE.md` — the Commands block now lists the four scripts, and the stale
  "There is no test suite, linter, or formatter configured" note is replaced by
  the formatting contract (who owns what, where the config lives, that Node is
  needed only for the front-end half).
- `.gitignore` — added `node_modules/`, in case someone installs Prettier
  locally instead of going through `npx`.

## Verification

```
./scripts/lint.sh      → Prettier: all matched files use Prettier code style
                         isort --check-only: clean
                         black --check: 17 files would be left unchanged
./scripts/test.sh      → 84 passed
node --check frontend/script.js → parses
```

`format.sh` is idempotent: a second run is a no-op.

The app itself was not launched to eyeball the UI — this worktree has no `.env`,
so `ANTHROPIC_API_KEY` is unset and startup would fail. The front-end changes
are provably whitespace-equivalent, and the 84 tests (including the FastAPI
endpoint tests) pass.

## Usage

```bash
./scripts/format.sh    # after editing anything
./scripts/lint.sh      # check only — suitable for CI or a pre-commit hook
./scripts/quality.sh   # before committing: lint + tests
```
