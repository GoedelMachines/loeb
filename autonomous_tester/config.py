import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Core
    anthropic_api_key: str = field(default_factory=lambda: os.environ["ANTHROPIC_API_KEY"])
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))

    # LLM Provider
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic"))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "16384")))

    # OpenAI (for --provider openai)
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))

    # Target app under test: local checkouts of its backend and frontend repos.
    backend_dir: str = field(default_factory=lambda: os.getenv("BACKEND_DIR", ""))
    frontend_dir: str = field(default_factory=lambda: os.getenv("FRONTEND_DIR", ""))

    # Target description: a Markdown file appended to the system prompt (how the
    # app works, DOM selectors, Redis keys, endpoints). See examples/.
    target_context: str = field(default_factory=lambda: os.getenv("TARGET_CONTEXT", ""))
    # Target services: a JSON file listing health checks and log sources. See examples/.
    target_services: str = field(default_factory=lambda: os.getenv("TARGET_SERVICES", ""))

    # GitHub repo ("owner/name") that file_github_issue files into.
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))

    # TTS — a local TTS server first (POST {TTS_URL}/v1/tts -> WAV);
    # Deepgram only as a fallback when a key is set.
    tts_url: str = field(default_factory=lambda: os.getenv("TTS_URL", "http://127.0.0.1:8081"))
    deepgram_api_key: str = field(default_factory=lambda: os.getenv("DEEPGRAM_API_KEY", ""))

    # Slack
    slack_bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    slack_channel: str = field(default_factory=lambda: os.getenv("SLACK_CHANNEL", "#alerts"))

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
