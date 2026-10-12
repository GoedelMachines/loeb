import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loeb.agent import Agent
from loeb.config import Config
from loeb.tool_registry import TOOL_DEFINITIONS, ToolRegistry
from loeb.tools.audio import AudioSystem
from loeb.tools.backend import BackendTools
from loeb.tools.browser import BrowserTools
from loeb.tools.reporter import Reporter
from loeb.tools.services import ServiceManager


@pytest.fixture
def mock_config():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        return Config()


def test_full_wiring(mock_config):
    """Verify all components wire together without errors."""
    services = ServiceManager(mock_config)
    browser = BrowserTools(mock_config)
    audio = AudioSystem(mock_config)
    backend = BackendTools(mock_config)
    reporter = Reporter(mock_config)

    registry = ToolRegistry(
        services=services,
        browser=browser,
        audio=audio,
        backend=backend,
        reporter=reporter,
        config=mock_config,
    )

    provider = MagicMock()
    agent = Agent(mock_config, registry, provider)
    assert agent.max_iterations == 200
    assert len(TOOL_DEFINITIONS) >= 20


@pytest.mark.asyncio
async def test_tool_dispatch_routes_correctly(mock_config):
    """Verify tool dispatch reaches the right handler."""
    services = MagicMock()
    browser = MagicMock()
    audio = MagicMock()
    backend = MagicMock()
    reporter = MagicMock()

    browser.screenshot = AsyncMock(return_value="screenshot.png")
    audio.inject_audio = AsyncMock(return_value="Audio injected")
    backend.check_api = AsyncMock(return_value="HTTP 200")
    backend.query_redis = AsyncMock(return_value="key: value")

    registry = ToolRegistry(
        services=services,
        browser=browser,
        audio=audio,
        backend=backend,
        reporter=reporter,
        config=mock_config,
    )

    assert "screenshot.png" in await registry.dispatch("screenshot", {})
    assert "Audio injected" in await registry.dispatch("inject_audio", {"text": "hello"})
    assert "HTTP 200" in await registry.dispatch(
        "check_api", {"method": "GET", "path": "/api/health"}
    )
    assert "key: value" in await registry.dispatch("query_redis", {"pattern": "tool:*"})
    assert "Unknown tool" in await registry.dispatch("fake_tool", {})
