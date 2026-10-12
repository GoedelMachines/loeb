# Löb — Original Design

> This is the original design. The implementation diverged in two places: audio is injected by overriding `getUserMedia` in the page (no virtual audio device), and Löb verifies an externally managed stack instead of starting and stopping it. The README describes the current behaviour.

## Problem

Current agentic testing tools (Spur, Momentic, QA.tech) test web UIs by clicking buttons and checking DOM state. The target is a voice AI assistant — its core interaction is audio over WebRTC, its value is in backend tool execution (email, calendar, web search), and its UI includes real-time elements (mute, zen mode, file upload) during active voice sessions. No existing tool can test this.

## Solution

A single AI agent in a tool-use loop that:
1. Reads the git diff to understand what changed
2. Spins up the full app stack
3. Opens the website in a real browser
4. Interacts with the app as a user would — including speaking to it via real-time TTS through a virtual audio device
5. Verifies backend side effects (emails sent, DB state, logs)
6. Investigates and reports bugs with full evidence

## Architecture

```
make test-e2e
       │
       ▼
┌──────────────────────────────────────────────────┐
│                  Test Agent                       │
│            (LLM in a tool-use loop)              │
│                                                   │
│  Tools available:                                 │
│  ├── git_diff()        — read what changed       │
│  ├── start_services()  — spin up the stack       │
│  ├── browser_*()       — Playwright actions       │
│  │   ├── navigate, click, type, screenshot       │
│  │   ├── inject_audio(text)                      │
│  │   ├── read_transcription()                    │
│  │   └── upload_file(path)                       │
│  ├── check_api()       — hit backend endpoints   │
│  ├── read_logs()       — docker/agent/API logs   │
│  ├── read_console()    — browser console output  │
│  ├── query_db()        — check postgres/redis    │
│  ├── file_github_issue() — with evidence         │
│  └── send_slack()      — alert the team          │
│                                                   │
│  No fixed plan. The agent reasons, acts,          │
│  observes, and adapts at every step.              │
└──────────────────────────────────────────────────┘
```

## Key Design Decisions

### Agentic Loop, Not Plan→Execute

The agent decides what to do at every step. If something unexpected happens — a crash, a weird UI state, an error in the console — it investigates on the spot. It reads logs, takes screenshots, checks the DB, and narrows down the cause before filing an issue. There is no static test plan.

### Real Voice via Virtual Audio Device

The agent speaks to the app using real audio:

```
Agent decides what to say
       │
       ▼
TTS generates audio (TTS API)
       │
       ▼
Audio routed to virtual audio device (BlackHole on macOS)
       │
       ▼
Browser picks it up as normal microphone input
       │
       ▼
LiveKit captures it like any real user's voice
       │
       ▼
Agent monitors DOM for transcription/subtitle updates
```

Playwright launches Chrome with `--use-fake-device-for-media-stream` pointed at the virtual audio device. Zero changes to the website code under test.

The agent can say anything it wants in real-time — it's not limited to pre-recorded clips. If it decides to test an edge case mid-session ("what if I ask to email someone not in my contacts?"), it just speaks it.

### Side Effect Verification

After the app responds, the agent doesn't trust the UI alone. It verifies:
- **Redis** — tool task status (completed/failed)
- **Docker logs** — Huey worker output, ReasoningToolCaller decisions
- **PostgreSQL** — conversation turns saved correctly
- **API** — history endpoint returns the right data
- **Browser console** — no JS errors, WebRTC connection healthy

### Smart Reporting

**When a bug is found:**
- GitHub Issue with: commit hash, steps to reproduce, screenshots, logs, console output, likely root cause
- Slack message to alerts channel with link to the issue

**When everything passes:**
- Slack summary: green, commit hash, what was tested, duration

## Components

### 1. Service Manager
Starts and stops the full app stack:
- `docker-compose up` (Redis, Postgres, Huey worker, browser service, filestorage)
- `poetry run python main.py dev` (LiveKit agent)
- `poetry run uvicorn api:app` (FastAPI server)
- Health checks: waits for all services to respond before testing begins
- Tears everything down after the test run

### 2. Audio System
- TTS: a TTS API (Deepgram)
- Virtual audio device: BlackHole (macOS) for routing TTS output to browser mic input
- The agent calls `inject_audio("some phrase")` which:
  1. Generates audio via TTS API
  2. Streams it to the virtual audio device
  3. Waits for transcription to appear in the DOM

### 3. Browser Tools (Playwright)
Standard Playwright actions exposed as agent tools:
- `navigate(url)` — go to a page
- `click(selector_or_text)` — click an element
- `type(selector, text)` — type into an input
- `screenshot()` — capture the current page
- `read_transcription()` — get current transcription text from the DOM
- `read_console()` — get browser console output
- `upload_file(path)` — trigger file upload dialog

### 4. Backend Tools
- `check_api(method, path, params)` — HTTP request to the FastAPI server
- `query_db(sql)` — query the local PostgreSQL (conversation history)
- `query_redis(pattern)` — check Redis keys (user config, task status)
- `read_logs(service, lines)` — docker logs for any container

### 5. Reporter
- `file_github_issue(title, body, labels)` — via `gh` CLI
- `send_slack(message)` — via Slack Bot Token

## Example Test Run

```
Agent reads git diff:
  "SessionPage.tsx: modified mute toggle logic"
  "reasoning_tool_caller.py: added retry on OpenAI timeout"

Agent thinks: "Two changes — UI mute button and backend retry logic.
              Let me test both."

1. start_services()
2. navigate("http://localhost:4321")
3. Sign in (click Google OAuth, handle auth flow)
4. Start voice session (click VoiceOrb)
5. inject_audio("Hello, can you hear me?")
6. read_transcription() → agent responded ✓
7. click("mute button")
8. inject_audio("Can you still hear me?")
9. read_transcription() → no new response ✓ (mute works)
10. click("mute button") again to unmute
11. inject_audio("Send an email to John saying I'll be late")
12. read_transcription() → "I've sent the email"
13. read_logs("worker", 50) → ReasoningToolCaller invoked Gmail ✓
14. query_redis("status:*") → task completed ✓
15. check_api("GET", "/api/history?limit=1") → turn saved ✓

Agent thinks: "Let me test the retry logic — I'll check the logs
              for timeout handling"

16. read_logs("worker", 100) → look for retry patterns
17. No timeout occurred in this run — but the code path exists.
    Agent notes this as "not exercised, needs dedicated test."

18. send_slack("✅ Commit abc123f — mute toggle + retry logic.
    2 features tested, 0 issues found. Retry path not exercised.")
```

## Tech Stack

- **Agent runtime:** Claude API (tool-use loop)
- **Browser automation:** Playwright (Python)
- **TTS:** Deepgram
- **Virtual audio:** BlackHole (macOS), PulseAudio virtual sink (Linux/CI)
- **Reporting:** GitHub CLI (`gh`), Slack Bot Token
- **Language:** Python (matches the target backend)

## Running

```bash
# Manual
make test-e2e

# Later: GitHub Actions on push
# .github/workflows/autonomous-test.yml
```

## Phase 2: Mobile (Future)

Add Maestro as a third track for testing a mobile client on an iOS simulator. Same agent, same tools, different UI driver.
