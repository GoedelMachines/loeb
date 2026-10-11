"""Tests for the main TUI application."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_tester.ui.app import TesterApp


@pytest.mark.asyncio
async def test_app_mounts():
    agent = MagicMock()
    agent.run = AsyncMock()
    agent.on_event = None
    app = TesterApp(agent=agent, prompt="test", headless=True)
    async with app.run_test():
        assert app.query_one("#stats-bar") is not None
        assert app.query_one("#tool-log") is not None
        assert app.query_one("#thinking-panel") is not None
        assert app.query_one("#active-tool") is not None
        assert app.query_one("#bugs-panel") is not None


@pytest.mark.asyncio
async def test_app_header_shows_lob():
    agent = MagicMock()
    agent.run = AsyncMock()
    agent.on_event = None
    app = TesterApp(agent=agent, prompt="test", headless=True)
    async with app.run_test():
        from autonomous_tester.ui.app import HeaderBar

        header = app.query_one(HeaderBar)
        rendered = header.render()
        assert "LÖB" in rendered
        assert "AUTONOMOUS" not in rendered


@pytest.mark.asyncio
async def test_theme_toggle_keybind():
    agent = MagicMock()
    agent.run = AsyncMock()
    agent.on_event = None
    app = TesterApp(agent=agent, prompt="test", headless=True)
    async with app.run_test() as pilot:
        assert app.theme_name == "dusk"
        await pilot.press("l")
        assert app.theme_name == "linen"
        await pilot.press("l")
        assert app.theme_name == "dusk"


@pytest.mark.asyncio
async def test_mode_toggle_keybind():
    agent = MagicMock()
    agent.run = AsyncMock()
    agent.on_event = None
    app = TesterApp(agent=agent, prompt="test", headless=True)
    async with app.run_test() as pilot:
        assert app.layout_mode == "instrument"
        await pilot.press("m")
        assert app.layout_mode == "focus"
        await pilot.press("m")
        assert app.layout_mode == "instrument"


@pytest.mark.asyncio
async def test_auto_exit_when_agent_finishes():
    """Direct (one-shot) mode must exit the app when the agent run ends.

    Regression: a capped/completed run left the TUI redrawing forever when
    launched detached (2026-08-25, 250-iter run spun ~95 min at 100% CPU).
    """
    agent = MagicMock()
    agent.run = AsyncMock()
    agent.on_event = None
    agent.registry.browser = None
    app = TesterApp(agent=agent, prompt="test", headless=True, auto_exit=True)
    async with app.run_test() as pilot:
        for _ in range(100):  # up to ~5s for the worker thread to finish
            await pilot.pause(0.05)
            if not app.is_running:
                break
    assert not app.is_running


@pytest.mark.asyncio
async def test_no_auto_exit_by_default():
    """Interactive mode (default) keeps the dashboard open after the run."""
    agent = MagicMock()
    agent.run = AsyncMock()
    agent.on_event = None
    agent.registry.browser = None
    app = TesterApp(agent=agent, prompt="test", headless=True)
    async with app.run_test() as pilot:
        await pilot.pause(0.5)
        assert app.is_running
