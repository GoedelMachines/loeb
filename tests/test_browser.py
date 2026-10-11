from unittest.mock import MagicMock

import pytest

from autonomous_tester.tools.browser import BrowserTools


@pytest.fixture
def config():
    mock = MagicMock()
    mock.website_url = "http://localhost:4321"
    mock.audio_device_name = "BlackHole 2ch"
    return mock


def test_browser_tools_init(config):
    bt = BrowserTools(config)
    assert bt.browser is None
    assert bt.page is None


@pytest.mark.asyncio
async def test_screenshot_requires_page(config):
    bt = BrowserTools(config)
    result = await bt.screenshot()
    assert "No browser page open" in result
