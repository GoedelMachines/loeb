# Löb

An end-to-end tester that uses your app the way a user does and checks the result for itself.

Named after Löb's theorem, which implies a formal system can't vouch for its own soundness. Löb is the outside check: an agent's claim that its code works counts only when the running app confirms it.

Löb is an LLM in a tool-use loop. It reads your git diff, decides what to test, drives the running app in a real Chromium browser, checks the side effects directly in Postgres, Redis, the logs and the API, and files a GitHub issue with evidence when something breaks. For voice apps it also speaks to the app, with synthesized speech injected into the browser's microphone.

There is no test script. Each step, the model picks the next tool from what it has observed so far.

## Getting started

Three steps: install Löb, have your coding agent set it up for your app, run it.

**1. Install** (Python 3.10 or newer):

```bash
uv tool install loeb   # or: pipx install loeb
loeb install                          # downloads the Chromium build Playwright drives
```

Löb is on PyPI as [`loeb`](https://pypi.org/project/loeb/). To run unreleased changes, install from a checkout: `uv tool install .`

**2. Set it up for your app.** Löb learns your app from two files in its repo: `loeb.json`, the profile (repos, health checks, pages and selectors, the sign-in form), and `loeb-target.md`, what a new tester would need to know. Writing them means reading your code, which is what a coding agent is good at. In your app's root:

```bash
loeb init      # writes loeb.json, loeb-target.md, a .env template, and the setup skill
```

Then tell your coding agent: *"Set up Löb for this project."* `loeb init` put the instructions where agents that read [Agent Skills](https://agentskills.io) find them (`.agents/skills/loeb-setup/SKILL.md`; add `--claude` for `.claude/skills/`). Any other agent can read them from `loeb guide`. The agent fills in both files from your code, then runs `loeb check --json` and fixes what it reports until everything passes. `loeb check` opens the running app and confirms that every selector in the profile matches and that sign-in works. It makes no LLM call, so this loop costs nothing.

You can also write the files by hand: [`docs/profile.md`](docs/profile.md) documents every field, and `loeb schema` prints the JSON Schema.

**3. Run it:**

```bash
loeb run "Test sign-up with a new email"   # terminal dashboard
loeb run                                    # the agent decides what to test from the diff
loeb run --dry-run                          # reads the diffs, proposes a plan, runs nothing
loeb run --ci "Test sign-up"                # no UI; exit 0 pass, 1 bugs found, 2 error
```

Every run calls the model and costs tokens. Every run that gets past setup, including one that crashes, writes `runs/<timestamp>.json` in the working directory; screenshots go to `screenshots/`.

To see the whole loop without your own app, try [`examples/todo/`](examples/todo/): a one-file to-do list with one planted bug, and the profile an agent would write for it.

## How it works

Tools return plain strings; the model reads them and chooses its next move.

| Category | Tools |
|----------|-------|
| Git | `git_diff` (only when the profile lists repos) |
| Services | `start_services` (verifies health checks; never starts anything) · `stop_services` (refuses; the stack is shared) |
| Browser | `launch_browser` · `navigate` · `click` · `type_text` · `screenshot` · `read_console` · `get_page_text` · `get_element_state` · `wait_for_selector` · `upload_file` · `login` |
| Voice apps only | `inject_audio` · `inject_silence` · `read_transcription` |
| Backend | `check_api` · `query_db` (read-only session) · `query_redis` · `read_logs` |
| Reporting | `file_github_issue` (via `gh`) · `send_slack` |

**Web and voice apps.** The profile's `"app_kind"` is `"web"` by default. `"voice"` adds the audio tools and voice instructions to the system prompt.

**Audio injection (voice apps).** Before any page script runs, Löb overrides `navigator.mediaDevices.getUserMedia` so the page's microphone is a Web Audio `MediaStream` that Löb controls. `inject_audio("Hey, are you there?")` synthesizes speech, resamples it to 48 kHz PCM and plays it into that stream. The app receives it as ordinary microphone input, so its real speech-to-text → model → text-to-speech path runs. No virtual audio device and no changes to the app are needed. Speech comes from a TTS server at `TTS_URL` that answers `POST /v1/tts` with JSON `{"text": ..., "streaming": false}` and returns a 16-bit mono WAV; with `DEEPGRAM_API_KEY` set, Deepgram is the fallback.

**Model providers.** Anthropic (default, `claude-sonnet-4-6`) and OpenAI or OpenAI-compatible endpoints sit behind one interface in `loeb/llm/`. Only the selected provider's key is needed.

**Exit codes.** `loeb run --ci` exits 0 when the model finished and reported no bugs, 1 when it reported bugs, and 2 on an error or an unfinished run (setup error, crash, iteration cap, refusal). `loeb check` exits 0 when everything passes, 1 when the setup is valid but the app is not fully up, and 2 when the setup is wrong.

## Configuration

- **`loeb.json`:** the target profile. Validated before every run; errors name the field. Reference: [`docs/profile.md`](docs/profile.md).
- **`loeb-target.md`:** free Markdown appended to the system prompt.
- **`.env`:** keys and URLs, never in the profile: `ANTHROPIC_API_KEY` (or `LLM_PROVIDER=openai` with `OPENAI_*`), `WEBSITE_URL`, `API_BASE_URL`, `TEST_EMAIL` / `TEST_PASSWORD`, `GITHUB_REPO` (`owner/name`; run `gh auth login`), `POSTGRES_*`, `REDIS_*`, and optionally `SUPABASE_*`, `TTS_URL`, `DEEPGRAM_API_KEY`, `SLACK_*`, `MAX_TOKENS`, `LOEB_PROFILE`, `LOEB_CONTEXT`. See [`.env.example`](.env.example).

Löb reads `--env-file PATH`, else `./.env`, else the Löb checkout's `.env`. Variables already set in the environment win. Relative paths in a `.env` resolve against that file's directory.

Other `loeb run` flags: `--model`, `--provider anthropic|openai`, `--openai-model`, `--max-iterations` (default 200), `--no-headless`, `--verbose`.

## Limitations

- Exercised mostly against one voice app; the to-do example is the only web app in the repo's tests, and those tests run `loeb check`, not a model.
- `git_diff` compares against `HEAD~1` by default. Postgres and Redis are the only data stores it can query. Token login supports Supabase only.
- Audio injection works only for apps that take microphone input through `getUserMedia` in Chromium.
- Every run costs tokens. The agent can be wrong: it can miss bugs, misjudge behaviour, or file issues that are not bugs. Review what it files.
- `query_db` uses a read-only session, but the agent otherwise has broad reach: it runs `gh`, `docker`, `journalctl` and arbitrary HTTP calls against your API. Point it at a test environment, not production.
- Health checks of kind `unit` and `systemd_units` log sources need `systemctl` / `journalctl --user` (Linux). Sound effects and desktop notifications are macOS-only and skipped elsewhere.

## Development

```bash
make install     # Poetry environment, then `loeb install`
make test        # pytest
make pre-commit  # ruff lint + format
make generated   # after editing loeb/guide.md or loeb/profile.py: rewrites the skill and schema copies
```

To add a tool: implement it in `loeb/tools/` returning a string (prefix failures with `Error:`), add its schema to `TOOL_DEFINITIONS` and a `case` to `ToolRegistry.dispatch()` in `tool_registry.py`, wire it in `run.py` `_build_stack()`, and test it in `tests/`. `tests/fake_llm.py` drives the real agent loop with a scripted provider.

Design notes are in [`docs/design/`](docs/design/).

## License

MIT. See [LICENSE](LICENSE).
