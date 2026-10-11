"""Screens for the Löb TUI."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Label, OptionList, RichLog, Static
from textual.widgets.option_list import Option

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


# ---------------------------------------------------------------------------
# InteractiveSetupScreen — pre-run wizard
# ---------------------------------------------------------------------------


@dataclass
class SetupResult:
    """Result from the interactive setup wizard."""

    mode: str  # "auto" | "specific" | "rerun"
    prompt: str | None
    services: str  # "full" | "backend" | "none"
    headless: bool


class InteractiveSetupScreen(Screen):
    """Pre-run wizard that lets the user configure test parameters."""

    @dataclass
    class Completed(Message):
        """Posted when the user clicks Start."""

        result: SetupResult

    def __init__(
        self,
        backend_diff_summary: str = "",
        frontend_diff_summary: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.backend_diff_summary = backend_diff_summary
        self.frontend_diff_summary = frontend_diff_summary

        # Defaults
        self._mode: str = "auto"
        self._services: str = "full"
        self._headless: bool = True

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Löb \u2014 Interactive Setup")

            if self.backend_diff_summary:
                yield Static(f"Backend diff:\n{self.backend_diff_summary}")
            if self.frontend_diff_summary:
                yield Static(f"Frontend diff:\n{self.frontend_diff_summary}")

            yield Label("Test mode:")
            yield OptionList(
                Option("Auto — discover & run tests from diff", id="auto"),
                Option("Specific — provide a custom prompt", id="specific"),
                Option("Re-run — repeat the last session", id="rerun"),
                id="mode-select",
            )

            yield Label("Services:")
            yield OptionList(
                Option("Full stack (backend + frontend)", id="full"),
                Option("Backend only", id="backend"),
                Option("None (assume already running)", id="none"),
                id="services-select",
            )

            yield Label("Browser:")
            yield OptionList(
                Option("Headless", id="headless"),
                Option("Visible", id="visible"),
                id="browser-select",
            )

            yield Button("Start", id="start-btn", variant="primary")
            yield Button("Cancel", id="cancel-btn", variant="error")

    # -- event handlers -------------------------------------------------------

    @on(OptionList.OptionSelected, "#mode-select")
    def _on_mode_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self._mode = event.option.id

    @on(OptionList.OptionSelected, "#services-select")
    def _on_services_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self._services = event.option.id

    @on(OptionList.OptionSelected, "#browser-select")
    def _on_browser_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self._headless = event.option.id == "headless"

    @on(Button.Pressed, "#start-btn")
    def _on_start(self, event: Button.Pressed) -> None:
        self.post_message(
            self.Completed(
                result=SetupResult(
                    mode=self._mode,
                    prompt=None,
                    services=self._services,
                    headless=self._headless,
                )
            )
        )

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, event: Button.Pressed) -> None:
        self.app.exit()
