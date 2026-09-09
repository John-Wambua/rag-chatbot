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
