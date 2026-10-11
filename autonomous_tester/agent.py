import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.table import Table

from autonomous_tester.config import Config
from autonomous_tester.llm.base import (
    LLMProvider,
    StreamEvent,
    ToolCall,
    compress_messages,
    estimate_tokens,
    is_tool_error,
)
from autonomous_tester.tool_registry import (
    DEFAULT_TOOL_TIMEOUT,
    TOOL_DEFINITIONS,
    TOOL_TIMEOUTS,
    ToolRegistry,
)
from autonomous_tester.ui.events import (
    AgentStarted,
    BugFiled,
    IterationStarted,
    PhaseChanged,
    RunCompleted,
    ThinkingDelta,
    TokensUpdated,
    ToolCompleted,
    ToolStarted,
)

console = Console()

SYSTEM_PROMPT = """\
You are Löb, an autonomous QA agent testing a web app end-to-end — typically a voice \
assistant that users talk to through the browser microphone. Your job is to:

1. Read the git diff to understand what changed
2. Verify the target stack is up (services, API, website)
3. Launch a browser and navigate to the website
4. Sign in and start a session
5. Speak to the app via inject_audio() and observe its responses
6. Verify backend side effects (Redis, Postgres, logs, API)
7. Report bugs or confirm everything works

How the specific app under test works (pages, DOM selectors, Redis keys, API endpoints, \
services, architecture) is described in the "Target" section below, when one is configured.

## Guidelines
- Be methodical. After each action, observe the result before deciding next steps.
- If something fails or looks wrong, investigate: take screenshots, read logs, check console, \
query DB.
- Don't just test the happy path. Think about edge cases based on what changed.
- After speaking to the app, wait a few seconds for the response, then check transcription.
- Always verify backend side effects — don't trust the UI alone.
- When done testing, send a Slack summary and stop services.
- If you find a bug, file a GitHub issue with full evidence before sending the Slack summary.
"""


def build_system_prompt(config: Config) -> str:
    """SYSTEM_PROMPT plus the target description file (TARGET_CONTEXT), if configured."""
    path = getattr(config, "target_context", "")
    if not isinstance(path, str) or not path:
        return SYSTEM_PROMPT
    target = Path(path).expanduser().read_text()
    return f"{SYSTEM_PROMPT}\n# Target\n\n{target}"


DEFAULT_PROMPT = (
    "Begin testing. Start by reading the git diff for both "
    "the backend and frontend repos to understand what changed, then decide what to test."
)

MAX_LOG_ENTRIES = 50

# macOS sound effects
SOUND_BUG = "/System/Library/Sounds/Sosumi.aiff"
SOUND_DONE = "/System/Library/Sounds/Glass.aiff"
SOUND_ERROR = "/System/Library/Sounds/Basso.aiff"


def _play_sound(path: str) -> None:
    """Play a macOS system sound (non-blocking). No-op in CI or non-Darwin."""
    if os.environ.get("CI") or sys.platform != "darwin":
        return
    if Path(path).exists():
        subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# Constants (previously on Dashboard class)
# ---------------------------------------------------------------------------

PHASES = ["Git Diff", "Services", "Browser", "Login", "Test", "Verify", "Report"]

PHASE_COLORS = {
    1: "green",
    2: "blue",
    3: "cyan",
    4: "cyan",
    5: "magenta",
    6: "yellow",
    7: "red",
}

TOOL_PHASE_MAP = {
    "git_diff": 1,
    "start_services": 2,
    "launch_browser": 3,
    "navigate": 3,
    "wait_for_selector": 3,
    "login": 4,
    "click": 4,
    "type_text": 4,
    "inject_audio": 5,
    "inject_silence": 5,
    "upload_file": 5,
    "get_page_text": 6,
    "get_element_state": 6,
    "read_transcription": 6,
    "read_console": 6,
    "screenshot": 6,
    "check_api": 6,
    "query_db": 6,
    "query_redis": 6,
    "read_logs": 6,
    "file_github_issue": 7,
    "send_slack": 7,
    "stop_services": 7,
}

TOOL_COLOR_MAP = {
    "git_diff": "green",
    "start_services": "blue",
    "stop_services": "blue",
    "launch_browser": "cyan",
    "navigate": "cyan",
    "click": "cyan",
    "type_text": "cyan",
    "screenshot": "cyan",
    "get_page_text": "cyan",
    "get_element_state": "cyan",
    "wait_for_selector": "cyan",
    "upload_file": "cyan",
    "login": "cyan",
    "read_transcription": "cyan",
    "read_console": "cyan",
    "inject_audio": "magenta",
    "inject_silence": "magenta",
    "check_api": "yellow",
    "query_db": "yellow",
    "query_redis": "yellow",
    "read_logs": "yellow",
    "file_github_issue": "red",
    "send_slack": "red",
}

# Pricing per million tokens (input, output, cache_read, cache_creation)
MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-4-6": (3.00, 15.00, 0.30, 3.75),
    "claude-opus-4-6": (5.00, 25.00, 0.50, 6.25),
    "claude-haiku-4-5": (1.00, 5.00, 0.10, 1.25),
    # OpenAI
    "gpt-4o": (2.50, 10.00, 0, 0),
    "gpt-4o-mini": (0.15, 0.60, 0, 0),
    "o3": (10.00, 40.00, 0, 0),
    "o3-mini": (1.10, 4.40, 0, 0),
}
# Unknown/flat-plan models cost $0 marginal — never invent a per-token bill.
# glm-5.3 runs on the z.ai coding plan (flat subscription); deepseek likewise
# ran on a subscription. Add a real row here before trusting any $ display.
DEFAULT_PRICING = (0.0, 0.0, 0.0, 0.0)

TOKEN_BUDGET = 150_000


def _normalize_tool_name(name: str) -> str:
    return name.split(" ", 1)[0].strip()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    def __init__(self, config: Config, registry: ToolRegistry, provider: LLMProvider):
        self.config = config
        self.registry = registry
        self.provider = provider
        self.system_prompt = build_system_prompt(config)
        self.max_iterations = 200
        self.messages: list[dict] = []
        self.tool_history: list[dict] = []
        self.bugs_found: list[str] = []
        self.session_dump_path: Path | None = None

        # Event callback for the Textual UI
        self.on_event: Callable | None = None

        # Token / stats counters
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0
        self.tool_successes = 0
        self.tool_errors = 0
        self.phase_index = 1
        self.start_time = 0.0
        self.iteration = 0

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(self, event: object) -> None:
        """Forward an event to the registered callback, if any."""
        if self.on_event is not None:
            self.on_event(event)

    # ------------------------------------------------------------------
    # Phase tracking
    # ------------------------------------------------------------------

    def _update_phase(self, tool_name: str) -> None:
        """Advance phase based on the tool and emit PhaseChanged if it moved."""
        phase = TOOL_PHASE_MAP.get(_normalize_tool_name(tool_name))
        if phase and phase > self.phase_index:
            self.phase_index = phase
            self._emit(
                PhaseChanged(
                    phase_index=self.phase_index,
                    phase_name=PHASES[self.phase_index - 1],
                )
            )

    # ------------------------------------------------------------------
    # Cost helpers
    # ------------------------------------------------------------------

    def _active_model(self) -> str:
        """The model actually serving the loop, per provider selection."""
        if getattr(self.config, "provider", "anthropic") == "openai":
            return getattr(self.config, "openai_model", self.config.model)
        return self.config.model

    def _pricing(self) -> tuple[float, float, float, float]:
        # Keyed on the ACTIVE model. Previously this read self.config.model
        # (the Anthropic field) even when the loop ran GLM via the openai
        # provider, pricing flat-plan GLM tokens at Sonnet rates.
        return MODEL_PRICING.get(self._active_model(), DEFAULT_PRICING)

    def _calculate_cost(self) -> float:
        p = self._pricing()
        return (
            self.input_tokens * p[0]
            + self.output_tokens * p[1]
            + self.cache_read_tokens * p[2]
            + self.cache_creation_tokens * p[3]
        ) / 1_000_000

    def _calculate_cost_without_cache(self) -> float:
        p = self._pricing()
        return (
            (self.input_tokens + self.cache_read_tokens) * p[0]
            + self.output_tokens * p[1]
            + self.cache_creation_tokens * p[3]
        ) / 1_000_000

    def _calculate_cache_savings(self) -> float:
        return max(0.0, self._calculate_cost_without_cache() - self._calculate_cost())

    # ------------------------------------------------------------------
    # Elapsed time
    # ------------------------------------------------------------------

    def _elapsed(self) -> str:
        s = int(time.time() - self.start_time)
        m, s = divmod(s, 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"

    # ------------------------------------------------------------------
    # Stream event handler
    # ------------------------------------------------------------------

    def _handle_stream_event(self, event: StreamEvent) -> None:
        """Bridge provider StreamEvents to Textual UI events."""
        if event.type == "thinking":
            self._emit(ThinkingDelta(text=event.text))
        elif event.type == "tool_start":
            self._update_phase(event.tool_name)

    # ------------------------------------------------------------------
    # Parallel tool execution
    # ------------------------------------------------------------------

    async def _execute_one(self, tc: ToolCall) -> str:
        """Execute a single tool call with timeout."""
        tool_name = tc.name
        timeout = TOOL_TIMEOUTS.get(tool_name, DEFAULT_TOOL_TIMEOUT)
        short_input = json.dumps(tc.input)
        if len(short_input) > 200:
            short_input = short_input[:200] + "..."

        self._emit(ToolStarted(name=tool_name, input_preview=short_input))

        tool_start = time.time()
        try:
            result = await asyncio.wait_for(
                self.registry.dispatch(tool_name, tc.input),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            result = f"Error: {tool_name} timed out after {timeout}s"
        elapsed_ms = int((time.time() - tool_start) * 1000)

        error = is_tool_error(result)
        preview = result[:120].replace("\n", " ")

        self._update_phase(tool_name)
        if error:
            self.tool_errors += 1
        else:
            self.tool_successes += 1

        self._emit(
            ToolCompleted(
                name=tool_name,
                elapsed_ms=elapsed_ms,
                result_preview=preview,
                is_error=error,
                full_result=result,
            )
        )

        self.tool_history.append(
            {
                "name": tool_name,
                "elapsed_ms": elapsed_ms,
                "result_preview": preview[:80],
                "error": error,
            }
        )

        if error and tool_name != "screenshot":
            _play_sound(SOUND_ERROR)
            await self._auto_screenshot(tool_name)

        if tool_name == "file_github_issue":
            title = tc.input.get("title", "unknown")
            self.bugs_found.append(title)
            self._emit(BugFiled(title=title))
            _play_sound(SOUND_BUG)

        return result

    async def _execute_tools(self, tool_calls: list[ToolCall]) -> list[str]:
        """Execute all tool calls in parallel."""
        tasks = [self._execute_one(tc) for tc in tool_calls]
        return list(await asyncio.gather(*tasks))

    # ------------------------------------------------------------------
    # Summary & persistence
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        console.print()
        cost = self._calculate_cost()
        no_cache_cost = self._calculate_cost_without_cache()
        cache_savings = self._calculate_cache_savings()
        total_tools = self.tool_successes + self.tool_errors
        pass_rate = self.tool_successes / total_tools if total_tools else 1.0
        health_color = "green" if pass_rate >= 0.9 else "yellow" if pass_rate >= 0.7 else "red"
        if total_tools == 0:
            health_color = "dim"
        table = Table(title="Test Run Complete", border_style="green")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Iterations", str(self.iteration))
        table.add_row("Duration", self._elapsed())
        table.add_row("Tool calls", str(len(self.tool_history)))
        table.add_row(
            "Tool health",
            f"[{health_color}]OK {self.tool_successes}/{total_tools}[/{health_color}]",
        )
        table.add_row(
            "Bugs found",
            f"[red]{len(self.bugs_found)}[/red]" if self.bugs_found else "[green]0[/green]",
        )
        table.add_row("Input tokens", f"{self.input_tokens:,}")
        table.add_row("Output tokens", f"{self.output_tokens:,}")
        if self.cache_read_tokens:
            table.add_row("Cache read tokens", f"{self.cache_read_tokens:,}")
        if self.cache_creation_tokens:
            table.add_row("Cache creation tokens", f"{self.cache_creation_tokens:,}")
        table.add_row("Total cost", f"${cost:.4f}")
        if self.cache_read_tokens:
            table.add_row("Cost without cache", f"${no_cache_cost:.4f}")
            table.add_row("Cache savings", f"[green]${cache_savings:.4f}[/green]")
        if self.session_dump_path:
            table.add_row("Session dump", str(self.session_dump_path))
        console.print(table)

        if self.tool_history:
            console.print()
            tool_table = Table(title="Tool Call Log", border_style="dim")
            tool_table.add_column("#", style="dim", width=4)
            tool_table.add_column("Tool", style="bold")
            tool_table.add_column("Duration", justify="right")
            tool_table.add_column("Preview", max_width=60)
            for i, entry in enumerate(self.tool_history, 1):
                tool_table.add_row(
                    str(i),
                    entry["name"],
                    f"{entry['elapsed_ms']}ms",
                    entry["result_preview"],
                )
            console.print(tool_table)

    async def _auto_screenshot(self, tool_name: str) -> None:
        """Take an automatic screenshot when a tool returns an error."""
        try:
            result = await self.registry.dispatch(
                "screenshot", {"name": f"auto_error_{tool_name}_{len(self.tool_history)}"}
            )
            preview = result[:120].replace("\n", " ")
            self._emit(
                ToolCompleted(
                    name="screenshot (auto)",
                    elapsed_ms=0,
                    result_preview=preview,
                    is_error=False,
                    full_result=result,
                )
            )
        except Exception:
            pass  # best-effort, don't interrupt the run

    @staticmethod
    def _escape_osascript(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    def _notify_completion(self) -> None:
        """Send native macOS notification when run completes (best-effort)."""
        if os.environ.get("CI") or sys.platform != "darwin":
            return
        total_tools = self.tool_successes + self.tool_errors
        summary = f"bugs: {len(self.bugs_found)}, OK {self.tool_successes}/{total_tools}"
        details = (
            f"{self.iteration} iterations in {self._elapsed()}, cost ${self._calculate_cost():.4f}"
        )
        script = (
            f'display notification "{self._escape_osascript(details)}" '
            f'with title "Löb" '
            f'subtitle "{self._escape_osascript(summary)}"'
        )
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _dump_session(self, prompt: str) -> Path | None:
        """Persist a full run artifact under runs/{timestamp}.json."""
        try:
            runs_dir = Path("runs")
            runs_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            dump_path = runs_dir / f"{timestamp}.json"
            duration_seconds = round(time.time() - self.start_time, 3)
            payload = {
                "prompt": prompt,
                "iterations": self.iteration,
                "tool_history": self.tool_history,
                "bugs_found": self.bugs_found,
                "tokens": {
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "cache_read_tokens": self.cache_read_tokens,
                    "cache_creation_tokens": self.cache_creation_tokens,
                },
                "cost": {
                    "actual": round(self._calculate_cost(), 6),
                    "without_cache": round(self._calculate_cost_without_cache(), 6),
                    "cache_savings": round(self._calculate_cache_savings(), 6),
                },
                "duration_seconds": duration_seconds,
            }
            dump_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.session_dump_path = dump_path
            return dump_path
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self, prompt: str | None = None) -> None:
        user_prompt = prompt or DEFAULT_PROMPT
        self.start_time = time.time()

        self.messages = [{"role": "user", "content": user_prompt}]

        self._emit(AgentStarted(prompt=user_prompt, model=self._active_model()))

        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            self.iteration = iteration
            self._emit(
                IterationStarted(
                    iteration=iteration,
                    max_iterations=self.max_iterations,
                )
            )

            # Compress old messages if context is getting large
            if estimate_tokens(self.messages) > TOKEN_BUDGET:
                self.messages = compress_messages(self.messages, keep_recent=10)

            result = await self.provider.complete(
                system=self.system_prompt,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                max_tokens=self.config.max_tokens,
                on_event=self._handle_stream_event,
            )

            # Update token counters
            self.input_tokens += result.input_tokens
            self.output_tokens += result.output_tokens
            self.cache_read_tokens += result.cache_read_tokens
            self.cache_creation_tokens += result.cache_creation_tokens
            self._emit(
                TokensUpdated(
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    cache_read=self.cache_read_tokens,
                    cache_creation=self.cache_creation_tokens,
                )
            )

            # Append assistant message
            self.messages.append(self.provider.make_assistant_message(result.raw_content))

            if result.stop_reason == "end_turn":
                _play_sound(SOUND_DONE)
                break

            if result.stop_reason == "tool_use":
                tool_results = await self._execute_tools(result.tool_calls)
                self.messages.extend(
                    self.provider.make_tool_result_message(result.tool_calls, tool_results)
                )

        _play_sound(SOUND_DONE)

        elapsed_seconds = round(time.time() - self.start_time, 3)
        self._emit(
            RunCompleted(
                iterations=iteration,
                elapsed_seconds=elapsed_seconds,
                bugs_found=list(self.bugs_found),
                cost=self._calculate_cost(),
                session_dump_path=str(self.session_dump_path or ""),
            )
        )

        self._dump_session(user_prompt)
        self._notify_completion()
        self._print_summary()
