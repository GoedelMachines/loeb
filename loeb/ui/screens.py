"""Screens for the Löb TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, RichLog

# ---------------------------------------------------------------------------
# ToolDetailScreen — modal overlay showing a full tool result
# ---------------------------------------------------------------------------


class ToolDetailScreen(ModalScreen):
    """Modal overlay that displays the full output of a tool invocation."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(
        self,
        tool_name: str,
        full_result: str,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.tool_name = tool_name
        self.full_result = full_result

    def compose(self) -> ComposeResult:
        with Vertical(id="tool-detail-container"):
            yield Label(f"Tool: {self.tool_name}")
            yield RichLog(id="tool-detail-log", wrap=True, markup=True)
            yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#tool-detail-log", RichLog)
        log.write(self.full_result)
