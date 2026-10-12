"""Löb — autonomous test observer TUI."""

from __future__ import annotations

import asyncio
from functools import partial

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Static

from loeb.agent import Agent, cost_label
from loeb.ui.events import (
    AgentStarted,
    BugFiled,
    IterationStarted,
    PhaseChanged,
    RunCompleted,
    ThinkingDelta,
    ThinkingFinished,
    TokensUpdated,
    ToolCompleted,
    ToolStarted,
)
from loeb.ui.focus import (
    FocusAction,
    FocusLayout,
    FocusThinking,
    MetricsStrip,
)
from loeb.ui.screens import ToolDetailScreen
from loeb.ui.widgets import (
    ActiveTool,
    BugsPanel,
    StatsBar,
    ThinkingStream,
    ToolLog,
)


class HeaderBar(Static):
    """Löb branded title bar."""

    def __init__(self, prompt: str = "") -> None:
        super().__init__()
        self._prompt = prompt

    def render(self) -> str:
        p = self._prompt[:55] + "..." if len(self._prompt) > 55 else self._prompt
        if p:
            return f"[bold #e8907a]LÖB[/bold #e8907a]  [#7a6e88]{p}[/#7a6e88]"
        return "[bold #e8907a]LÖB[/bold #e8907a]"


class TesterApp(App):
    """Löb — autonomous test observer."""

    TITLE = "Löb"
    CSS_PATH = "styles.tcss"

    theme_name: reactive[str] = reactive("dusk")
    layout_mode: reactive[str] = reactive("instrument")

    BINDINGS = [
        Binding("q", "quit", "quit", show=True),
        Binding("p", "toggle_pause", "pause", show=True),
        Binding("v", "toggle_verbose", "verbose", show=True),
        Binding("t", "toggle_thinking", "thinking", show=True),
        Binding("l", "toggle_theme", "theme", show=True),
        Binding("m", "toggle_mode", "mode", show=True),
        Binding("enter", "show_tool_detail", "expand", show=False),
    ]

    def __init__(
        self,
        agent: Agent,
        prompt: str = "",
        headless: bool = True,
        verbose: bool = False,
        auto_exit: bool = False,
    ) -> None:
        super().__init__()
        self.agent = agent
        self._prompt = prompt
        self._headless = headless
        self._verbose = verbose
        self._auto_exit = auto_exit
        self._tool_counter = 0
        self.agent_error: str | None = None  # set when the agent run raised

    def compose(self) -> ComposeResult:
        yield HeaderBar(self._prompt)
        with Horizontal(id="dashboard"):
            with Vertical(id="sidebar"):
                yield StatsBar()
                yield BugsPanel()
            with Vertical(id="main-area"):
                yield ThinkingStream()
                yield ActiveTool()
                yield ToolLog()
        yield FocusLayout()
        yield Footer()

    def watch_theme_name(self, value: str) -> None:
        self.remove_class("dusk", "linen")
        self.add_class(value)
        try:
            self.screen.remove_class("dusk", "linen")
            self.screen.add_class(value)
        except Exception:
            pass

    def on_mount(self) -> None:
        self.add_class(self.theme_name)
        self.screen.add_class(self.theme_name)

        def emit_to_ui(event):
            self.call_from_thread(self.post_message, event)

        self.agent.on_event = emit_to_ui
        self.run_worker(
            partial(self._run_agent_in_thread),
            thread=True,
            exclusive=True,
        )

    def _run_agent_in_thread(self) -> None:
        loop = asyncio.new_event_loop()
        self._agent_loop = loop
        try:
            self._agent_task = loop.create_task(self.agent.run(prompt=self._prompt))
            loop.run_until_complete(self._agent_task)
        except Exception as e:
            self.agent_error = f"{type(e).__name__}: {e}"
            self.call_from_thread(self.notify, f"error: {e}", severity="error")
        finally:
            # Close browser inside this loop before it shuts down,
            # otherwise Playwright's subprocess transport raises on GC.
            try:
                browser = self.agent.registry.browser
                if browser:
                    loop.run_until_complete(browser.close())
            except Exception:
                pass
            loop.close()
            # Direct (one-shot) runs must terminate the process when the
            # agent is done — completion, iteration cap, or crash alike.
            # Without this, a detached run leaves the TUI redrawing forever
            # at 100% CPU (observed 2026-08-25: capped run spun ~95 min).
            # Interactive mode keeps the dashboard open (auto_exit=False).
            if self._auto_exit:
                try:
                    self.call_from_thread(self.exit)
                except Exception:
                    pass

    # --- Events ---

    def on_agent_started(self, event: AgentStarted) -> None:
        import time

        bar = self.query_one(StatsBar)
        bar.model = event.model
        bar.start_time = time.time()

    def on_iteration_started(self, event: IterationStarted) -> None:
        import time

        bar = self.query_one(StatsBar)
        if bar.start_time == 0.0:
            bar.start_time = time.time()
        bar.iteration = event.iteration
        bar.max_iterations = event.max_iterations
        strip = self.query_one(MetricsStrip)
        strip.iteration = event.iteration
        strip.max_iterations = event.max_iterations

    def on_thinking_delta(self, event: ThinkingDelta) -> None:
        self.query_one(ThinkingStream).append_text(event.text)
        self.query_one(FocusThinking).append_text(event.text)

    def on_thinking_finished(self, event: ThinkingFinished) -> None:
        self.query_one(ThinkingStream).finish(event.summary)
        self.query_one(FocusThinking).finish(event.summary)

    def on_tool_started(self, event: ToolStarted) -> None:
        self.query_one(ActiveTool).set_tool(event.name, event.input_preview)
        self.query_one(FocusAction).set_tool(event.name, event.input_preview)

    def on_tool_completed(self, event: ToolCompleted) -> None:
        self._tool_counter += 1
        self.query_one(ActiveTool).clear_tool()
        self.query_one(ToolLog).add_entry(
            num=self._tool_counter,
            name=event.name,
            elapsed_ms=event.elapsed_ms,
            preview=event.result_preview,
            is_error=event.is_error,
            full_result=event.full_result,
        )
        bar = self.query_one(StatsBar)
        if event.is_error:
            bar.tool_errors += 1
        else:
            bar.tool_successes += 1
        self.query_one(FocusAction).complete_tool(
            event.name,
            event.elapsed_ms,
            event.result_preview,
            event.is_error,
        )

    def on_tokens_updated(self, event: TokensUpdated) -> None:
        bar = self.query_one(StatsBar)
        bar.input_tokens = event.input_tokens
        bar.output_tokens = event.output_tokens
        bar.cache_read_tokens = event.cache_read
        bar.cache_creation_tokens = event.cache_creation
        # Sync to focus mode strip
        strip = self.query_one(MetricsStrip)
        tok_k = (event.input_tokens + event.output_tokens) / 1000
        strip.tokens = f"{tok_k:.0f}k"
        # Compute cost from StatsBar (it has the model)
        strip.cost = cost_label(bar.model, bar._cost())
        strip.elapsed = bar._elapsed()

    def on_phase_changed(self, event: PhaseChanged) -> None:
        self.query_one(StatsBar).phase_index = event.phase_index
        self.query_one(MetricsStrip).phase = event.phase_name

    def on_bug_filed(self, event: BugFiled) -> None:
        self.query_one(StatsBar).bug_count += 1
        self.query_one(BugsPanel).add_bug(event.title)
        self.query_one(MetricsStrip).bug_count += 1

    def on_run_completed(self, event: RunCompleted) -> None:
        self.notify(
            f"done  {event.iterations} iters  {len(event.bugs_found)} bugs  "
            f"{cost_label(self.query_one(StatsBar).model, event.cost)}",
        )

    # --- Actions ---

    def action_toggle_pause(self) -> None:
        if self.agent.paused:
            self.agent.resume()
            self.notify("running")
        else:
            self.agent.pause()
            self.notify("pausing after the current step")

    async def action_quit(self) -> None:
        """Stop the agent (cancelling any in-flight model call or tool), then exit."""
        self.agent.request_stop()
        loop, task = getattr(self, "_agent_loop", None), getattr(self, "_agent_task", None)
        if loop is not None and task is not None and not loop.is_closed():
            loop.call_soon_threadsafe(task.cancel)
        self.exit()

    def action_toggle_verbose(self) -> None:
        self._verbose = not self._verbose
        self.notify(f"verbose {'on' if self._verbose else 'off'}")

    def action_toggle_thinking(self) -> None:
        self.query_one(ThinkingStream).toggle()

    def action_toggle_theme(self) -> None:
        self.theme_name = "linen" if self.theme_name == "dusk" else "dusk"
        self.notify(f"theme: {self.theme_name}")

    def action_toggle_mode(self) -> None:
        self.layout_mode = "focus" if self.layout_mode == "instrument" else "instrument"
        self.notify(f"mode: {self.layout_mode}")

    def watch_layout_mode(self, value: str) -> None:
        try:
            dashboard = self.query_one("#dashboard")
            focus = self.query_one(FocusLayout)
        except Exception:
            return
        if value == "focus":
            dashboard.display = False
            focus.add_class("active")
        else:
            dashboard.display = True
            focus.remove_class("active")

    def action_show_tool_detail(self) -> None:
        log = self.query_one(ToolLog)
        table = log.query_one("DataTable")
        if table.row_count == 0:
            return
        row_idx = table.cursor_row
        full = log.get_full_result(row_idx)
        row = table.get_row_at(row_idx)
        tool_name = str(row[1]) if row else "tool"
        self.push_screen(ToolDetailScreen(tool_name, full))
