"""Tests for Löb Focus mode — AI-native minimal layout."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from loeb.ui.focus import (
    FocusAction,
    FocusLayout,
    FocusThinking,
    MetricsStrip,
)


class FocusApp(App):
    def compose(self) -> ComposeResult:
        yield FocusLayout()


class ThinkingApp(App):
    def compose(self) -> ComposeResult:
        yield FocusThinking()


class ActionApp(App):
    def compose(self) -> ComposeResult:
        yield FocusAction()


class MetricsApp(App):
    def compose(self) -> ComposeResult:
        yield MetricsStrip()


# ---------------------------------------------------------------------------
# FocusLayout — mounts with only thinking + action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_focus_layout_mounts():
    async with FocusApp().run_test() as pilot:
        layout = pilot.app.query_one(FocusLayout)
        assert layout is not None
        assert pilot.app.query_one(FocusThinking) is not None
        assert pilot.app.query_one(FocusAction) is not None
        assert pilot.app.query_one(MetricsStrip) is not None


# ---------------------------------------------------------------------------
# FocusThinking — simple current thought, no history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thinking_starts_waiting():
    async with ThinkingApp().run_test() as pilot:
        thinking = pilot.app.query_one(FocusThinking)
        rendered = thinking.render()
        assert "waiting" in rendered


@pytest.mark.asyncio
async def test_thinking_streams_text():
    async with ThinkingApp().run_test() as pilot:
        thinking = pilot.app.query_one(FocusThinking)
        thinking.append_text("analyzing login flow...")
        await pilot.pause()
        rendered = thinking.render()
        assert "analyzing login flow" in rendered


@pytest.mark.asyncio
async def test_thinking_finishes_to_summary():
    async with ThinkingApp().run_test() as pilot:
        thinking = pilot.app.query_one(FocusThinking)
        thinking.append_text("analyzing...")
        thinking.finish("decided to test login")
        await pilot.pause()
        rendered = thinking.render()
        assert "decided to test login" in rendered


@pytest.mark.asyncio
async def test_thinking_summary_persists():
    """Summary stays visible, never goes blank."""
    async with ThinkingApp().run_test() as pilot:
        thinking = pilot.app.query_one(FocusThinking)
        thinking.finish("some summary")
        await pilot.pause()
        rendered = thinking.render()
        assert "some summary" in rendered
        assert rendered != ""


@pytest.mark.asyncio
async def test_thinking_replaces_previous():
    """New thought replaces the old — no history accumulation."""
    async with ThinkingApp().run_test() as pilot:
        thinking = pilot.app.query_one(FocusThinking)
        thinking.finish("first thought")
        thinking.finish("second thought")
        await pilot.pause()
        rendered = thinking.render()
        assert "second thought" in rendered
        # First thought is gone — no history chain
        assert "first thought" not in rendered


@pytest.mark.asyncio
async def test_thinking_streaming_replaces_summary():
    """Active streaming replaces the previous summary."""
    async with ThinkingApp().run_test() as pilot:
        thinking = pilot.app.query_one(FocusThinking)
        thinking.finish("old summary")
        thinking.append_text("now streaming...")
        await pilot.pause()
        rendered = thinking.render()
        assert "now streaming" in rendered
        assert "old summary" not in rendered


# ---------------------------------------------------------------------------
# FocusAction — single current/last tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_shows_active_tool():
    async with ActionApp().run_test() as pilot:
        action = pilot.app.query_one(FocusAction)
        action.set_tool("navigate", '{"url": "http://localhost"}')
        await pilot.pause()
        rendered = action.render()
        assert "navigate" in rendered
        assert "localhost" in rendered


@pytest.mark.asyncio
async def test_action_shows_last_result():
    async with ActionApp().run_test() as pilot:
        action = pilot.app.query_one(FocusAction)
        action.complete_tool("git_diff", 89, "Recent commits: abc1234", False)
        await pilot.pause()
        rendered = action.render()
        assert "git_diff" in rendered
        assert "89ms" in rendered
        assert "Recent commits" in rendered


@pytest.mark.asyncio
async def test_action_last_result_persists():
    """Last result stays visible even when no tool is active."""
    async with ActionApp().run_test() as pilot:
        action = pilot.app.query_one(FocusAction)
        action.complete_tool("check_api", 200, "HTTP 200 OK", False)
        await pilot.pause()
        rendered = action.render()
        assert "check_api" in rendered
        assert "HTTP 200 OK" in rendered


@pytest.mark.asyncio
async def test_action_shows_error():
    async with ActionApp().run_test() as pilot:
        action = pilot.app.query_one(FocusAction)
        action.complete_tool("check_api", 200, "error: 500", True)
        await pilot.pause()
        rendered = action.render()
        assert "✗" in rendered


@pytest.mark.asyncio
async def test_action_replaces_previous():
    """Only the last completed tool is shown — no stack."""
    async with ActionApp().run_test() as pilot:
        action = pilot.app.query_one(FocusAction)
        action.complete_tool("git_diff", 89, "3 files changed", False)
        action.complete_tool("navigate", 1660, "Page loaded", False)
        await pilot.pause()
        rendered = action.render()
        assert "navigate" in rendered
        assert "Page loaded" in rendered
        # git_diff is gone — no stack
        assert "git_diff" not in rendered


@pytest.mark.asyncio
async def test_action_empty_at_start():
    """Action renders empty when nothing has happened."""
    async with ActionApp().run_test() as pilot:
        action = pilot.app.query_one(FocusAction)
        rendered = action.render()
        assert rendered == ""


# ---------------------------------------------------------------------------
# MetricsStrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_strip_mounts():
    async with MetricsApp().run_test() as pilot:
        strip = pilot.app.query_one(MetricsStrip)
        assert strip is not None
        rendered = strip.render()
        assert "iter" in rendered
        assert "time" in rendered
        assert "cost" in rendered


@pytest.mark.asyncio
async def test_metrics_strip_updates():
    async with MetricsApp().run_test() as pilot:
        strip = pilot.app.query_one(MetricsStrip)
        strip.iteration = 5
        strip.max_iterations = 100
        strip.elapsed = "01:30"
        strip.cost = "$0.1234"
        strip.phase = "browser"
        await pilot.pause()
        rendered = strip.render()
        assert "5" in rendered
        assert "100" in rendered
        assert "01:30" in rendered
        assert "$0.1234" in rendered
        assert "browser" in rendered


@pytest.mark.asyncio
async def test_metrics_strip_shows_bugs():
    async with MetricsApp().run_test() as pilot:
        strip = pilot.app.query_one(MetricsStrip)
        strip.bug_count = 2
        await pilot.pause()
        rendered = strip.render()
        assert "2 bugs" in rendered
