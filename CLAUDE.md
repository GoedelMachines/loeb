# Löb

## What This Is
An AI agent that tests a web app end-to-end. It reads git diffs, verifies the target stack is up, drives the app in a browser (speaking to it via injected audio when the profile says `"app_kind": "voice"`), and verifies backend side effects. The app under test is described by a target profile (`loeb.json`; see `docs/profile.md` and `examples/todo/`). Users' coding agents write that profile by following `loeb guide`.

## Commands
- `make install` — install deps, then `loeb install` (Chromium)
- `make test` — run unit tests
- `make test-e2e` — run Löb (`loeb run`)
- `make check` — validate the target profile and probe the stack (`loeb check`)
- `make pre-commit` — lint + format
- `make generated` — after editing `loeb/guide.md` or `loeb/profile.py`: rewrite `skills/loeb-setup/SKILL.md` and `schema/loeb.schema.json` (a test fails until you do)

## Architecture
- `loeb/agent.py` — LLM tool-use loop
- `loeb/tool_registry.py` — tool schemas (`TOOL_DEFINITIONS`) and `dispatch()`
- `loeb/tools/` — tool implementations (git, services, browser, audio, backend, reporter)
- `loeb/profile.py` — the target profile schema and loader
- `loeb/config.py` — configuration from env vars and `.env`
- `loeb/llm/` — Anthropic and OpenAI providers
- `loeb/ui/` — Textual TUI
- `loeb/cli.py` — the `loeb` command (guide / schema / install / init / check / run); `run.py` — the run itself
- `loeb/check.py` — `loeb check`: static checks, then live checks in Chromium (selectors, sign-in); `--json`
- `loeb/guide.md`, `loeb/guide.py` — the setup guide for coding agents, the skill built from it, the JSON Schema

## Conventions
- Spelling: `loeb` in code, files, commands and env names; Löb in prose
- Python 3.10+ (tests run on 3.12, 3.13 and 3.14), Ruff for linting/formatting, line length 99
- All tools return strings (for the LLM); failures start with `Error:`
- Tests in `tests/` using pytest
