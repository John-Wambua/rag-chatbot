# Frontend Changes — Theme Toggle Button

A sun/moon icon button in the top-right of the viewport that switches the app
between its existing dark palette and a new light palette.

Front-end only: no backend file was touched, and no new dependency was added.

## Files changed

| File | Change |
| --- | --- |
| `frontend/index.html` | Toggle button markup, pre-paint theme bootstrap, cache-bust `v=13` → `v=15` |
| `frontend/style.css` | Light-theme token block, `.theme-toggle` styles, icon cross-fade, surface transitions, accent-text contrast fix |
| `frontend/script.js` | `setupTheme` / `toggleTheme` and the localStorage + `prefers-color-scheme` plumbing |

## What was built

### Toggle button design

A 44×44px circular icon button using the same tokens as the rest of the UI
(`--surface` fill, `--border-color` border, `--shadow`), so it reads as part of
the existing aesthetic rather than an add-on. Hover lifts it 1px and recolours it
to `--primary-color`, matching the `#sendButton` and `.suggested-item` hover
treatments already in the sheet. Active state settles back down with a slight
scale-in.

Icons are two inline stroke SVGs (feather-style sun and moon) drawn at
`stroke-width: 2` with round caps — the same drawing style as the existing send
arrow — and coloured with `currentColor` so they follow the button's text colour.

### Position

`position: fixed; top: 1.25rem; right: 1.25rem` on the viewport, not inside a
header — `header` is `display: none` in this app, so there is no top bar to hang
it in. It shrinks to 40px with a 0.75rem inset below 768px.

Below 1200px the centred 800px chat column reaches the gutter the button sits in,
so `.chat-messages` gains `padding-right: 5rem` (4.25rem on mobile) to keep a
16px clearance between the widest message bubble and the button. Verified at
1100px and 420px: 16px gap in both, no horizontal page scroll.

### Transition animation

The two icons are stacked absolutely in the same cell and cross-fade in place:
the outgoing icon rotates 90° and scales to 0.4 while fading out, the incoming one
unwinds to `rotate(0) scale(1)`, over 350ms on a slightly overshooting
`cubic-bezier(0.34, 1.36, 0.64, 1)`.

The surfaces underneath fade too rather than snapping — `body`, `.sidebar`,
`.chat-*`, `.message-content`, `.stat-item`, `.suggested-item` and `#chatInput`
transition `background-color` / `border-color` / `color` over a shared
`--theme-transition` (300ms). The pre-existing hover and focus animations on
`.suggested-item` and `#chatInput` were folded into their new transition lists so
they keep working.

`@media (prefers-reduced-motion: reduce)` collapses all of it to 0.01ms and drops
the hover lift, keeping the focus ring intact.

### Accessibility and keyboard support

- A real `<button type="button">`, so it is in the natural tab order and Enter and
  Space activate it without extra key handling.
- `aria-label` and `title` name the action and are rewritten on every toggle
  ("Switch to light theme" ⇄ "Switch to dark theme"). The visible icon is the theme
  you are switching *to*, so icon and label always agree.
- Both SVGs are `aria-hidden="true" focusable="false"` — the label is the only
  thing announced, and IE/Edge-style focusable SVG children can't create phantom
  tab stops.
- `:focus-visible` gets the app's standard `0 0 0 3px var(--focus-ring)` ring plus a
  `--primary-color` border; mouse clicks don't show it.
- 44×44px hit target (WCAG 2.5.5 AAA).

## Light theme

The toggle needs somewhere to toggle *to*, so the app's dark-only palette was
split in two. Every colour was already a CSS custom property on `:root`, so this
is a re-pointing rather than a restyle: a `:root[data-theme="light"]` block
redefines the same token names. Nothing else needed new selectors.

Two extras were needed:

- `color-scheme: dark` / `light` on `:root`, so native scrollbars and form chrome
  follow the theme.
- `--code-bg`, replacing the two hardcoded `rgba(0, 0, 0, 0.2)` fills on
  `.message-content code` and `pre`, which would have been a muddy grey slab on
  white.

Contrast was measured in-browser for both palettes. All light-theme pairs pass
WCAG AA: body text 17.85:1, assistant bubble 16.3:1, secondary text and the toggle
icon 6.92:1, links 6.7:1, `.stat-value` 5.17:1.

## Dark-theme contrast fix

Measuring the palettes surfaced a pre-existing failure in the dark theme, which was
then fixed. `--primary-color` (`#2563eb`) was being used both as a **background**
fill and as a **foreground** colour. As a fill it is fine — white on it is 5.17:1 —
but as text or an icon on the dark surfaces it failed AA everywhere it appeared:

| Usage | Surface | Before | After |
| --- | --- | --- | --- |
| `.stat-value` | `--background` | 3.45:1 ✗ | **7.02:1** ✓ |
| `.stats-header` / `.suggested-header` / `#newChatButton` hover + focus | `--surface` | 2.83:1 ✗ | **5.75:1** ✓ |
| `.course-titles-header:focus` | `--surface` | 2.83:1 ✗ | **5.75:1** ✓ |
| `.suggested-item:hover` text + border | `--surface-hover` | 2.00:1 ✗ | **5.74:1** ✓ |
| `.theme-toggle:hover` icon + border | `--surface-hover` | 2.00:1 ✗ | **5.74:1** ✓ |
| `#chatInput:focus` border | `--surface` | 2.83:1 ✗ | **5.75:1** ✓ |

The `.suggested-item` hover at 2.00:1 was the worst of them — effectively
unreadable — and only `.stat-value` was visible without interacting, which is why
the static screenshot didn't reveal the rest.

The fix follows the pattern the stylesheet had already established for links
(`--link-color` is a lighter blue than `--primary-color` for exactly this reason).
Two foreground tokens were added and `--primary-color` was left to do only what it
is good at:

```css
--accent-text: #60a5fa;         /* accent as text/icon on --background and --surface */
--accent-text-strong: #93c5fd;  /* --surface-hover is light enough to need brighter */
```

Two tokens rather than one because `--surface-hover` (`#334155`) is a good deal
lighter than the other two surfaces: `--accent-text` only reaches 4.07:1 against it,
still short of AA, so hover states step up to `--accent-text-strong`.

Light theme runs the same two tokens darker (`#1d4ed8` / `#1e3a8a`), giving
6.7:1 / 6.12:1 / 8.4:1 on the equivalent surfaces.

After the change the only remaining `var(--primary-color)` in the sheet is the
`#sendButton` background, which is the fill usage that was always correct.

### Also fixed

`.message-content blockquote` had `border-left: 3px solid var(--primary)` — a token
that does not exist in this stylesheet (the real name is `--primary-color`). The
invalid reference made the border fall back to `currentColor`, so blockquotes drew a
grey border instead of the intended accent. Now points at `--accent-text`.

### Not changed

`--focus-ring` is `rgba(37, 99, 235, 0.2)`, which composites to only ~1.2:1 against
either dark surface — a very faint glow. For `#chatInput` and `.theme-toggle` this
does not matter much, because both also switch their border to `--accent-text` on
focus, which is now the visible cue at 5.75:1. But `.suggested-item:focus` sets
*only* the box-shadow, so its keyboard focus indicator is weak. Fixing that means
either raising the ring's alpha or giving `.suggested-item:focus` a border change,
and it affects both themes and three components — a design decision rather than a
contrast bug in this feature, so it is flagged here rather than changed.

## How the theme is chosen and remembered

The active theme lives in a `data-theme` attribute on `<html>`:

1. An inline `<script>` in `<head>` sets it **before first paint**, so a reloading
   light-theme user never sees a flash of dark. It has to be inline and separate
   from `script.js`, which only runs on `DOMContentLoaded`.
2. Order of preference: stored choice → OS `prefers-color-scheme` → dark.
3. Clicking stores the choice in `localStorage` under `theme`.
4. Until an explicit choice is stored, a `matchMedia` listener follows live OS
   theme changes. Once the user has clicked, their choice wins and the listener
   stands down.

Every `localStorage` access is wrapped in `try`/`catch` — it throws in private-mode
Safari and when site data is blocked. On failure the app falls back to dark and
simply doesn't remember the preference.

## Verification

Driven in a real browser (Playwright) against the frontend served statically:

- Toggle flips `data-theme`, and `body`, sidebar, input and message bubbles all
  repaint (`#0f172a` → `#ffffff`, `#1e293b` → `#f1f5f9`).
- Icon states swap correctly: sun `opacity: 1` in dark, moon `opacity: 1` in light.
- Reachable by `Shift+Tab` from the input; shows the blue focus ring; activates on
  **both Enter and Space**.
- `aria-label` and `title` update on each toggle, and are correct on load.
- Choice survives a reload with the label still in sync and no flash.
- No overlap with message content at 1100px or 420px.
- Both palettes screenshotted and inspected, including an expanded sidebar, a user
  bubble, an assistant bubble with bold text and an inline `code` span, and an open
  Sources citation link.
- Contrast fix verified on live computed styles, not just token maths: hovering
  `.suggested-item` in the browser reports `rgb(147, 197, 253)` on `rgb(51, 65, 85)`
  = 5.74:1, and the settled `.stat-value` reports `rgb(96, 165, 250)` on
  `rgb(15, 23, 42)` = 7.02:1.

Not exercised: the backend was not run (no `ANTHROPIC_API_KEY` / `.env` in this
worktree), so the frontend was served statically and the sample exchange above was
injected into the DOM rather than returned by `/api/query`. Every element the
light palette touches was checked, but not against live API output.

---

# Frontend Changes — Static Mount & Wiring Tests

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
