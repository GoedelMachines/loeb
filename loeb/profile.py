"""The target profile: everything Löb needs to know about the app under test.

A profile is one JSON file (default `loeb.json`, or LOEB_PROFILE). Relative paths in
it resolve against the file's own directory. Secrets and URLs stay in the environment
(.env); the profile describes the app's shape:

    {
      "app_kind": "web",                           # or "voice": audio tools and prompt
      "context": "loeb-target.md",                 # Markdown appended to the system prompt
      "repos": {"api": "../api", "web": "../web"}, # repos git_diff can read (any number)
      "api_health_path": "/api/health",
      "checks": [                                  # start_services health checks
        {"name": "API", "kind": "http", "probe": "api", "fix": "make api"},
        {"name": "Postgres", "kind": "tcp", "probe": ["127.0.0.1", 5432]},
        {"name": "Worker", "kind": "unit", "probe": "app-worker"}
      ],
      "systemd_units": ["app-worker"],             # read_logs via journalctl --user
      "docker_containers": {"db": "app-postgres"}, # read_logs via docker logs
      "auth": {"login_path": "/login", "email_selector": "#email", ...},
      "transcription": {"user_selector": ".you", "agent_selector": ".bot"},
      "pages": {"/": ["#new-todo", "ul.todos"]}    # what `loeb check` verifies live
    }

An older services-only file (TARGET_SERVICES, no "repos") still loads: its repos come
from BACKEND_DIR / FRONTEND_DIR, as before. docs/profile.md documents every field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

DEFAULT_PROFILE_NAME = "loeb.json"


class ProfileError(Exception):
    """The profile is missing, unreadable or invalid. The message is user-facing."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Check(_Strict):
    name: str
    kind: Literal["http", "tcp", "unit"]
    # http: a URL, "api" (API_BASE_URL + api_health_path), "website" (WEBSITE_URL), or
    #       null (legacy: "api" if the name starts with "API", else "website").
    # tcp:  [host, port] or "host:port".   unit: a systemd --user unit name.
    probe: str | list | None = None
    fix: str = ""

    @model_validator(mode="after")
    def _probe_matches_kind(self) -> Check:
        p = self.probe
        if self.kind == "http":
            if p is None or p in ("api", "website"):
                return self
            if not isinstance(p, str) or urlparse(p).scheme not in ("http", "https"):
                raise ValueError(
                    f"http probe must be a http(s) URL, 'api', 'website' or null, got {p!r}"
                )
        elif self.kind == "tcp":
            if isinstance(p, str) and p.rpartition(":")[2].isdigit():
                host, _, port = p.rpartition(":")
                p = [host, int(port)]
            if not (isinstance(p, list) and len(p) == 2 and isinstance(p[0], str)
                    and isinstance(p[1], int) and not isinstance(p[1], bool)):
                raise ValueError(f"tcp probe must be [host, port] or 'host:port', got {p!r}")
            self.probe = p
        elif not isinstance(p, str) or not p:
            raise ValueError(f"unit probe must be a systemd unit name, got {p!r}")
        return self


class Auth(_Strict):
    """The sign-in form login(method='browser') fills. Unset in the profile: the app has
    no sign-in form (login works only through Supabase token injection, if configured)."""

    login_path: str = "/sign-in"
    email_selector: str = "input#email"
    password_selector: str = "input#password"
    submit_selector: str = "button[type='submit']"
    success_url_glob: str = "**/app**"


class Transcription(_Strict):
    """Where read_transcription finds what the user and the app said. Unset: the tool is
    not offered to the model."""

    user_selector: str | None = None
    agent_selector: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.user_selector or self.agent_selector)


class Profile(_Strict):
    # "voice": the app is talked to through the microphone; the audio and transcription
    # tools and the voice instructions are offered. "web": they are not.
    # Optional pointer to the JSON Schema (`loeb schema`), for editors; ignored.
    schema_ref: str | None = Field(default=None, alias="$schema")
    app_kind: Literal["web", "voice"] = "web"
    context: str | None = None
    repos: dict[str, str] = {}
    api_health_path: str = "/api/health"
    checks: list[Check] = []
    systemd_units: list[str] = []
    docker_containers: dict[str, str] = {}
    auth: Auth | None = None
    transcription: Transcription = Transcription()
    # navigate opens only WEBSITE_URL's and API_BASE_URL's origins, plus these (e.g. an
    # OAuth provider the sign-in flow redirects through). Each is an http(s) origin.
    extra_origins: list[str] = []

    @field_validator("extra_origins")
    @classmethod
    def _origins_are_http(cls, origins: list[str]) -> list[str]:
        for o in origins:
            if urlparse(o).scheme not in ("http", "https") or not urlparse(o).hostname:
                raise ValueError(f"{o!r} is not an http(s) origin like https://accounts.example.com")
        return origins
    # Pages `loeb check` opens, each with the selectors that must match once it loads:
    # {"/": ["#new-todo", "ul.todos"]}. Keys are paths under WEBSITE_URL or full URLs.
    pages: dict[str, list[str]] = {}

    # Where it was loaded from (None: no profile file, environment only).
    _source: Path | None = PrivateAttr(default=None)

    @property
    def source(self) -> Path | None:
        return self._source

    @field_validator("repos")
    @classmethod
    def _repo_names(cls, v: dict[str, str]) -> dict[str, str]:
        for name, path in v.items():
            if not name or not path:
                raise ValueError("repo names and paths must be non-empty")
        return v

    @model_validator(mode="after")
    def _transcription_needs_voice(self) -> Profile:
        if self.transcription.configured and self.app_kind != "voice":
            raise ValueError('transcription selectors need "app_kind": "voice"')
        return self

    @field_validator("pages")
    @classmethod
    def _page_keys(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for page, selectors in v.items():
            if not (page.startswith("/") or urlparse(page).scheme in ("http", "https")):
                raise ValueError(f"page {page!r} must be a path starting with '/' or a URL")
            if not all(isinstance(s, str) and s.strip() for s in selectors):
                raise ValueError(f"page {page!r}: selectors must be non-empty strings")
        return v

    @field_validator("api_health_path")
    @classmethod
    def _health_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError(f"api_health_path must start with '/', got {v!r}")
        return v


def _format_errors(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        loc = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e["loc"]).lstrip(".")
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "extra_forbidden":
            msg = "unknown field (typo?)"
        lines.append(f"  {loc or '(top level)'}: {msg}")
    return "\n".join(lines)


def find_profile_path(config) -> Path | None:
    """LOEB_PROFILE, else the legacy TARGET_SERVICES, else ./loeb.json if it exists."""
    for attr in ("target_profile", "target_services"):
        value = getattr(config, attr, "")
        if isinstance(value, str) and value:
            return Path(value).expanduser()
    default = Path(DEFAULT_PROFILE_NAME)
    return default if default.is_file() else None


def parse_profile(data: object, source: Path | None = None) -> Profile:
    if not isinstance(data, dict):
        raise ProfileError(f"{source}: the profile must be a JSON object")
    try:
        profile = Profile.model_validate(data)
    except ValidationError as e:
        raise ProfileError(f"{source or 'profile'} is invalid:\n{_format_errors(e)}") from None
    profile._source = source
    return profile


def load_profile(config) -> Profile:
    """Load, validate and resolve the target profile for `config`. Raises ProfileError."""
    path = find_profile_path(config)
    if path is None:
        profile = Profile()
    else:
        try:
            text = path.read_text()
        except OSError as e:
            raise ProfileError(f"cannot read target profile {path}: {e.strerror}") from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProfileError(f"{path} is not valid JSON: {e}") from None
        profile = parse_profile(data, source=path)

    base = path.resolve().parent if path is not None else Path.cwd()

    def resolve(p: str) -> str:
        return str((base / Path(p).expanduser()).resolve())

    if profile.repos:
        profile.repos = {name: resolve(p) for name, p in profile.repos.items()}
    else:  # legacy: the two repo dirs come from the environment
        for name in ("backend", "frontend"):
            value = getattr(config, f"{name}_dir", "")
            if isinstance(value, str) and value:
                profile.repos[name] = str(Path(value).expanduser().resolve())

    # LOEB_CONTEXT, when set, overrides the profile's "context".
    env_context = getattr(config, "target_context", "")
    if isinstance(env_context, str) and env_context:
        profile.context = str(Path(env_context).expanduser().resolve())
    elif profile.context:
        profile.context = resolve(profile.context)
    return profile


def profile_of(config) -> Profile:
    """The profile attached to config at startup, or a fresh load (tests, ad-hoc use)."""
    profile = getattr(config, "profile", None)
    if isinstance(profile, Profile):
        return profile
    return load_profile(config)


def profile_problems(profile: Profile) -> list[str]:
    """Static checks beyond the schema: referenced files and repos exist."""
    from loeb.tools.git import check_repo

    problems = []
    if profile.context and not Path(profile.context).is_file():
        problems.append(f"context file {profile.context} does not exist")
    for name, path in profile.repos.items():
        problem = check_repo(path)
        if problem:
            problems.append(f"repo '{name}': {problem.removeprefix('Error: ')}")
    return problems

