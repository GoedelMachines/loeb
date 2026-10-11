# Löb

Löb is an autonomous end-to-end tester: an LLM in a tool-use loop that reads your git diff, decides what to test, drives your app in a real browser, **talks to it with synthesized speech injected into the browser microphone**, checks the side effects directly in Postgres, Redis, logs and the API, and files a GitHub issue with evidence when something breaks.

There is no test script. Each step, the model picks the next tool based on what it has observed so far.

It was built to test a voice-assistant web app (LiveKit/WebRTC, FastAPI, Huey workers, Postgres, Redis). That app ships here as the worked example in [`examples/voice-assistant/`](examples/voice-assistant/); point Löb at your own app by writing your own versions of those two files.

## How it works

Tools return plain strings; the model reads them and chooses its next move. There are 23 tools:

| Category | Tools |
|----------|-------|
| Git | `git_diff` |
| Services | `start_services` (verifies health checks; never starts anything) · `stop_services` (refuses; the stack is shared) |
| Browser | `launch_browser` · `navigate` · `click` · `type_text` · `screenshot` · `read_transcription` · `read_console` · `get_page_text` · `get_element_state` · `wait_for_selector` · `upload_file` · `login` |
| Audio | `inject_audio` · `inject_silence` |
| Backend | `check_api` · `query_db` (read-only session) · `query_redis` · `read_logs` |
| Reporting | `file_github_issue` (via `gh`) · `send_slack` |

**Audio injection.** Before any page script runs, Löb overrides `navigator.mediaDevices.getUserMedia` so the page's microphone is a Web Audio `MediaStream` that Löb controls. `inject_audio("Hey, are you there?")` synthesizes speech (a local TTS server at `TTS_URL`, falling back to Deepgram if a key is set), resamples it to 48 kHz PCM, and plays it into that stream. The app receives it as ordinary mic input, so the real STT → LLM → TTS path runs. No virtual audio device and no changes to the app are needed.

**LLM providers.** `autonomous_tester/llm/` puts Anthropic (default, `claude-sonnet-4-6`) and OpenAI/OpenAI-compatible endpoints behind one interface.

**UI.** A Textual TUI shows iterations, cost, tokens, the tool log, the model's thinking and the bugs found. `--ci` runs headless and exits 0 (no bugs), 1 (bugs filed) or 2 (error). Every run writes `runs/<timestamp>.json`; screenshots go to `screenshots/`.

## Point it at your app

1. Run your app's stack yourself. Löb attaches to it; it never starts or stops it.
2. Copy `.env.example` to `.env` and set:
   - `BACKEND_DIR`, `FRONTEND_DIR`: local checkouts whose `HEAD~1` diffs the agent reads.
   - `TARGET_CONTEXT`: a Markdown file appended to the system prompt. Put in what a new tester would need: how the app works, its pages, DOM selectors, Redis key patterns, API endpoints. See `examples/voice-assistant/target.md`.
   - `TARGET_SERVICES`: a JSON file of health checks (`http`, `tcp`, or `systemd --user` unit), each with the command to fix it, plus the log sources `read_logs` can read (systemd units, docker containers, otherwise `docker compose logs` in `BACKEND_DIR`). See `examples/voice-assistant/services.json`. Without it, only the API (`/api/health`) and the website are checked.
   - `GITHUB_REPO` (`owner/name`) for issues; `API_BASE_URL`, `WEBSITE_URL`, `POSTGRES_*`, `REDIS_*`.
   - `TEST_EMAIL` / `TEST_PASSWORD`. `login(method="browser")` fills `input#email` / `input#password` at `/sign-in`; `login(method="token")` injects a Supabase session and needs `SUPABASE_URL` and `SUPABASE_ANON_KEY`.
   - `ANTHROPIC_API_KEY` (or the `OPENAI_*` variables with `--provider openai`).
3. Install and run (Python 3.10–3.12: `tools/audio.py` uses `audioop`, removed in 3.13; Chromium via Playwright):

```bash
make install                 # poetry install + playwright install chromium
make dry-run                 # read the diffs and propose a test plan, run nothing
make test-autonomous         # interactive TUI
make test-autonomous ARGS='"Test the mute button during a voice session"'
poetry run python -m autonomous_tester.run --ci   # no TUI; exit code 0/1/2
```

Other flags: `--model`, `--provider anthropic|openai`, `--openai-model`, `--max-iterations` (default 200), `--no-headless`, `--verbose`.

Relative paths in `TARGET_CONTEXT` / `TARGET_SERVICES` resolve against the directory you run from.

## Limitations

- Built for and exercised against one app. The generic parts (browser, audio injection, backend checks, reporting) are generic; the example target, the `/api/health` default and the sign-in flow reflect that app, and other apps will need their own target files.
- Some details are still hardwired: `git_diff` knows exactly two repos (backend, frontend), always against `HEAD~1` by default; Postgres and Redis are the only data stores it can query; token login supports Supabase only.
- Audio injection works only for apps that take mic input through `getUserMedia` in Chromium.
- Every run costs LLM tokens. The agent can be wrong: it can miss bugs, misjudge behaviour, or file issues that are not bugs. Review what it files.
- `query_db` uses a read-only session, but the agent has otherwise broad reach: it runs `gh`, `docker`, `journalctl` and arbitrary HTTP calls against your API. Point it at a test environment, not production.
- Sound effects and desktop notifications are macOS-only and are skipped elsewhere.
- The interactive pre-run setup screen exists (`ui/screens.py`) but is not wired into the app yet.

## Development

```bash
make test        # pytest
make pre-commit  # ruff lint + format
```

To add a tool: implement it in `autonomous_tester/tools/` returning a string, add its schema to `TOOL_DEFINITIONS` and a `case` to `ToolRegistry.dispatch()` in `tool_registry.py`, wire it in `run.py` `_build_stack()`, and test it in `tests/`.

Design notes are in [`docs/design/`](docs/design/).

## License

MIT. See [LICENSE](LICENSE).
