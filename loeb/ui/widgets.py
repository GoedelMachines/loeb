"""Löb TUI widgets — autonomous test observer.

Sidebar panel layout. Vertical phase timeline. Animated indicators.
The interface breathes.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from loeb.agent import DEFAULT_PRICING, MODEL_PRICING, cost_label
from loeb.ui.theme import DUSK, THEMES, Theme

# ---------------------------------------------------------------------------
# Thinking text formatter
# ---------------------------------------------------------------------------

_CODE_RE = __import__("re").compile(r"`([^`]+)`")
_BOLD_RE = __import__("re").compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = __import__("re").compile(r"\*(.+?)\*")
_BULLET_RE = __import__("re").compile(r"^- ", __import__("re").MULTILINE)
_NUMBERED_RE = __import__("re").compile(r"^(\d+)\. ", __import__("re").MULTILINE)


def format_thinking(text: str) -> str:
    """Convert markdown-ish thinking text to Rich markup."""
    # Escape existing Rich markup brackets so [foo] doesn't break rendering
    text = text.replace("[", "\\[")
    # `code` → Rich reverse (monospace feel)
    text = _CODE_RE.sub(r"[bold]\1[/bold]", text)
    # **bold** → Rich bold
    text = _BOLD_RE.sub(r"[bold]\1[/bold]", text)
    # *italic* → Rich italic
    text = _ITALIC_RE.sub(r"[italic]\1[/italic]", text)
    # - bullet → • bullet
    text = _BULLET_RE.sub("  • ", text)
    # 1. numbered → indented
    text = _NUMBERED_RE.sub(r"  \1. ", text)
    return text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASES = ["diff", "services", "browser", "login", "test", "verify", "report"]

TOOL_CATEGORY = {
    "git_diff": "git",
    "start_services": "svc",
    "stop_services": "svc",
    "launch_browser": "brw",
    "navigate": "brw",
    "click": "brw",
    "type_text": "brw",
    "screenshot": "brw",
    "get_page_text": "brw",
    "get_element_state": "brw",
    "wait_for_selector": "brw",
    "upload_file": "brw",
    "login": "brw",
    "read_transcription": "brw",
    "read_console": "brw",
    "inject_audio": "aud",
    "inject_silence": "aud",
    "check_api": "api",
    "query_db": "api",
    "query_redis": "api",
    "read_logs": "api",
    "file_github_issue": "out",
    "send_slack": "out",
}

CATEGORY_MARKER = {
    "git": "◇",
    "svc": "□",
    "brw": "◉",
    "aud": "∿",
    "api": "⊙",
    "out": "△",
}


# ---------------------------------------------------------------------------
# StatsBar — vertical sidebar panel with metrics + phase timeline
# ---------------------------------------------------------------------------


class StatsBar(Static):
    """Sidebar stats: metrics block, vertical phase timeline, health."""

    iteration: reactive[int] = reactive(0)
    max_iterations: reactive[int] = reactive(200)
    start_time: reactive[float] = reactive(0.0)
    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    cache_read_tokens: reactive[int] = reactive(0)
    cache_creation_tokens: reactive[int] = reactive(0)
    tool_successes: reactive[int] = reactive(0)
    tool_errors: reactive[int] = reactive(0)
    bug_count: reactive[int] = reactive(0)
    phase_index: reactive[int] = reactive(1)
    model: reactive[str] = reactive("claude-sonnet-4-6")

    @property
    def _t(self) -> Theme:
        """Current theme."""
        try:
            name = getattr(self.app, "theme_name", "dusk")
            return THEMES.get(name, DUSK)
        except Exception:
            return DUSK

    def __init__(self, **kwargs):
        super().__init__(id="stats-bar", **kwargs)
        self._last_cost_tier = 0
        self._cost_alert_ticks = 0

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        if self._cost_alert_ticks > 0:
            self._cost_alert_ticks -= 1
        self.refresh()

    def _elapsed(self) -> str:
        if self.start_time == 0.0:
            return "--:--"
        s = int(time.time() - self.start_time)
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def _cost(self) -> float:
        p = MODEL_PRICING.get(self.model, DEFAULT_PRICING)
        return (
            self.input_tokens * p[0]
            + self.output_tokens * p[1]
            + self.cache_read_tokens * p[2]
            + self.cache_creation_tokens * p[3]
        ) / 1_000_000

    def render(self) -> str:
        cost = self._cost()
        tok_k = (self.input_tokens + self.output_tokens) / 1000
        t = self._t

        if cost < 0.25:
            cc = t.success
            tier = 0
        elif cost < 1.00:
            cc = t.primary
            tier = 1
        elif cost < 3.00:
            cc = t.warning
            tier = 2
        else:
            cc = t.error
            tier = 3

        # Detect cost tier change — flash indicator for 5 seconds
        if tier > self._last_cost_tier and self._last_cost_tier >= 0:
            self._cost_alert_ticks = 5
        self._last_cost_tier = tier

        label = cost_label(self.model, cost)
        cost_str = f"[{cc}]{label}[/]"
        if self._cost_alert_ticks > 0:
            cost_str = f"[bold {cc}]↑ {label}[/]"

        # --- Metrics ---
        lines = [
            f"[{t.dim_dark}]── METRICS ──[/]",
            f" [{t.dim_mid}]iter[/]  [bold]{self.iteration}[/]/{self.max_iterations}",
            f" [{t.dim_mid}]time[/]  {self._elapsed()}",
            f" [{t.dim_mid}]cost[/]  {cost_str}",
            f" [{t.dim_mid}]tok[/]   {tok_k:.0f}k",
            "",
        ]

        # --- Pipeline (vertical phase timeline) ---
        lines.append(f"[{t.dim_dark}]── PIPELINE ──[/]")
        for i, name in enumerate(PHASES, 1):
            if i < self.phase_index:
                lines.append(f" [{t.success}]●[/] [{t.dim_mid}]{name}[/]")
            elif i == self.phase_index:
                if i > 1:
                    lines.append(f" [{t.dim_dark}]─────────────[/]")
                lines.append(f" [{t.primary}]◉[/] [bold {t.primary}]{name}[/]")
            else:
                lines.append(f" [{t.dim_dark}]○ {name}[/]")
        lines.append("")

        # --- Health ---
        total = self.tool_successes + self.tool_errors
        if total > 0:
            rate = self.tool_successes / total
            filled = int(rate * 10)
            bar = "█" * filled + "░" * (10 - filled)
            hc = t.success if rate >= 0.9 else t.warning if rate >= 0.7 else t.error
            lines.append(f"[{t.dim_dark}]── HEALTH ───[/]")
            lines.append(f" [{hc}]{bar}[/]")
            lines.append(f" [{t.dim_mid}]{self.tool_successes}/{total}[/]")
        else:
            lines.append(f"[{t.dim_dark}]── HEALTH ───[/]")
            lines.append(f" [{t.dim_mid}]waiting[/]")

        if self.bug_count > 0:
            lines.append("")
            lines.append(f" [bold {t.error}]▲ {self.bug_count} bugs[/]")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ThinkingStream — watch the mind work
# ---------------------------------------------------------------------------


class ThinkingStream(Static):
    """Flowing thinking text with blinking cursor.

    Accumulates into prose, not lines. Collapses to a dim summary
    when thought finishes. Violet accent when expanded.
    """

    collapsed: reactive[bool] = reactive(True)
    _cursor_visible: reactive[bool] = reactive(True)

    @property
    def _t(self) -> Theme:
        """Current theme."""
        try:
            name = getattr(self.app, "theme_name", "dusk")
            return THEMES.get(name, DUSK)
        except Exception:
            return DUSK

    def __init__(self, **kwargs):
        super().__init__(id="thinking-panel", **kwargs)
        self._buffer: list[str] = []
        self._summary = ""

    def on_mount(self) -> None:
        self._apply_state()
        self.set_interval(0.5, self._blink_cursor)

    def _apply_state(self) -> None:
        self.remove_class("collapsed", "expanded")
        self.add_class("collapsed" if self.collapsed else "expanded")

    def _blink_cursor(self) -> None:
        if not self.collapsed and self._buffer:
            self._cursor_visible = not self._cursor_visible
            self.refresh()

    def watch_collapsed(self, value: bool) -> None:
        self._apply_state()
        self.refresh()

    def append_text(self, text: str) -> None:
        self._buffer.append(text)
        if self.collapsed:
            self.collapsed = False
        self.refresh()

    def finish(self, summary: str) -> None:
        self._summary = summary
        self._buffer.clear()
        self.collapsed = True

    def toggle(self) -> None:
        self.collapsed = not self.collapsed

    def render(self) -> str:
        if self.collapsed:
            if self._summary:
                t = self._t
                summary = format_thinking(self._summary)
                return f"[{t.thinking}]▸[/] [{t.text_secondary}]{summary}[/]"
            return f"[{self._t.dim_mid}]  ...[/]"

        full = "".join(self._buffer)
        if not full.strip():
            return f"[italic {self._t.dim_light}]  thinking...[/]"
        visible = full[-800:] if len(full) > 800 else full
        if len(full) > 800:
            visible = "..." + visible
        visible = format_thinking(visible)
        cursor = "█" if self._cursor_visible else " "
        return f"{visible}[bold {self._t.primary}]{cursor}[/]"


# ---------------------------------------------------------------------------
# ActiveTool — pulsing indicator
# ---------------------------------------------------------------------------


class ActiveTool(Static):
    """Currently executing tool with a pulsing marker."""

    tool_name: reactive[str] = reactive("")
    tool_input: reactive[str] = reactive("")
    _pulse_frame: reactive[int] = reactive(0)

    _PULSE = ["◉", "◎", "○", "◎"]

    @property
    def _t(self) -> Theme:
        """Current theme."""
        try:
            name = getattr(self.app, "theme_name", "dusk")
            return THEMES.get(name, DUSK)
        except Exception:
            return DUSK

    def __init__(self, **kwargs):
        super().__init__(id="active-tool", **kwargs)

    def on_mount(self) -> None:
        self.set_interval(0.3, self._tick)

    def _tick(self) -> None:
        if self.tool_name:
            self._pulse_frame = (self._pulse_frame + 1) % len(self._PULSE)
            self.refresh()

    def set_tool(self, name: str, input_preview: str) -> None:
        self.tool_name = name
        self.tool_input = input_preview
        self._pulse_frame = 0

    def clear_tool(self) -> None:
        self.tool_name = ""
        self.tool_input = ""

    def render(self) -> str:
        if not self.tool_name:
            return ""
        cat = TOOL_CATEGORY.get(self.tool_name, "")
        color = self._t.category_colors.get(cat, self._t.text_muted)
        marker = self._PULSE[self._pulse_frame]
        preview = self.tool_input
        if len(preview) > 80:
            preview = preview[:80] + "..."
        return f"[{color}]{marker} {self.tool_name}[/]  [{self._t.text_muted}]{preview}[/]"


# ---------------------------------------------------------------------------
# ToolLog — geometric feed
# ---------------------------------------------------------------------------


class ToolLog(Static):
    """Scrollable tool history with category markers."""

    @property
    def _t(self) -> Theme:
        """Current theme."""
        try:
            name = getattr(self.app, "theme_name", "dusk")
            return THEMES.get(name, DUSK)
        except Exception:
            return DUSK

    def __init__(self, **kwargs):
        super().__init__(id="tool-log", **kwargs)
        self._full_results: list[str] = []

    def compose(self):
        table = DataTable(cursor_type="row", show_header=False)
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("num", "tool", "time", "result")

    def add_entry(
        self,
        num: int,
        name: str,
        elapsed_ms: int,
        preview: str,
        is_error: bool,
        full_result: str = "",
    ) -> None:
        table = self.query_one(DataTable)
        t = self._t

        cat = TOOL_CATEGORY.get(name, "")
        color = t.category_colors.get(cat, t.dim_mid)
        marker = t.category_markers.get(cat, "·")

        num_text = Text(f"{num:>3}", style=t.dim_mid)
        name_text = Text(f"{marker} {name}", style=f"bold {color}")

        time_style = t.dim_mid if elapsed_ms < 500 else t.warning if elapsed_ms < 3000 else t.error
        time_text = Text(f"{elapsed_ms:>5}ms", style=time_style)

        if is_error:
            result_text = Text(
                preview,
                style=f"bold {t.error}",
                overflow="ellipsis",
                no_wrap=True,
            )
        else:
            result_text = Text(
                preview,
                style=t.text_muted,
                overflow="ellipsis",
                no_wrap=True,
            )

        table.add_row(num_text, name_text, time_text, result_text)
        table.scroll_end(animate=False)
        self._full_results.append(full_result)

    def get_full_result(self, row_index: int) -> str:
        if 0 <= row_index < len(self._full_results):
            return self._full_results[row_index]
        return ""


# ---------------------------------------------------------------------------
# BugsPanel — sharp alerts
# ---------------------------------------------------------------------------


class BugsPanel(Static):
    """Bugs filed. Hidden until first bug."""

    @property
    def _t(self) -> Theme:
        """Current theme."""
        try:
            name = getattr(self.app, "theme_name", "dusk")
            return THEMES.get(name, DUSK)
        except Exception:
            return DUSK

    def __init__(self, **kwargs):
        super().__init__(id="bugs-panel", **kwargs)
        self._bugs: list[str] = []

    def add_bug(self, title: str) -> None:
        self._bugs.append(title)
        self.add_class("has-bugs")
        self.refresh()

    def render(self) -> str:
        if not self._bugs:
            return ""
        t = self._t
        lines = [f"[{t.dim_dark}]── BUGS ─────[/]"]
        for i, bug_title in enumerate(self._bugs, 1):
            lines.append(f" [bold {t.error}]▲{i}[/] {bug_title}")
        return "\n".join(lines)
