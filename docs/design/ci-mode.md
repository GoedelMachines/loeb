# CI Full-Run Mode Design

**Goal:** Add a `--ci` flag that runs the full autonomous test loop (stack, browser, audio, testing) without the Textual TUI, exiting with a meaningful exit code.

**Architecture:** The agent loop is already decoupled from the TUI — `Agent.run()` works without any event callback. We add a thin `_run_ci()` path in `run.py` that builds the stack, runs the agent directly, and exits with code 0/1/2 based on results.

---

## What changes

| File | Change |
|------|--------|
| `run.py` | Add `--ci` flag, new `_run_ci()` async function |
| `agent.py` | Guard `_play_sound` and `_notify_completion` behind platform/CI check |

## New code path: `_run_ci()`

- Reuses `_build_stack()` (same as TUI path)
- Runs `agent.run(prompt)` directly (no TUI, no event callback)
- Prints Rich summary table via `agent._print_summary()` (already exists)
- Dumps session JSON to `runs/` via `agent._dump_session()` (already exists)
- Cleans up browser + services in `finally` block
- Default prompt: "Begin testing. Read git diffs to decide what to test."

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Run completed, no bugs found |
| 1 | Run completed, bugs found |
| 2 | Run failed (agent error, stack crash) |

## macOS-specific guards

`_play_sound` and `_notify_completion` in `agent.py` currently call `afplay` and `osascript`. Guard these behind `sys.platform == "darwin"` and absence of `CI` env var so they no-op on Linux runners.

## What does NOT change

- `Agent` class core — already works without TUI
- `_build_stack` — already returns everything needed
- `_dump_session` / `_print_summary` — already standalone
- Focus mode, widgets, styles — unrelated
