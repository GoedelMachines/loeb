"""Event messages emitted by the Agent and consumed by the Textual UI."""

from __future__ import annotations

from textual.message import Message


class ThinkingDelta(Message):
    """Streamed chunk of thinking text."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class ThinkingFinished(Message):
    """Thinking ended with a collapsed summary."""

    def __init__(self, summary: str) -> None:
        self.summary = summary
        super().__init__()


class ToolStarted(Message):
    """A tool is about to run."""

    def __init__(self, name: str, input_preview: str) -> None:
        self.name = name
        self.input_preview = input_preview
        super().__init__()


class ToolCompleted(Message):
    """A tool finished execution."""

    def __init__(
        self,
        name: str,
        elapsed_ms: int,
        result_preview: str,
        is_error: bool,
        full_result: str = "",
    ) -> None:
        self.name = name
        self.elapsed_ms = elapsed_ms
        self.result_preview = result_preview
        self.is_error = is_error
        self.full_result = full_result
        super().__init__()


class IterationStarted(Message):
    """New loop iteration began."""

    def __init__(self, iteration: int, max_iterations: int) -> None:
        self.iteration = iteration
        self.max_iterations = max_iterations
        super().__init__()


class TokensUpdated(Message):
    """Token usage snapshot."""

    def __init__(
        self, input_tokens: int, output_tokens: int, cache_read: int, cache_creation: int
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read = cache_read
        self.cache_creation = cache_creation
        super().__init__()


class BugFiled(Message):
    """A GitHub issue was filed."""

    def __init__(self, title: str) -> None:
        self.title = title
        super().__init__()


class AgentStarted(Message):
    """The agent run began."""

    def __init__(self, prompt: str, model: str) -> None:
        self.prompt = prompt
        self.model = model
        super().__init__()


class RunCompleted(Message):
    """The agent run finished."""

    def __init__(
        self,
        iterations: int,
        elapsed_seconds: float,
        bugs_found: list[str] | None = None,
        cost: float = 0.0,
        session_dump_path: str = "",
    ) -> None:
        self.iterations = iterations
        self.elapsed_seconds = elapsed_seconds
        self.bugs_found = bugs_found if bugs_found is not None else []
        self.cost = cost
        self.session_dump_path = session_dump_path
        super().__init__()


class PhaseChanged(Message):
    """Agent moved to a new phase."""

    def __init__(self, phase_index: int, phase_name: str) -> None:
        self.phase_index = phase_index
        self.phase_name = phase_name
        super().__init__()
