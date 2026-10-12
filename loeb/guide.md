# Setting up Löb for this project (loeb {version})

Löb is an end-to-end tester: an LLM drives the running app in a real browser, checks
the effects in the database, logs and API, and reports bugs. It learns the app from
two files in the app's repo, which you, the coding agent, write by reading the code:

- `loeb.json`: the profile. Repos, health checks, log sources, pages and selectors,
  the sign-in form. Validated against a schema (`loeb schema` prints it).
- `loeb-target.md`: what a new tester would need to know, in prose. Appended to Löb's
  system prompt.

Secrets and URLs go in `.env` (or the environment), never in `loeb.json`.

You are done when `loeb check --json` reports `"exit_code": 0`.

## Steps

1. In the app's root, run `loeb init`. It writes `loeb.json`, `loeb-target.md` and a
   `.env` template. It never overwrites an existing `.env`; it prints the lines to add.
   If `loeb check` later reports that Chromium is missing, run `loeb install`.
2. Read the repo: how each service starts and on which port, the routes and pages, the
   sign-in flow, the database tables and Redis keys that user actions change, the logs.
3. Fill in `loeb.json` (fields below). Take every selector from the markup or the
   templates in the repo, never from guesswork. Prefer ids, `name` attributes and
   `data-testid`. Ask the user before adding test ids to the app.
4. Write `loeb-target.md` (template below).
5. Set `.env`: `WEBSITE_URL`, `API_BASE_URL`, the model key, and whatever else applies
   (list below). Ask the user for values you cannot find: the API key, the test
   account's password. Do not commit `.env`.
6. Start the app, or ask the user to. Then loop until it passes:

       loeb check --json

   Every failed result has a `fix`. Exit 2 means the setup is wrong (key, browser,
   profile, repo, a selector that matches nothing, a failed sign-in): fix the files.
   Exit 1 means the app is not fully up: start what is down. `loeb check` makes no LLM
   call and costs nothing; run it as often as you like.
7. Tell the user it is ready, and how to run it:

       loeb run "Test sign-up with a new email"     # a dashboard in the terminal
       loeb run --ci "Test sign-up"                 # no UI; exit 0 pass, 1 bugs, 2 error

   Each run calls the model and costs tokens. A run writes `runs/<timestamp>.json`.

## loeb.json

```json
{
  "app_kind": "web",
  "context": "loeb-target.md",
  "repos": {"api": "services/api", "web": "apps/web"},
  "api_health_path": "/api/health",
  "checks": [
    {"name": "API", "kind": "http", "probe": "api", "fix": "make api"},
    {"name": "Web", "kind": "http", "probe": "website", "fix": "npm run dev"},
    {"name": "Postgres", "kind": "tcp", "probe": "127.0.0.1:5432", "fix": "docker compose up -d db"}
  ],
  "systemd_units": [],
  "docker_containers": {"db": "app-postgres-1"},
  "pages": {"/": ["#new-todo", "ul.todo-list"], "/settings": ["form#profile"]},
  "auth": {
    "login_path": "/login",
    "email_selector": "input[name=email]",
    "password_selector": "input[name=password]",
    "submit_selector": "button[type=submit]",
    "success_url_glob": "**/dashboard**"
  }
}
```

| Field | Meaning |
|---|---|
| `app_kind` | `"web"` (default) or `"voice"`: users talk to the app through the microphone. Voice adds audio tools. |
| `context` | Path to `loeb-target.md`. |
| `repos` | `{name: path}` of repos Löb may `git diff`, relative to `loeb.json`. Any number, or none. |
| `api_health_path` | Path the `"api"` probe requests on `API_BASE_URL`. |
| `checks` | Health checks. `kind` `http` (`probe`: a URL, `"api"` or `"website"`; any HTTP answer passes), `tcp` (`"host:port"`), or `unit` (a `systemd --user` unit). `fix` is shown when it fails. |
| `systemd_units`, `docker_containers` | Where `read_logs` reads logs: unit names, `{alias: container}`. |
| `pages` | `{path: [selectors]}`. `loeb check` opens each page and requires every selector to match. List what a tester relies on. |
| `extra_origins` | Origins besides the website and API that the agent may `navigate` to (e.g. an OAuth provider). Usually empty. |
| `auth` | The sign-in form. Leave it out if the app has none. `loeb check` signs in when `TEST_EMAIL` and `TEST_PASSWORD` are set. |
| `transcription` | Voice apps only: `{"user_selector": ..., "agent_selector": ...}`, where the app shows what was heard and said. |

Unknown fields are errors. Full schema: `loeb schema`.

## loeb-target.md

```markdown
## How the app works
What it is for, who uses it, and the main flows (sign in -> dashboard -> create an order).

## Pages and selectors
For each page: its path, and the selectors for the buttons, inputs and status elements
a tester uses, with what each does.

## Data to verify
Postgres tables and Redis key patterns that change when users act, with the columns or
values that show it worked.

## API endpoints
The endpoints behind the main flows, with what they return.

## Known quirks
Slow pages, flaky elements, test-only accounts, anything a new tester would trip on.
```

## .env

| Variable | Needed for |
|---|---|
| `ANTHROPIC_API_KEY` | the model (default provider) |
| `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | an OpenAI-compatible model instead |
| `WEBSITE_URL`, `API_BASE_URL` | where the app runs |
| `TEST_EMAIL`, `TEST_PASSWORD` | signing in (a test account, not a real user's) |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `query_db` (offered and checked only when at least one is set) |
| `REDIS_HOST`, `REDIS_PORT` | `query_redis` (offered and checked only when at least one is set) |
| `GITHUB_REPO` | filing issues (`owner/name`; needs `gh auth login`) |
| `LOEB_PROFILE`, `LOEB_CONTEXT` | a profile or context somewhere other than `./loeb.json` |

Relative paths in `.env` resolve against the file's own directory.

## If this guide and the installed loeb disagree

This text matches loeb {version}. If `loeb --version` prints something else, run
`loeb guide` and follow that instead.
