# UI design tokens (extracted from the design canvas)

Source: the claude.ai design canvas "Strategy Factory — Admin & Dashboard UI" (18 dark and 4 light
boards). Extracted by the supervisor from the boards' markup: every dark colour on the four boards
that have a light twin (Overview, Live monitor, Profile editor, Candidate detail) maps to exactly one
light colour. Values marked **derived** do not occur on a light board and were chosen by the
supervisor to match; everything else is measured. This file and `UI_spec.md` together are the
authority for the look; token names are ours, for the Mantine theme and CSS variables.

## Type

| token | value |
|---|---|
| `font-sans` | Manrope (400, 500, 600, 700, 800), fallback `system-ui, sans-serif` — **bundled**, not Google Fonts |
| `font-mono` | JetBrains Mono (400, 500, 600), fallback `ui-monospace, monospace` — ids, hashes, numbers in tables |
| sizes (px) | 11 caption · 12 small/table · 13 secondary · 14 body · 16 section title · 26 page title (h1) · 24/28/34 big KPI numbers |
| page title | 26 px, weight 800, letter-spacing −0.02 em |
| caption (`.cap`) | 11 px, weight 600, uppercase, letter-spacing 0.08 em, colour `text-muted` |
| badges | 11 px, weight 800, uppercase, padding 5 × 10 px, radius pill |

## Shape and space

| token | value |
|---|---|
| radius | 3 (legend swatch, dot) · 6 (bars) · 8 · 10 (buttons, nav items, inputs) · 12 (small panels) · 16 (cards) · pill 999 |
| spacing scale (px) | 2 · 6 · 8 · 10 · 12 · 16 · 20 · 22 · 26 — card padding 20, page padding 26 × 32, grid gap 12–16 |
| layout | sidebar 248 px fixed; content fluid; boards designed at 1440 px wide |
| primary button | height 44, padding 0 18, radius 10, weight 800, background `accent`, text `on-accent` |

## Colour — surfaces and text

| token | dark | light |
|---|---|---|
| `bg` (page) | `#0A0E16` | `#F4F6FA` |
| `bg-sidebar` | `#0E131D` | `#FFFFFF` |
| `surface` (card) | `#111826` | `#FFFFFF` |
| `surface-2` (inset panel) | `#121A28` | `#F1F4F9` |
| `surface-3` | `#0D1420` | `#F6F8FC` |
| `surface-sunken` | `#0B111B` | `#F3F5F9` |
| `surface-hover` | `#1A2232` | `#E8ECF2` |
| `surface-alt` | `#1B2638` | `#E9EDF3` |
| `nav-active-bg` | `#16202F` | `#E6F4F1` |
| `border` | `#1C2536` | `#E3E8F0` |
| `border-sidebar` | `#1B2332` | `#E3E8F0` |
| `border-panel` | `#1E2839` | `#DDE3EC` |
| `border-strong` | `#243047` | `#D5DCE7` |
| `border-strong-2` | `#222D40` | `#D5DCE7` |
| `border-input` | `#2E3B52` | `#CBD5E3` |
| `track` (empty bar, idle dot) | `#2A3547` | `#C9D1DD` |
| `text` | `#E6EAF2` | `#141A26` |
| `text-strong` | `#FFFFFF` | `#141A26` |
| `text-secondary` | `#B6BFD0` | `#3E4859` |
| `text-body-2` | `#C7D0DF` | `#2F3848` |
| `text-tertiary` | `#A3ADBF` | `#4F5B6E` |
| `text-subtle` | `#9AA4B8` | `#566275` |
| `text-muted` | `#8E99AE` | `#5F6B80` |
| `text-faint` | `#7D889C` | `#6A7588` |
| `text-disabled` | `#4B5568` | `#4B5568` |
| `link` | `#7FB2FF` | `#1D5FD0` |
| `link-hover` | `#A9CBFF` | `#1D4ED8` |

## Colour — accents and semantics

| token | dark | light | used for |
|---|---|---|---|
| `accent` | `#2DD4BF` | `#2DD4BF` | brand, primary button, done, "real passes" |
| `on-accent` | `#04211D` | `#04211D` | text on `accent` |
| `accent-fg` | `#7DEBD7` | `#0F766E` | pass, success text, MR |
| `accent-fg-2` | `#9FE8D8` | `#0F766E` | server-on text |
| `accent-bg` | `#0F3A33` | `#DDF5F0` | pass / running-download badge |
| `blue` | `#5B8DEF` | `#5B8DEF` | running bar, after-cost series |
| `blue-fg` | `#A9CBFF` | `#1D4ED8` | real arm, long, library |
| `blue-bg` | `#16233A` | `#E4ECFB` | REAL source badge, profile tag |
| `status-running` | `#7DB2FF` | `#1D5FD0` **derived** | run status Running |
| `amber` | `#F5A524` | `#F5A524` | null/control bars, warnings in charts |
| `amber-fg` | `#F6C26B` | `#9A5B00` | control arm, NULL source, short, target missed |
| `amber-fg-2` | `#F6D29B` | `#7A4700` | |
| `amber-bg` | `#3A2A0E` | `#FCEFD9` | NULL badge, warning badge |
| `amber-bg-2` | `#2A1E0B` | `#FFF4E0` | warning banner fill |
| `amber-border` | `#5A3F12` | `#F0D29A` | warning banner border |
| `amber-mid` | `#8A6420` | `#D9A441` | |
| `violet` | `#C4A5FF` | `#6D28D9` | PLANTED source, the user's own rules |
| `violet-strong` | `#D9CBFF` | `#5B21B6` | |
| `violet-bg` | `#2A1F45` | `#EDE7FB` | PLANTED badge |
| `violet-bg-2` | `#1A1430` | `#F1ECFC` | |
| `violet-border` | `#3A2C63` | `#D8CCF6` | |
| `danger` | `#FF8A7A` | `#D92D20` **derived** | failed status, failure swatch |
| `danger-fg` | `#FF9A8A` | `#B42318` **derived** | FAIL verdict, removed value in diffs |
| `danger-bg` | `#2A1616` | `#FDECEA` **derived** | FAIL badge, data-gap bar |
| `waiting` | `#4B5568` | `#9AA4B8` **derived** | waiting stage bar |

Selected card (launch wizard): background `#132033` / light `#E4ECFB` **derived**, border `accent`;
unselected `surface-3` with `border`.

## Status and arm colours (the live monitor and history)

| state | colour token |
|---|---|
| Done | `accent` (bar), `accent-fg` (label) |
| Running | `blue` (bar), `status-running` (label) |
| Waiting / Queued | `waiting` (bar), `text-subtle` (label) |
| Failed | `danger` |
| Real arm | `blue-fg` |
| Control arm | `amber-fg` |
| Source badges | REAL `blue-bg`/`blue-fg` · NULL `amber-bg`/`amber-fg` · PLANTED `violet-bg`/`violet-fg` (`violet`) |

## Chart palette (ECharts and Plotly, both themes)

Series order: `accent` `#2DD4BF`, `blue` `#5B8DEF`, `violet` `#C4A5FF` (light `#6D28D9`), `amber`
`#F5A524`, `danger` `#FF8A7A` (light `#D92D20`), `blue-fg`, `accent-fg`. Sequential heat scale (stage-1
edge map): `#1C2536` → `#34507A` → `#5B8DEF` → `#2DD4BF` (light: start from `#E3E8F0`, **derived**).
Axis and grid lines `border`; axis labels `text-muted`, 11–12 px.
