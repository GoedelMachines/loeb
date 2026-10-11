import os
from unittest.mock import patch

from autonomous_tester.config import Config


def test_config_provider_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    cfg = Config()
    assert cfg.provider == "anthropic"
    assert cfg.max_tokens == 16384
    assert cfg.openai_api_key == ""
    assert cfg.openai_base_url == ""
    assert cfg.openai_model == "gpt-4o"


def test_config_provider_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "o3")
    monkeypatch.setenv("MAX_TOKENS", "8192")
    cfg = Config()
    assert cfg.provider == "openai"
    assert cfg.openai_api_key == "sk-test"
    assert cfg.openai_model == "o3"
    assert cfg.max_tokens == 8192


def test_config_loads_from_env():
    env = {
        "ANTHROPIC_API_KEY": "test-key",
        "BACKEND_DIR": "/tmp/backend",
        "FRONTEND_DIR": "/tmp/frontend",
        "DEEPGRAM_API_KEY": "dg-key",
        "SLACK_BOT_TOKEN": "xoxb-test",
        "SLACK_CHANNEL": "#test",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "app",
        "POSTGRES_USER": "app",
        "POSTGRES_PASSWORD": "postgres",
        "API_BASE_URL": "http://localhost:8000",
        "WEBSITE_URL": "http://localhost:4321",
    }
    with patch.dict(os.environ, env, clear=False):
        from autonomous_tester.config import Config

        cfg = Config()
        assert cfg.anthropic_api_key == "test-key"
        assert cfg.backend_dir == "/tmp/backend"
        assert cfg.redis_host == "localhost"
        assert cfg.redis_port == 6379
        assert cfg.postgres_dsn == "postgresql://app:postgres@localhost:5432/app"
        assert cfg.website_url == "http://localhost:4321"
