"""Tests for TUI dashboard widgets."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import DataTable

from loeb.ui.theme import DUSK, LINEN
from loeb.ui.widgets import (
    ActiveTool,
    BugsPanel,
    StatsBar,
    ThinkingStream,
    ToolLog,
    format_thinking,
)

# ---------------------------------------------------------------------------
# Helper apps
# ---------------------------------------------------------------------------


class StatsBarApp(App):
    def compose(self) -> ComposeResult:
        yield StatsBar()


class ThinkingApp(App):
    def compose(self) -> ComposeResult:
        yield ThinkingStream()


class ActiveToolApp(App):
    def compose(self) -> ComposeResult:
        yield ActiveTool()


class ToolLogApp(App):
    def compose(self) -> ComposeResult:
        yield ToolLog()


class BugsPanelApp(App):
    def compose(self) -> ComposeResult:
        yield BugsPanel()


# ---------------------------------------------------------------------------
# StatsBar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_bar_mounts():
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        assert bar is not None
        assert bar.iteration == 0


@pytest.mark.asyncio
async def test_stats_bar_reactive_updates():
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.iteration = 5
        bar.max_iterations = 50
        bar.input_tokens = 1000
        bar.output_tokens = 500
        bar.bug_count = 2
        bar.phase_index = 3
        await pilot.pause()
        rendered = bar.render()
        assert "5" in rendered
        assert "50" in rendered


@pytest.mark.asyncio
async def test_stats_bar_cost():
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.model = "claude-sonnet-4-6"
        bar.input_tokens = 1_000_000
        bar.output_tokens = 100_000
        await pilot.pause()
        rendered = bar.render()
        assert "$4.5000" in rendered


@pytest.mark.asyncio
async def test_stats_bar_cost_threshold_alert():
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.model = "claude-sonnet-4-6"
        # Start below $0.25 (tier 0)
        bar.input_tokens = 10_000
        bar.output_tokens = 1_000
        await pilot.pause()
        bar.render()  # establish baseline tier
        # Jump to tier 2 (>$1.00)
        bar.input_tokens = 500_000
        bar.output_tokens = 50_000
        await pilot.pause()
        rendered = bar.render()
        assert "↑" in rendered


@pytest.mark.asyncio
async def test_stats_bar_health():
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.tool_successes = 9
        bar.tool_errors = 1
        await pilot.pause()
        rendered = bar.render()
        assert "9/10" in rendered


@pytest.mark.asyncio
async def test_stats_bar_phase_track():
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.phase_index = 3
        await pilot.pause()
        rendered = bar.render()
        assert "browser" in rendered


# ---------------------------------------------------------------------------
# ThinkingStream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thinking_mounts_collapsed():
    async with ThinkingApp().run_test() as pilot:
        panel = pilot.app.query_one(ThinkingStream)
        assert panel.collapsed is True
        assert panel.has_class("collapsed")


@pytest.mark.asyncio
async def test_thinking_streams_without_newlines():
    async with ThinkingApp().run_test() as pilot:
        panel = pilot.app.query_one(ThinkingStream)
        panel.append_text("Hello ")
        panel.append_text("world")
        await pilot.pause()
        rendered = panel.render()
        assert "Hello world" in rendered
        assert panel.collapsed is False


@pytest.mark.asyncio
async def test_thinking_finish_collapses():
    async with ThinkingApp().run_test() as pilot:
        panel = pilot.app.query_one(ThinkingStream)
        panel.append_text("thinking...")
        panel.finish("decided to test login")
        await pilot.pause()
        assert panel.collapsed is True
        assert panel.has_class("collapsed")


@pytest.mark.asyncio
async def test_thinking_summary_has_arrow():
    async with ThinkingApp().run_test() as pilot:
        panel = pilot.app.query_one(ThinkingStream)
        panel.finish("decided to test login")
        await pilot.pause()
        rendered = panel.render()
        assert "▸" in rendered
        assert "decided to test login" in rendered


@pytest.mark.asyncio
async def test_thinking_toggle():
    async with ThinkingApp().run_test() as pilot:
        panel = pilot.app.query_one(ThinkingStream)
        assert panel.collapsed is True
        panel.toggle()
        await pilot.pause()
        assert panel.collapsed is False
        panel.toggle()
        await pilot.pause()
        assert panel.collapsed is True


# ---------------------------------------------------------------------------
# ActiveTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_tool_empty_when_idle():
    async with ActiveToolApp().run_test() as pilot:
        tool = pilot.app.query_one(ActiveTool)
        assert tool.render() == ""


@pytest.mark.asyncio
async def test_active_tool_set_and_clear():
    async with ActiveToolApp().run_test() as pilot:
        tool = pilot.app.query_one(ActiveTool)
        tool.set_tool("navigate", '{"url": "http://localhost:3000"}')
        await pilot.pause()
        rendered = tool.render()
        assert "navigate" in rendered
        tool.clear_tool()
        await pilot.pause()
        assert tool.render() == ""


@pytest.mark.asyncio
async def test_active_tool_truncates():
    async with ActiveToolApp().run_test() as pilot:
        tool = pilot.app.query_one(ActiveTool)
        tool.set_tool("screenshot", "x" * 200)
        await pilot.pause()
        assert "..." in tool.render()


# ---------------------------------------------------------------------------
# ToolLog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_log_adds_rows():
    async with ToolLogApp().run_test() as pilot:
        log = pilot.app.query_one(ToolLog)
        table = pilot.app.query_one(DataTable)
        log.add_entry(1, "git_diff", 150, "diff output...", False, "full diff")
        log.add_entry(2, "navigate", 300, "navigated to /app", False)
        await pilot.pause()
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_tool_log_full_result():
    async with ToolLogApp().run_test() as pilot:
        log = pilot.app.query_one(ToolLog)
        log.add_entry(1, "query_db", 50, "ok", False, "SELECT * FROM ...")
        await pilot.pause()
        assert log.get_full_result(0) == "SELECT * FROM ..."
        assert log.get_full_result(99) == ""


@pytest.mark.asyncio
async def test_tool_log_error_entry():
    async with ToolLogApp().run_test() as pilot:
        log = pilot.app.query_one(ToolLog)
        log.add_entry(1, "check_api", 200, "error: 500", True)
        await pilot.pause()
        assert pilot.app.query_one(DataTable).row_count == 1


# ---------------------------------------------------------------------------
# BugsPanel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bugs_panel_hidden_by_default():
    async with BugsPanelApp().run_test() as pilot:
        panel = pilot.app.query_one(BugsPanel)
        assert not panel.has_class("has-bugs")
        assert panel.render() == ""


@pytest.mark.asyncio
async def test_bugs_panel_shows_on_add():
    async with BugsPanelApp().run_test() as pilot:
        panel = pilot.app.query_one(BugsPanel)
        panel.add_bug("Login button unresponsive")
        await pilot.pause()
        assert panel.has_class("has-bugs")
        assert "Login button unresponsive" in panel.render()


@pytest.mark.asyncio
async def test_bugs_panel_multiple():
    async with BugsPanelApp().run_test() as pilot:
        panel = pilot.app.query_one(BugsPanel)
        panel.add_bug("Bug one")
        panel.add_bug("Bug two")
        await pilot.pause()
        rendered = panel.render()
        assert "Bug one" in rendered
        assert "Bug two" in rendered


# ---------------------------------------------------------------------------
# Theme-aware helper apps
# ---------------------------------------------------------------------------


class DuskStatsBarApp(App):
    theme_name: reactive[str] = reactive("dusk")

    def compose(self) -> ComposeResult:
        yield StatsBar()


class LinenStatsBarApp(App):
    theme_name: reactive[str] = reactive("linen")

    def compose(self) -> ComposeResult:
        yield StatsBar()


class DuskBugsPanelApp(App):
    theme_name: reactive[str] = reactive("dusk")

    def compose(self) -> ComposeResult:
        yield BugsPanel()


class DuskActiveToolApp(App):
    theme_name: reactive[str] = reactive("dusk")

    def compose(self) -> ComposeResult:
        yield ActiveTool()


class LinenActiveToolApp(App):
    theme_name: reactive[str] = reactive("linen")

    def compose(self) -> ComposeResult:
        yield ActiveTool()


# ---------------------------------------------------------------------------
# Theme-aware tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_bar_uses_dusk_colors():
    async with DuskStatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.phase_index = 2
        await pilot.pause()
        rendered = bar.render()
        assert DUSK.success in rendered


@pytest.mark.asyncio
async def test_stats_bar_uses_linen_colors():
    async with LinenStatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.phase_index = 2
        await pilot.pause()
        rendered = bar.render()
        assert LINEN.success in rendered


@pytest.mark.asyncio
async def test_stats_bar_dusk_cost_colors():
    async with DuskStatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.model = "claude-sonnet-4-6"
        bar.input_tokens = 1_000_000
        bar.output_tokens = 100_000
        await pilot.pause()
        rendered = bar.render()
        # cost = $4.50 which is >= $3.00, so error color
        assert DUSK.error in rendered


@pytest.mark.asyncio
async def test_stats_bar_dusk_dim_dark_in_headers():
    async with DuskStatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        await pilot.pause()
        rendered = bar.render()
        assert DUSK.dim_dark in rendered


@pytest.mark.asyncio
async def test_bugs_panel_uses_dusk_error():
    async with DuskBugsPanelApp().run_test() as pilot:
        panel = pilot.app.query_one(BugsPanel)
        panel.add_bug("Crash on load")
        await pilot.pause()
        rendered = panel.render()
        assert DUSK.error in rendered
        assert DUSK.dim_dark in rendered


@pytest.mark.asyncio
async def test_active_tool_uses_dusk_category_colors():
    async with DuskActiveToolApp().run_test() as pilot:
        tool = pilot.app.query_one(ActiveTool)
        tool.set_tool("navigate", '{"url": "http://localhost"}')
        await pilot.pause()
        rendered = tool.render()
        # navigate -> brw category
        assert DUSK.category_colors["brw"] in rendered


@pytest.mark.asyncio
async def test_active_tool_uses_linen_category_colors():
    async with LinenActiveToolApp().run_test() as pilot:
        tool = pilot.app.query_one(ActiveTool)
        tool.set_tool("navigate", '{"url": "http://localhost"}')
        await pilot.pause()
        rendered = tool.render()
        assert LINEN.category_colors["brw"] in rendered


@pytest.mark.asyncio
async def test_stats_bar_falls_back_to_dusk_without_theme_name():
    """Widgets default to DUSK when app has no theme_name attr."""
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.phase_index = 2
        await pilot.pause()
        rendered = bar.render()
        # StatsBarApp has no theme_name, so _t defaults to DUSK
        assert DUSK.success in rendered


@pytest.mark.asyncio
async def test_stats_bar_pipeline_separator():
    """Pipeline should have a visual separator between completed and pending."""
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        bar.phase_index = 3
        await pilot.pause()
        rendered = bar.render()
        assert "─" in rendered


@pytest.mark.asyncio
async def test_stats_bar_section_headers():
    """Section headers should be present."""
    async with StatsBarApp().run_test() as pilot:
        bar = pilot.app.query_one(StatsBar)
        await pilot.pause()
        rendered = bar.render()
        assert "METRICS" in rendered
        assert "PIPELINE" in rendered
        assert "HEALTH" in rendered


# ---------------------------------------------------------------------------
# format_thinking
# ---------------------------------------------------------------------------


def test_format_thinking_bold():
    result = format_thinking("I need to **check the login** flow")
    assert "[bold]check the login[/bold]" in result
    assert "**" not in result


def test_format_thinking_italic():
    result = format_thinking("this is *important* to verify")
    assert "[italic]important[/italic]" in result
    assert result.count("*") == 0


def test_format_thinking_bullets():
    result = format_thinking("Steps:\n- check login\n- verify redirect\n- done")
    assert "  • check login" in result
    assert "  • verify redirect" in result


def test_format_thinking_numbered():
    result = format_thinking("1. first step\n2. second step")
    assert "  1. first step" in result
    assert "  2. second step" in result


def test_format_thinking_escapes_brackets():
    result = format_thinking("found [error] in console")
    assert "\\[error]" in result


def test_format_thinking_backticks():
    result = format_thinking("A `_rescue_stale_redirect` safety net")
    assert "[bold]_rescue_stale_redirect[/bold]" in result
    assert "`" not in result


def test_format_thinking_mixed():
    text = "**Plan:**\n- *analyze* the diff\n- check [API] response"
    result = format_thinking(text)
    assert "[bold]Plan:[/bold]" in result
    assert "  • [italic]analyze[/italic] the diff" in result
    assert "\\[API]" in result


def test_unpriced_model_never_shows_a_dollar_figure():
    from loeb.agent import cost_label
    from loeb.ui.widgets import StatsBar

    assert cost_label("deepseek-v4-flash", 0.0) == "unpriced"
    assert cost_label("claude-sonnet-4-6", 1.5) == "$1.5000"
    bar = StatsBar()
    bar.model = "deepseek-v4-flash"
    bar.input_tokens = 400_000
    rendered = bar.render()
    assert "unpriced" in rendered and "$" not in rendered
