from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loeb.tools.services import ServiceManager


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


@pytest.mark.asyncio
async def test_default_checks_without_profile(config):
    config.profile = None
    config.target_profile = ""
    sm = ServiceManager(config)
    sm._check_http = AsyncMock(return_value=True)
    out = await sm.start_all()
    assert "✓ API" in out and "✓ Website" in out
