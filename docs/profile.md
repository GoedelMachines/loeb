# Target profile reference

The target profile is one JSON file that describes the app under test. `loeb init`
writes a starting one, a coding agent usually fills it in (`loeb guide`), and
`loeb check` validates it. The schema is `loeb/profile.py`; `loeb schema` prints it
as JSON Schema (also in [`schema/loeb.schema.json`](../schema/loeb.schema.json), which a
profile may reference with `"$schema"`). Unknown fields are errors, so a typo fails
`loeb check` and the run's setup instead of being ignored.

**Where Löb looks:** `LOEB_PROFILE`, else `TARGET_SERVICES` (the older name), else
`./loeb.json`. Relative paths inside the profile resolve against the profile file's
directory.

Secrets and URLs (`ANTHROPIC_API_KEY`, `WEBSITE_URL`, `API_BASE_URL`, `GITHUB_REPO`,
`TEST_EMAIL`, `POSTGRES_*`, `REDIS_*`, …) stay in the environment or `.env`, never in the
profile. See `.env.example`.

**Environment names.** Variables specific to Löb carry the `LOEB_` prefix:
`LOEB_PROFILE` and `LOEB_CONTEXT`. The rest keep the names their tools already use
(`ANTHROPIC_API_KEY`, `OPENAI_*`, `POSTGRES_*`, `REDIS_*`, `GITHUB_REPO`) or describe the
app rather than Löb (`WEBSITE_URL`, `API_BASE_URL`, `TEST_EMAIL`, `TEST_PASSWORD`).
`TARGET_SERVICES`, `BACKEND_DIR` and `FRONTEND_DIR` are read only to load profiles
written before the `repos` map existed.

## Fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `app_kind` | `"web"` or `"voice"` | `"web"` | `"voice"`: the app is talked to through the microphone. Adds voice instructions to the system prompt and offers `inject_audio`, `inject_silence` and (with `transcription`) `read_transcription`. |
| `context` | path | none | Markdown appended to the system prompt: how the app works, its pages, selectors, data. `LOEB_CONTEXT` overrides it. |
| `repos` | `{name: path}` | `{}` | Repos whose diffs `git_diff` can read. Any number, including none (then `git_diff` is not offered). If absent, `BACKEND_DIR` / `FRONTEND_DIR` are used as `backend` / `frontend`. |
| `api_health_path` | string starting with `/` | `/api/health` | Path that the probe `"api"` hits on `API_BASE_URL`. |
| `checks` | list of checks | API + website | Health checks run by `start_services` and `loeb check`. |
| `systemd_units` | list of strings | `[]` | Log sources `read_logs` reads via `journalctl --user -u`. |
| `docker_containers` | `{alias: container}` | `{}` | Log sources `read_logs` reads via `docker logs`. Any other name falls back to `docker compose logs` in the first repo. |
| `auth` | object | unset | The sign-in form `login(method="browser")` fills, and `loeb check` tries. Unset: the app has no sign-in form. |
| `transcription` | object | unset | Where `read_transcription` reads what the user and the app said. Needs `"app_kind": "voice"`. If unset, the tool is not offered. |
| `pages` | `{path: [selector]}` | `{}` | Pages `loeb check` opens, each with the CSS selectors that must match once it loads. Keys are paths under `WEBSITE_URL` or full URLs. |
| `extra_origins` | `[origin]` | `[]` | `navigate` opens only `WEBSITE_URL`'s and `API_BASE_URL`'s origins (paths resolve against `WEBSITE_URL`), plus these, e.g. `"https://accounts.google.com"` for an OAuth sign-in. Redirects and clicks are not restricted. |

### `checks[]`

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Label shown in the report. |
| `kind` | yes | `http`, `tcp` or `unit`. |
| `probe` | depends on kind | `http`: a full `http(s)://` URL, `"api"` (`API_BASE_URL` + `api_health_path`), `"website"` (`WEBSITE_URL`), or `null` (older rule: `"api"` if the name starts with `API`, else `"website"`). `tcp`: `["host", port]` or `"host:port"`. `unit`: a `systemd --user` unit name (Linux only). |
| `fix` | no | Free text shown next to a failed check, such as the command that starts the service. It is not run or expanded. |

An `http` check passes on any HTTP answer, including a 404. A `tcp` check passes when
it can connect.

### `auth`

All five fields have defaults (`/sign-in`, `input#email`, `input#password`,
`button[type='submit']`, `**/app**`); set the ones your app differs in:

```json
"auth": {
  "login_path": "/login",
  "email_selector": "input[name=email]",
  "password_selector": "input[name=password]",
  "submit_selector": "button[type=submit]",
  "success_url_glob": "**/dashboard**"
}
```

`login()` defaults to `browser`, unless `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set;
then it defaults to `token`, which injects a Supabase session. It needs `TEST_EMAIL` and
`TEST_PASSWORD`.

`loeb check` opens `login_path`, checks the three selectors match, and, when
`TEST_EMAIL` and `TEST_PASSWORD` are set, signs in and waits for `success_url_glob`.

### `pages`

```json
"pages": {"/": ["#new-todo", "ul.todo-list"], "/settings": ["form#profile"]}
```

List the elements a tester relies on, so a renamed id fails `loeb check` instead of
failing a run halfway.

### `transcription`

```json
"transcription": {"user_selector": ".caption--user", "agent_selector": ".caption--bot"}
```

Either selector may be left out. These elements appear only during a session, so
`loeb check` does not test them.

## `loeb check`

Runs without an LLM call and spends no tokens. In order: the provider key, Chromium,
the profile and repos; then, unless `--no-services`, the health checks, Postgres and
Redis, every `pages` selector, and the sign-in form.

| Exit | Meaning |
|---|---|
| 0 | everything passed |
| 1 | the setup is valid but the app is not fully up (a health check fails, a page does not load) |
| 2 | the setup is wrong: missing key or browser, invalid profile, missing repo, a selector that matches nothing, a page that returns 4xx/5xx, a sign-in that fails |

`loeb check --json` prints one object. Schema version 1:

```json
{
  "schema": 1,
  "loeb_version": "0.1.0",
  "exit_code": 2,
  "ok": false,
  "env": "/path/to/app/.env",
  "results": [
    {"check": "selector", "name": "/ #new-todo", "status": "fail",
     "detail": "no element matches after 5s",
     "fix": "fix the selector in the profile (read the page's markup)"}
  ]
}
```

- `check`: `provider`, `browser`, `profile`, `repo`, `service`, `postgres`, `redis`,
  `page`, `selector`, `login` or `transcription`.
- `status`: `pass`, `fail`, `skip` or `warn`. Only `fail` changes the exit code.
- `fix`: what to do, on failures; otherwise `null`.

Fields are only ever added within a schema version.

## A minimal profile

```json
{
  "context": "loeb-target.md",
  "repos": {"app": "."},
  "checks": [
    {"name": "API", "kind": "http", "probe": "api", "fix": "npm run api"},
    {"name": "Web", "kind": "http", "probe": "website", "fix": "npm run dev"},
    {"name": "Postgres", "kind": "tcp", "probe": "127.0.0.1:5432"}
  ]
}
```

A worked example is [`examples/todo/loeb.json`](../examples/todo/loeb.json).
