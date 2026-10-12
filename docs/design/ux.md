# UX Improvements: Textual Dashboard + CLI Ergonomics

## Problem

The current Rich Live dashboard wastes space, has a janky thinking panel (collapse/expand), a tool log that truncates too aggressively, and no interactivity during runs. The CLI has no dry-run, verbose, or interactive modes.

## Decision

Replace the Rich Live dashboard with a Textual TUI app. Keep the agent loop unchanged — only the rendering layer changes.

## Dashboard Layout

```
┌──────────────────────────────────────────────────────────┐
│  Löb              Phase 3/7: Browser   ◆  │  Header
├────────────────┬─────────────────────────────────────────┤
│ ITER   12/200  │                                         │
│ TIME   2m 34s  │  Thinking text streams here as a        │  Thinking
│ COST   $0.12   │  scrollable RichLog. Auto-scrolls       │  (RichLog)
│ SAVED  $0.05   │  while streaming, scroll up to read     │
│ TOKENS 45.2k   │  history. Markdown rendered.            │
│ HEALTH ✓ 15/16 │                                         │
│ BUGS   0       │                                         │
├────────────────┤                                         │
│ ▸ screenshot   │                                         │  Current Tool
│ {"name":"home"}│                                         │  (in sidebar)
├────────────────┴─────────────────────────────────────────┤
│ Tool Log                                          15 total│  DataTable
│  #  Tool            ms    Result                         │  (scrollable)
│  13 click           45    Clicked .session-page__btn--m… │
│  14 get_element_st  12    {"class":"…--muted","visible"… │
│ ▸15 screenshot      230   Saved screenshots/home_14.png  │
├──────────────────────────────────────────────────────────┤
│  [q] Quit  [p] Pause  [v] Verbose  [Enter] Expand  [?]  │  Footer
└──────────────────────────────────────────────────────────┘
```

### Stats Sidebar (left column, always visible)
- Iteration counter, elapsed time, cost, cache savings, token count, tool health ratio, bug count
- Compact vertical stack — no horizontal cramming

### Thinking Panel (RichLog, collapsible)
- **Streaming**: expanded (~5 lines visible), auto-scrolls to bottom
- **Idle**: collapses to single-line summary of last thought (default resting state)
- Press `t` to toggle expand/collapse manually; when expanded, scrollable through full history
- Keeps layout tight — collapsed most of the time, only opens when Claude is actively thinking

### Tool Log (DataTable)
- Color-coded rows by category: git=green, services=blue, browser=cyan, audio=magenta, backend=yellow, report=red
- Columns: #, Tool, ms, Result (Result expands to fill width)
- Scrollable with keyboard (up/down/pgup/pgdn)
- Press Enter on any row → overlay showing full untruncated result
- Error rows get red background
- Auto-scrolls unless user has scrolled up (sticky bottom)

### Current Tool
- Tucked into sidebar below stats
- Shows tool name + input preview

### Bugs Panel
- Only mounts when first bug is filed
- Docked above footer, collapsible with `b` key

### Keybindings
- `q` — Quit (graceful shutdown)
- `p` — Pause agent loop (finish current tool, then wait)
- `v` — Toggle verbose mode (full tool results inline)
- `t` — Toggle thinking panel expand/collapse
- `Enter` — Expand selected tool log row (full result overlay)
- `b` — Toggle bugs panel
- `?` — Help overlay

## CLI Modes

### Interactive mode (default when no prompt)
Pre-run wizard using Textual screens:
1. Show recent git changes for the backend and frontend repos
2. Pick test mode: Auto (from diff), Specific (user describes), Re-run (previous session)
3. Pick services: Full stack, Backend only, None (already running)
4. Pick browser: Headless or Visible
5. Confirm and launch

### `--dry-run`
Agent reads the diff and proposes a test plan. No services started, no browser, no side effects. Prints the plan to stdout and exits.

### `--verbose`
Starts with verbose mode on (full tool results in the log panel). Can also be toggled mid-run with `v` key.

## Architecture

```
loeb/
├── agent.py          # Agent class stays, Dashboard class removed
├── ui/
│   ├── app.py        # TextualApp(App) — main app, composes widgets, runs agent in Worker
│   ├── widgets.py    # StatsPanel, ThinkingLog, ToolLog, CurrentTool, BugsPanel
│   ├── screens.py    # ToolDetailScreen (modal)
│   ├── styles.tcss   # Textual CSS
│   └── events.py     # Custom messages: ToolCompleted, ThinkingUpdate, BugFiled, etc.
├── run.py            # Adds --dry-run, --verbose; launches TextualApp or prints dry-run
└── ...
```

### Event flow
1. `TextualApp` launches the agent loop in a Textual `Worker` (background thread)
2. Agent emits custom `Message` subclasses as things happen (thinking text, tool start/complete, bug filed, etc.)
3. UI widgets listen for these messages and update reactively
4. Agent loop logic in `Agent.run()` is unchanged — only the rendering callbacks change

### Dependencies
- Add `textual` to pyproject.toml
- Remove `rich.live` / `rich.layout` usage from agent.py (Rich renderables like Table/Text still used inside Textual widgets)
- Add `questionary` only if Textual's built-in Select/Input widgets are insufficient for the wizard
