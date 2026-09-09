# Frontend changes

## Summary

Added test coverage for the front-end delivery layer — the static mount at `/`
— plus the shared fixtures and pytest configuration that support it. No
production front-end code changed: `frontend/index.html`, `frontend/script.js`
and `frontend/style.css` are untouched. The work is a regression net around the
hand-maintained parts of the front-end that nothing was watching before.

Suite went from **84 → 98 tests**, all passing (`uv run pytest`).

## Why this shape

The `/implement-feature` request asked for API endpoint tests, a `conftest.py`,
and `pytest.ini_options`. All three already existed as of commit `e5099b3`
(`backend/tests/conftest.py`, `test_api_endpoints.py`, and the
`[tool.pytest.ini_options]` block in `pyproject.toml`) and cover `/api/query`
and `/api/courses` in depth. The untested endpoint was `/` — the route the
browser actually hits for the UI — which is also the part of the request that
falls inside this command's front-end-only scope. So that's what was built.

The static-mount import problem the request flagged is real but already solved:
the session-scoped `app_module` fixture imports the real `backend/app.py` with
`RAGSystem` stubbed and the cwd temporarily set to `backend/`, so
`StaticFiles(directory="../frontend")` validates. What was missing is that
Starlette re-resolves that relative directory **per request**, so requests must
also run from `backend/` — handled by the new `frontend_client` fixture rather
than by duplicating the routes inline. Testing the real app means the real
route order, real middleware and real pydantic models are exercised.

## Files changed

### `backend/tests/test_static_frontend.py` (new, 14 tests)

**Serving** — through a real `TestClient` against the real app:

| Test | Guards |
| --- | --- |
| `test_root_serves_the_index_document` | `GET /` → 200, `text/html`, real `<title>` |
| `test_index_html_is_reachable_by_name_too` | `/index.html` works alongside `html=True`'s `/` mapping |
| `test_frontend_assets_are_served` | `/style.css` → `text/css`, `/script.js` → `javascript`, both non-empty |
| `test_cache_busted_asset_urls_resolve` | the versioned URLs the browser really requests (`style.css?v=13`) 200 |
| `test_unknown_asset_returns_404_not_the_index` | `html=True` doesn't turn a typo'd asset path into a 200 HTML page |
| `test_static_mount_does_not_shadow_the_api` | the catch-all mount at `/` still leaves `/api/*` routable — route order is load-bearing |
| `test_static_mount_does_not_serve_files_outside_frontend` | path traversal can't reach `.env` or `backend/config.py` |

**Hand-maintained wiring** — static analysis of `frontend/`, which lives here
because a break in any of it is indistinguishable from a broken page:

| Test | Guards |
| --- | --- |
| `test_all_cache_bust_versions_move_together` | `style.css?v=N` and `script.js?v=N` share `N`. CLAUDE.md documents this bump as manual; bumping one and not the other ships a stale half-pair to every warm cache |
| `test_every_local_asset_ref_exists_on_disk` | no `index.html` reference to a deleted or renamed file |
| `test_element_ids_queried_by_script_exist_in_the_markup` | every `getElementById(...)` in `script.js` has a matching `id=` — a miss yields `null` and the handler dies silently, with no server-side error |
| `test_marked_loads_before_script_js` | `marked.min.js` still loads, and *before* `script.js`, which calls `marked.parse()` on assistant text |
| `test_frontend_calls_the_api_on_a_relative_path` | `API_URL === '/api'`; an absolute host breaks the single-process static+API deployment |
| `test_every_endpoint_the_frontend_calls_is_routed` | the three `fetch()` targets in `script.js` (`POST /api/query`, `GET /api/courses`, `DELETE /api/session/{id}`) match routes `app.py` declares — both directions, so a rename on either side fails |

Two of these were mutation-checked: changing `?v=13` → `?v=12` on one asset and
renaming `id="chatInput"` each fail exactly the intended test.

### `backend/tests/conftest.py` (appended)

New front-end tier, alongside the existing `fake_store` / `real_store` tiers:

- `frontend_dir` (session) — path to `frontend/`.
- `index_html`, `script_js` (session) — source text, read once.
- `frontend_client` — `TestClient` over the real app with `rag_system` replaced
  by `FakeRAGSystem` and cwd monkeypatched to `backend/`, so the static mount's
  relative directory resolves on every request. Bare `TestClient` (not a
  context manager), so the `@on_event("startup")` ingest of real `docs/` never
  fires.

### `pyproject.toml` — `[tool.pytest.ini_options]`

- `addopts`: added `-ra` (summary of non-passing outcomes) and
  `--strict-config` (typo in this block becomes an error, not a silent ignore).
- `markers`: added `frontend`, so the front-end layer runs alone via
  `uv run pytest -m frontend` (~0.2s, no ChromaDB) and can be deselected with
  `-m "not frontend"`.
- `filterwarnings`: `default`, plus targeted ignores for `pkg_resources` and
  SWIG deprecation noise that chromadb/torch drag in and no change here can
  fix. `app.py`'s own `on_event` deprecation stays visible on purpose — that
  one is actionable tech debt (migrate to a lifespan handler).

## Running

```bash
uv run pytest                  # 98 tests
uv run pytest -m frontend      # the 14 static-mount / wiring tests only
uv run pytest -m "not integration"
```
