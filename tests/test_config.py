import os
from unittest.mock import patch

from loeb.config import Config


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
        from loeb.config import Config

        cfg = Config()
        assert cfg.anthropic_api_key == "test-key"
        assert cfg.backend_dir == "/tmp/backend"
        assert cfg.redis_host == "localhost"
        assert cfg.redis_port == 6379
        assert cfg.postgres_dsn == "postgresql://app:postgres@localhost:5432/app"
        assert cfg.website_url == "http://localhost:4321"


def test_config_without_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert Config().anthropic_api_key == ""


def test_openai_provider_needs_no_anthropic_key(monkeypatch):
    from loeb.llm import OpenAIProvider, create_provider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = Config()
    cfg.provider = "openai"
    assert isinstance(create_provider(cfg), OpenAIProvider)


def test_anthropic_provider_without_key_is_a_clear_error(monkeypatch):
    import pytest

    from loeb.llm import create_provider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY required"):
        create_provider(Config())


def test_unknown_provider_is_rejected(monkeypatch):
    import pytest

    from loeb.llm import create_provider

    cfg = Config()
    cfg.provider = "gemini"
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(cfg)


# --- .env loading -------------------------------------------------------------

import pytest  # noqa: E402

from loeb.config import PATH_VARS, load_env  # noqa: E402


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    # load_env writes os.environ directly; give each test its own copy.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in (*PATH_VARS, "ANTHROPIC_API_KEY", "GITHUB_REPO"):
        os.environ.pop(var, None)
    monkeypatch.setattr("loeb.config._CHECKOUT_ENV", tmp_path / "no-checkout.env")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_env_loaded_from_working_directory(clean_env):
    (clean_env / ".env").write_text("ANTHROPIC_API_KEY=sk-from-cwd\n")
    assert load_env().name == ".env"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-cwd"


def test_real_environment_wins_over_env_file(clean_env, monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "real/env")
    (clean_env / ".env").write_text("GITHUB_REPO=file/value\n")
    load_env()
    assert os.environ["GITHUB_REPO"] == "real/env"


def test_relative_paths_in_env_file_resolve_against_its_directory(clean_env, monkeypatch):
    app = clean_env / "myapp"
    app.mkdir()
    (app / "loeb.env").write_text("LOEB_PROFILE=loeb.json\nLOEB_CONTEXT=/abs/t.md\n")
    monkeypatch.chdir(clean_env)  # run from somewhere else
    load_env(str(app / "loeb.env"))
    assert os.environ["LOEB_PROFILE"] == str(app / "loeb.json")
    assert os.environ["LOEB_CONTEXT"] == "/abs/t.md"


def test_missing_explicit_env_file_is_an_error(clean_env):
    with pytest.raises(ValueError, match="does not exist"):
        load_env(str(clean_env / "nope.env"))


def test_no_env_file_is_fine(clean_env):
    assert load_env() is None
