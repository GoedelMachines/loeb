<!--
Example target description (TARGET_CONTEXT). Löb appends this file to its system
prompt. It describes the voice-assistant app Löb was built against; replace the
selectors, keys, endpoints and services with your own app's.
-->

## How the app works
- A voice assistant accessed via a web app at the website URL
- Users sign in, click "Start Talking" on /app, which navigates to /app/session
- The session page has a voice orb, mute button, stop button, subtitles
- Users speak → the app listens via LiveKit/WebRTC → STT → LLM → responds via TTS
- Tool calls (email, calendar, web search) are executed asynchronously by a Huey worker

## Key DOM selectors
- Mute button: `.session-page__btn--mute` (gets `.session-page__btn--muted` class when muted)
- Stop button: `.session-page__btn--stop`
- Upload button: `.session-page__btn--upload`
- Zen mode: `.session-page__btn--zen`
- CC/Subtitles toggle: `.session-page__top-btn`
- User subtitle text: `.session-page__user-text`
- Agent subtitle text: `.session-page__agent-text`
- Status text: `.session-page__status`
- Start Talking CTA: `.app-home__cta`
- Sign-in email: `input#email`
- Sign-in password: `input#password`

## Key Redis patterns
- `tool:*` — tool task status (hash with status, result)
- `user_config:*` — per-room user config
- `active_room:*` — user's active room
- `huey:worker:heartbeat` — worker alive signal

## Key API endpoints
- GET /api/health — stack health check
- GET /api/history?limit=N — recent conversation turns
- POST /api/session — create a new LiveKit session

## Architecture
Two repos: a Python backend (`BACKEND_DIR`: LiveKit agent, FastAPI server, Huey workers,
tool execution) and a web frontend (`FRONTEND_DIR`).

```
Web app (frontend)
    │
    ├── POST /api/session (Bearer JWT) ──► FastAPI ──► Redis user config
    │                                        Returns {token, url, roomName}
    │
    └── WebRTC (LiveKit) ──► LiveKit agent
                                │
                                ├── STT → LLM → TTS
                                │
                                └── Tool calls → Huey worker → tools
                                                    (web search, email, calendar,
                                                     sandboxed code, browser)
```

- **Auth**: Supabase JWT on all endpoints.
- **Conversation history**: local PostgreSQL; user data and auth: Supabase.
