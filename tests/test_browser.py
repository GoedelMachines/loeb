from unittest.mock import AsyncMock, MagicMock

import pytest

from loeb.tools.browser import SCREENSHOTS_DIR, BrowserTools


@pytest.fixture
def config(monkeypatch):
    from loeb.profile import Profile

    mock = MagicMock()
    mock.website_url = "http://localhost:4321"
    mock.api_base_url = "http://localhost:8000"
    mock.audio_device_name = "BlackHole 2ch"
    monkeypatch.setattr("loeb.profile.profile_of", lambda c: Profile(
        extra_origins=["https://accounts.example.com"]))
    return mock


def _bt_with_page(config):
    bt = BrowserTools(config)
    bt.page = MagicMock()
    bt.page.goto = AsyncMock()
    bt.page.title = AsyncMock(return_value="Home")
    return bt


def test_browser_tools_init(config):
    bt = BrowserTools(config)
    assert bt.browser is None
    assert bt.page is None


@pytest.mark.asyncio
async def test_screenshot_requires_page(config):
    bt = BrowserTools(config)
    result = await bt.screenshot()
    assert "No browser page open" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "FILE:///home/u/.env", "chrome://settings", "data:text/html,x"]
)
async def test_navigate_refuses_non_web_urls(config, url):
    bt = BrowserTools(config)
    bt.page = MagicMock()
    bt.page.goto = AsyncMock()
    result = await bt.navigate(url)
    assert result.startswith("Error:")
    bt.page.goto.assert_not_called()


@pytest.mark.asyncio
async def test_navigate_allows_http(config):
    bt = BrowserTools(config)
    bt.page = MagicMock()
    bt.page.goto = AsyncMock()
    bt.page.title = AsyncMock(return_value="Home")
    result = await bt.navigate("http://localhost:4321/app")
    assert result.startswith("Navigated to")


@pytest.mark.asyncio
@pytest.mark.parametrize("path,expected", [
    ("/", "http://localhost:4321/"),
    ("/settings?tab=2", "http://localhost:4321/settings?tab=2"),
    ("settings", "http://localhost:4321/settings"),
])
async def test_navigate_resolves_paths_against_the_website(config, path, expected):
    bt = _bt_with_page(config)
    assert (await bt.navigate(path)).startswith(f"Navigated to {expected}")
    assert bt.page.goto.call_args.args[0] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://localhost:8080/",          # another app on the same machine
    "http://localhost:3000/login",
    "https://example.org/",
    "http://localhost:43210/",          # same host, different port
])
async def test_navigate_stays_on_the_app_under_test(config, url):
    bt = _bt_with_page(config)
    result = await bt.navigate(url)
    assert result.startswith("Error:") and "outside the app under test" in result
    bt.page.goto.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://localhost:8000/api/health",  # the API origin
    "https://accounts.example.com/o/oauth",  # profile extra_origins
    "HTTP://LOCALHOST:4321/x",
])
async def test_navigate_allows_the_api_and_extra_origins(config, url):
    bt = _bt_with_page(config)
    assert (await bt.navigate(url)).startswith("Navigated to")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["../escape", "/tmp/abs", "..\\x", ".hidden"])
async def test_screenshot_name_cannot_leave_screenshots_dir(config, name):
    bt = BrowserTools(config)
    bt.page = MagicMock()
    bt.page.screenshot = AsyncMock()
    await bt.screenshot(name)
    path = bt.page.screenshot.call_args.kwargs["path"]
    assert path.parent == SCREENSHOTS_DIR
    assert ".." not in path.name and "/" not in path.name
