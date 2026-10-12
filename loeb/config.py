import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass
class Config:
    # Core
    # Only the selected provider's key is required; create_provider checks it.
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # LLM Provider
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic"))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "16384")))

    # OpenAI (for --provider openai)
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))

    # Legacy repo dirs, used only when the profile has no "repos" map.
    backend_dir: str = field(default_factory=lambda: os.getenv("BACKEND_DIR", ""))
    frontend_dir: str = field(default_factory=lambda: os.getenv("FRONTEND_DIR", ""))

    # Target description: a Markdown file appended to the system prompt (how the
    # app works, pages, Redis keys, endpoints). Overrides the profile's "context".
    target_context: str = field(default_factory=lambda: os.getenv("LOEB_CONTEXT", ""))
    # Target profile: a JSON file describing the app (repos, health checks, log sources,
    # sign-in form, transcription selectors). Default: ./loeb.json if present.
    # TARGET_SERVICES is the older name for the same file. See docs/profile.md.
    target_profile: str = field(default_factory=lambda: os.getenv("LOEB_PROFILE", ""))
    target_services: str = field(default_factory=lambda: os.getenv("TARGET_SERVICES", ""))
    # The loaded profile (loeb.profile.Profile), set once at startup.
    profile: object = None

    # GitHub repo ("owner/name") that file_github_issue files into.
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))

    # TTS — a local TTS server first (POST {TTS_URL}/v1/tts -> WAV);
    # Deepgram only as a fallback when a key is set.
    tts_url: str = field(default_factory=lambda: os.getenv("TTS_URL", "http://127.0.0.1:8081"))
    deepgram_api_key: str = field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))

    # Slack
    slack_bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    slack_channel: str = field(default_factory=lambda: os.getenv("SLACK_CHANNEL", "#alerts"))

    # Redis and Postgres are opt-in: the probes and query tools exist only when at least one
    # of their variables is set, so a web app with no data store gets neither.
    redis_configured: bool = field(
        default_factory=lambda: any(os.getenv(k) for k in ("REDIS_HOST", "REDIS_PORT"))
    )
    postgres_configured: bool = field(
        default_factory=lambda: any(
            os.getenv(k)
            for k in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
                      "POSTGRES_PASSWORD")
        )
    )

    # Redis
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))

    # Postgres
    postgres_host: str = field(default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"))
    postgres_port: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    postgres_db: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "postgres"))
    postgres_user: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "postgres"))
    postgres_password: str = field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "postgres")
    )

    # API & Website
    api_base_url: str = field(
        default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:8000")
    )
    website_url: str = field(
        default_factory=lambda: os.getenv("WEBSITE_URL", "http://localhost:4321")
    )

    # Virtual audio device
    audio_device_name: str = field(
        default_factory=lambda: os.getenv("AUDIO_DEVICE_NAME", "BlackHole 2ch")
    )

    # Test user (email/password)
    test_email: str = field(default_factory=lambda: os.getenv("TEST_EMAIL", ""))
    test_password: str = field(default_factory=lambda: os.getenv("TEST_PASSWORD", ""))

    # Supabase (optional; only for login(method="token") session injection)
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Variables holding paths. A relative value read from a .env file means "relative to
# that file", so the file works from any working directory.
PATH_VARS = ("LOEB_PROFILE", "TARGET_SERVICES", "LOEB_CONTEXT", "BACKEND_DIR", "FRONTEND_DIR")

# A checkout's own .env (the repo root), used only when the working directory has none.
_CHECKOUT_ENV = Path(__file__).resolve().parent.parent / ".env"


def load_env(env_file: str | None = None) -> Path | None:
    """Load a .env into os.environ without overriding variables already set.

    Order: `env_file` if given (it must exist), else ./.env, else the Löb checkout's
    .env. Returns the file loaded, or None.
    """
    if env_file:
        path = Path(env_file).expanduser()
        if not path.is_file():
            raise ValueError(f"env file {env_file} does not exist")
    else:
        path = next((p for p in (Path(".env"), _CHECKOUT_ENV) if p.is_file()), None)
        if path is None:
            return None
    base = path.resolve().parent
    for key, value in dotenv_values(path).items():
        if key in os.environ or value is None:
            continue
        if key in PATH_VARS and value and not Path(value).expanduser().is_absolute():
            value = str(base / value)
        os.environ[key] = value
    return path
