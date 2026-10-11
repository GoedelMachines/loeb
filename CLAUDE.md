# Löb — Autonomous Tester

## What This Is
An AI agent that tests a web app end-to-end. It reads git diffs, verifies the target stack is up, speaks to the app via injected audio in a browser, and verifies backend side effects. The app under test is described by config (`TARGET_CONTEXT`, `TARGET_SERVICES`; see `examples/`).

## Commands
- `make install` — install deps + Playwright browsers
- `make test` — run unit tests
- `make test-autonomous` — run the autonomous tester
- `make pre-commit` — lint + format

## Architecture
- `autonomous_tester/agent.py` — LLM tool-use loop
- `autonomous_tester/tools/` — all agent tools (git, services, browser, audio, backend, reporter)
- `autonomous_tester/config.py` — configuration from env vars
- `autonomous_tester/run.py` — entry point

## Conventions
- Python 3.10+, Ruff for linting/formatting, line length 99
- All tools are plain functions that return strings (for the LLM)
- Tests in `tests/` using pytest
