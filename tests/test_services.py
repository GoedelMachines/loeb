from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_tester.tools.services import ServiceManager


@pytest.fixture
def config():
    mock = MagicMock()
    mock.backend_dir = "/tmp/backend"
    mock.frontend_dir = "/tmp/frontend"
    mock.target_services = ""
    mock.api_base_url = "http://localhost:8000"
    mock.website_url = "http://localhost:4321"
    return mock


def test_service_manager_init(config):
    sm = ServiceManager(config)
    assert sm.config == config


def test_stop_all_refuses(config):
    sm = ServiceManager(config)
    assert "Refusing" in sm.stop_all()


@pytest.mark.asyncio
async def test_health_check_url(config):
    sm = ServiceManager(config)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        result = await sm._check_http("http://localhost:8000/api/health")
        assert result is True


@pytest.mark.asyncio
async def test_health_check_url_fails(config):
    sm = ServiceManager(config)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        result = await sm._check_http("http://localhost:8000/api/health")
        assert result is False


def test_load_checks_defaults_without_target_file(config):
    from autonomous_tester.tools.services import DEFAULT_CHECKS, load_checks

    assert load_checks(config) == DEFAULT_CHECKS


def test_load_checks_from_example_target_file(config):
    from pathlib import Path

    from autonomous_tester.tools.services import load_checks

    example = Path(__file__).parent.parent / "examples/voice-assistant/services.json"
    config.target_services = str(example)
    checks = load_checks(config)
    assert checks[0][0].startswith("API")
    assert ("127.0.0.1", 7880) in [c[2] for c in checks]
