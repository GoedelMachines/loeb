"""Löb Focus mode — AI-native minimal interface.

Focus mode provides comfort that the agent is working. Nothing more.
Current thought, current action, heartbeat metrics, bug alert.
Empty space is the design — calm, control, trust.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

from loeb.agent import cost_label
from loeb.ui.theme import DUSK, THEMES, Theme
from loeb.ui.widgets import TOOL_CATEGORY, format_thinking


def _theme(widget: Static) -> Theme:
    """Resolve current theme from app."""
    try:
        name = getattr(widget.app, "theme_name", "dusk")
        return THEMES.get(name, DUSK)
    except Exception:
        return DUSK


# ---------------------------------------------------------------------------
# MetricsStrip — heartbeat bar, proof of life
# ---------------------------------------------------------------------------


class MetricsStrip(Static):
    """Thin strip. Iteration, time, cost. Proof the agent is alive."""

    iteration: reactive[int] = reactive(0)
    max_iterations: reactive[int] = reactive(200)
    elapsed: reactive[str] = reactive("--:--")
    cost: reactive[str] = reactive("$0.0000")
    tokens: reactive[str] = reactive("0k")
    phase: reactive[str] = reactive("diff")
    bug_count: reactive[int] = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(id="metrics-strip", **kwargs)

    def on_mount(self) -> None:
        self.set_interval(1.0, self._sync_time)

    def _sync_time(self) -> None:
        try:
            from loeb.ui.widgets import StatsBar

            bar = self.app.query_one(StatsBar)
            self.elapsed = bar._elapsed()
            self.cost = cost_label(bar.model, bar._cost())
        except Exception:
            pass

    def render(self) -> str:
        t = _theme(self)
        parts = (
            f"[{t.dim_mid}]iter[/] [bold]{self.iteration}[/]/{self.max_iterations}"
            f"  [{t.dim_mid}]time[/] {self.elapsed}"
            f"  [{t.dim_mid}]cost[/] [{t.primary}]{self.cost}[/]"
            f"  [{t.dim_mid}]tok[/] {self.tokens}"
            f"  [{t.dim_mid}]phase[/] [{t.primary}]{self.phase}[/]"
        )
        if self.bug_count > 0:
            parts += f"  [bold {t.error}]▲ {self.bug_count} bugs[/]"
        return parts


# ---------------------------------------------------------------------------
# FocusThinking — single current thought, nothing more
# ---------------------------------------------------------------------------


class FocusThinking(Static):
    """Current thought only. No history, no chain, no trace.

    Streaming shows active text with a blinking cursor.
    Finished thought collapses to a quiet summary.
    Empty state: gentle waiting message, vertically centered.
    """

    _active: reactive[bool] = reactive(False)
    _cursor_visible: reactive[bool] = reactive(True)

    def __init__(self, **kwargs):
        super().__init__(id="focus-thinking", **kwargs)
        self._buffer: list[str] = []
        self._summary = ""

    def on_mount(self) -> None:
        self.set_interval(0.5, self._blink)

    def _blink(self) -> None:
        if self._active and self._buffer:
            self._cursor_visible = not self._cursor_visible
            self.refresh()

    def append_text(self, text: str) -> None:
        self._buffer.append(text)
        self._active = True
        self.refresh(layout=True)

    def finish(self, summary: str) -> None:
        self._summary = summary
        self._buffer.clear()
        self._active = False
        self.refresh(layout=True)

    def render(self) -> str:
        t = _theme(self)

        if self._active and self._buffer:
            full = "".join(self._buffer)
            visible = full[-600:] if len(full) > 600 else full
            if len(full) > 600:
                visible = "..." + visible
            visible = format_thinking(visible)
            cursor = "█" if self._cursor_visible else " "
            return f"{visible}[bold {t.primary}]{cursor}[/]"

        if self._summary:
            summary = format_thinking(self._summary)
            return f"[{t.text_muted}]{summary}[/]"

        return f"[{t.dim_mid}]waiting for agent...[/]"


# ---------------------------------------------------------------------------
# FocusAction — single current/last tool, nothing more
# ---------------------------------------------------------------------------


class FocusAction(Static):
    """Current tool or last result. One line. No stack, no history."""

    def __init__(self, **kwargs):
        super().__init__(id="focus-action", **kwargs)
        self._active_name = ""
        self._active_input = ""
        self._last_name = ""
        self._last_ms = 0
        self._last_result = ""
        self._last_error = False
        self._pulse_frame = 0

    _PULSE = ["◉", "◎", "○", "◎"]

    def on_mount(self) -> None:
        self.set_interval(0.3, self._tick)

    def _tick(self) -> None:
        if self._active_name:
            self._pulse_frame = (self._pulse_frame + 1) % len(self._PULSE)
            self.refresh()

    def set_tool(self, name: str, input_preview: str) -> None:
        self._active_name = name
        self._active_input = input_preview
        self._pulse_frame = 0
        self.refresh(layout=True)

    def complete_tool(
        self, name: str, elapsed_ms: int, result: str, is_error: bool
    ) -> None:
        self._active_name = ""
        self._active_input = ""
        self._last_name = name
        self._last_ms = elapsed_ms
        self._last_result = result
        self._last_error = is_error
        self.refresh(layout=True)

    def render(self) -> str:
        t = _theme(self)

        if self._active_name:
            cat = TOOL_CATEGORY.get(self._active_name, "")
            color = t.category_colors.get(cat, t.text_muted)
            pulse = self._PULSE[self._pulse_frame]
            preview = self._active_input
            if len(preview) > 80:
                preview = preview[:80] + "..."
            return (
                f"[bold {color}]{pulse} {self._active_name}[/]"
                f"  [{t.text_muted}]{preview}[/]"
            )

        if self._last_name:
            status_color = t.error if self._last_error else t.success
            marker = "✗" if self._last_error else "●"
            result = self._last_result
            if len(result) > 80:
                result = result[:80] + "..."
            result = result.replace("[", "\\[")
            return (
                f"[{status_color}]{marker}[/] [{t.dim_mid}]{self._last_name}[/]"
                f"  [{t.dim_dark}]{self._last_ms}ms[/]"
                f"  [{t.text_muted}]{result}[/]"
            )

        return ""


# ---------------------------------------------------------------------------
# FocusLayout — the container: metrics + centered content
# ---------------------------------------------------------------------------


class FocusLayout(Static):
    """Focus mode: metrics strip + vertically centered thinking & action."""

    def __init__(self, **kwargs):
        super().__init__(id="focus-layout", **kwargs)

    def compose(self):
        yield MetricsStrip()
        with Vertical(id="focus-main"):
            yield FocusThinking()
            yield FocusAction()
