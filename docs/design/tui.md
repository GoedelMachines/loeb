# Löb — TUI Redesign Design

## Identity

- **Name:** Löb (after Löb's theorem — self-referential provability)
- **What it is:** Autonomous testing TUI that observes an AI agent proving a system works
- **Palette:** Own palette (Dusk dark / Linen light) with a peach-coral accent

## Themes

### Dusk (dark)

| Token | Value | Notes |
|-------|-------|-------|
| bg-base | `#0e0718` | Deep purple-black |
| bg-surface | `#180f24` | Slightly lighter purple |
| bg-deep | `#07030e` | Near black |
| bg-hover | `#20152c` | Interactive state |
| primary | `#e8907a` | Sharp peach-coral (Löb's own) |
| text-primary | `#dde0c8` | Warm cream |
| text-secondary | `rgba(221, 224, 200, 0.8)` | 80% cream |
| text-muted | `#9a9878` | Warm gray-brown |
| border | `#3a2e42` | Muted purple |
| border-subtle | `rgba(255, 255, 255, 0.08)` | Faint |
| success | `#22c55e` | Bright green |
| error | `#ef4444` | Bright red |
| warning | `#ffaa00` | Golden orange |

### Linen (light)

| Token | Value | Notes |
|-------|-------|-------|
| bg-base | `#ffffff` | White |
| bg-surface | `#fafafa` | Off-white |
| bg-deep | `#f5f5f5` | Very light gray |
| bg-hover | `#f0f0f2` | Light gray |
| primary | `#e8907a` | Same peach-coral |
| text-primary | `#1e1d26` | Near black |
| text-secondary | `#2e2d3a` | Dark |
| text-muted | `#5e5d74` | Medium gray |
| border | `#e2e2e8` | Light gray |
| border-subtle | `rgba(20, 20, 32, 0.07)` | Faint |
| success | `#16a34a` | Darker green |
| error | `#dc2626` | Darker red |
| warning | `#cc7700` | Darker orange |

## Tool Category Colors

| Category | Color | Marker |
|----------|-------|--------|
| git | `#22c55e` | `◇` |
| services | `#93a4f4` | `□` |
| browser | `#e8907a` | `◉` |
| audio | `#a78bfa` | `∿` |
| backend | `#ffaa00` | `⊙` |
| output | `#c4786a` | `△` |

## Two Layout Modes

### Instrument Mode (developer default)

Sidebar + main area. Familiar panel layout, refined presentation.

**Sidebar (fixed width):**
- Metrics: iteration, elapsed time (live-ticking), cost, tokens
- Pipeline: 7-phase vertical progression with dot indicators
  - Completed: green `●`
  - Current: primary-colored `◉` (bold)
  - Pending: dim `○`
  - Thin rule separating completed from pending
- Health: success/error ratio bar
- Bugs: appears when bugs found

**Main area:**
- Thinking stream (collapsible)
- Active tool indicator (pulsing)
- Tool log (scrollable table)

**Presentation refinements over current TUI:**
- Progressive dimming on older tool log rows
- 1-char left border accent per row matching category color
- Latest row visually elevated (brighter, bolder)
- Section headers with hairline rules beneath
- Top banner (change context) in a labeled panel, not floating
- Bottom bar: left side shows current phase + last action (keybinds via `?` / palette)

### Focus Mode (adaptive, novel)

Single hero zone that morphs with agent cognitive state.

**States:**
- **Thinking** → hero is reasoning stream (large, breathing, pulsed). Periphery compresses to glanceable strips.
- **Acting** → hero is live tool execution with real-time output. Thinking fades to one-line summary.
- **Finding** → hero is the bug/failure detail. Proof chain highlights where it cracked.
- **Between steps** → hero is proof tree / progress map showing proven vs pending vs failed.

**Periphery (always visible):**
- Metrics as a thin horizontal strip
- Proof chain as a vertical spine
- Background color temperature shifts with confidence (warmer = proven, cooler = breaking)

**Transitions:** Smooth weight shifts (panels grow/shrink), not snapping. Breathing rhythm.

## Information Regions (shared)

1. **Metrics** — iteration, elapsed (live), cost, tokens
2. **Pipeline** — 7-phase progression (diff → services → browser → login → test → verify → report)
3. **Health** — success/error ratio
4. **Thinking stream** — live Claude reasoning, collapsible
5. **Active tool** — currently executing, category indicator, pulse animation
6. **Tool log** — chronological history with timing, results, category colors
7. **Bugs panel** — appears on first bug filed

## Keybinds

| Key | Action |
|-----|--------|
| `q` | Quit |
| `p` | Pause / resume |
| `v` | Verbose toggle |
| `t` | Thinking panel collapse / expand |
| `m` | Toggle instrument / focus mode |
| `l` | Toggle dusk / linen theme |
| `enter` | Tool detail modal |
| `?` / `ctrl+p` | Command palette |

## Animation

- Thinking cursor blink (0.5s interval)
- Active tool pulse (4-frame cycle, 0.3s)
- Progressive row fade on older entries
- Live elapsed time ticker in metrics
- Focus mode: smooth panel weight transitions on cognitive state change

## Typography

Monospace throughout (terminal constraint). Hierarchy via:
- **Weight:** bold for headers/active, dim for historical/secondary
- **Color:** primary/muted/category-specific
- **Spacing:** section separators, padding

## Header

Branded: `LÖB` with primary accent color, replacing current `⬡ AUTONOMOUS·TESTER`
