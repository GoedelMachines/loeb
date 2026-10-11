"""Tests for TUI screens."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from autonomous_tester.ui.screens import InteractiveSetupScreen, ToolDetailScreen


class ToolDetailApp(App):
    """Minimal app that pushes a ToolDetailScreen on mount."""

    def __init__(self, tool_name: str, full_result: str) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._full_result = full_result

    def compose(self) -> ComposeResult:
        yield Static("base")

    def on_mount(self) -> None:
        self.push_screen(ToolDetailScreen(self._tool_name, self._full_result))


class SetupApp(App):
    """Minimal app that pushes an InteractiveSetupScreen on mount."""

    def compose(self) -> ComposeResult:
        yield Static("base")

    def on_mount(self) -> None:
        self.push_screen(InteractiveSetupScreen())


@pytest.mark.asyncio
async def test_tool_detail_screen_shows_content() -> None:
    app = ToolDetailApp("git_diff", "diff --git a/foo.py")
    async with app.run_test() as pilot:
        # Verify the modal screen is mounted
        screen = app.screen
        assert isinstance(screen, ToolDetailScreen)

        # Press escape to dismiss
        await pilot.press("escape")

        # After dismiss, we should be back at the base screen
        assert not isinstance(app.screen, ToolDetailScreen)


@pytest.mark.asyncio
async def test_interactive_setup_screen_mounts() -> None:
    app = SetupApp()
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, InteractiveSetupScreen)

        # Verify key widgets are present
        mode_select = screen.query_one("#mode-select")
        assert mode_select is not None

        services_select = screen.query_one("#services-select")
        assert services_select is not None

        browser_select = screen.query_one("#browser-select")
        assert browser_select is not None

        start_btn = screen.query_one("#start-btn")
        assert start_btn is not None

        cancel_btn = screen.query_one("#cancel-btn")
        assert cancel_btn is not None

        await pilot.pause()
