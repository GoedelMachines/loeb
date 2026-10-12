from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loeb.tools.backend import BackendTools


@pytest.fixture
def config():
    mock = MagicMock()
    mock.api_base_url = "http://localhost:8000"
    mock.redis_host = "localhost"
    mock.redis_port = 6379
    mock.postgres_dsn = "postgresql://postgres:postgres@localhost:5432/app"
    mock.backend_dir = "/tmp/backend"
    return mock


def test_backend_tools_init(config):
    bt = BackendTools(config)
    assert bt.config.api_base_url == "http://localhost:8000"


@pytest.mark.asyncio
async def test_check_api_get(config):
    bt = BackendTools(config)
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = MagicMock(
            status_code=200,
            text='{"ok": true}',
            headers={"content-type": "application/json"},
        )
        result = await bt.check_api("GET", "/api/health")
        assert "200" in result
        assert "ok" in result


@pytest.mark.asyncio
async def test_read_logs(config):
    mock_result = MagicMock()
    mock_result.stdout = "worker log line 1\nworker log line 2"
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result):
        bt = BackendTools(config)
        result = await bt.read_logs("worker", 10)
        assert "worker log line 1" in result


@pytest.mark.asyncio
async def test_read_logs_refuses_option_like_service(config):
    with patch("subprocess.run") as run:
        result = await BackendTools(config).read_logs("--help", 10)
    assert result.startswith("Error:")
    run.assert_not_called()


@pytest.mark.asyncio
async def test_read_logs_compose_service_after_double_dash(config):
    mock_result = MagicMock(stdout="ok", stderr="", returncode=0)
    with patch("subprocess.run", return_value=mock_result) as run:
        await BackendTools(config).read_logs("worker", 10)
    cmd = run.call_args.args[0]
    assert cmd[-2:] == ["--", "worker"]
