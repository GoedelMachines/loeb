# Provider Abstraction & Agent Loop Improvements

## Problem

The agent loop in `agent.py` is hardcoded to the Anthropic SDK. The streaming logic, message format, tool schema format, and prompt caching are all Anthropic-specific. This prevents using other models (GPT-4o, o3, Gemini) and makes the loop harder to maintain.

Additionally, the loop has several operational issues: sequential tool execution, hardcoded `max_tokens=4096`, unbounded message history, naive error detection, no API retries, and no tool timeouts.

## Design

### Core Types (`autonomous_tester/llm/base.py`)

Normalized data types that all providers map to/from:

```python
@dataclass
class ToolCall:
    id: str
    name: str
    input: dict

@dataclass
class CompletionResult:
    stop_reason: str          # "end_turn" | "tool_use"
    tool_calls: list[ToolCall]
    raw_content: Any          # provider-native content for message history
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

@dataclass
class StreamEvent:
    type: str  # "thinking" | "tool_start" | "error"
    text: str = ""
    tool_name: str = ""

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 16384,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> CompletionResult: ...

    @abstractmethod
    def make_tool_result_message(
        self, tool_calls: list[ToolCall], results: list[str],
    ) -> dict: ...

    @abstractmethod
    def make_assistant_message(self, raw_content: Any) -> dict: ...
```

Tool definitions stay in Anthropic format as the canonical schema. Each provider converts internally.

`raw_content` preserves the provider-native response content so message history works without re-serialization.

`make_tool_result_message` / `make_assistant_message` let each provider format its own message history entries (Anthropic uses `tool_result` blocks, OpenAI uses `role: "tool"` messages).

### Anthropic Provider (`autonomous_tester/llm/anthropic.py`)

Extracts the current streaming logic from `agent.py:539-607` into a provider class.

- Prompt caching: `cache_control` on system prompt + second-to-last user message
- Streaming: text deltas forwarded via `on_event(StreamEvent("thinking", text=...))`
- Tool block accumulation from `content_block_start/stop` events
- Token counting from `message_start` / `message_delta` events
- Retry with exponential backoff (3 attempts) on rate limits, 500s, connection errors

Extended thinking not added now, but the provider is where it would go.

### OpenAI Provider (`autonomous_tester/llm/openai.py`)

Covers GPT-4o, o3, and any OpenAI-compatible endpoint (Groq, Together, Fireworks) via configurable `base_url`.

- Converts tool defs: `input_schema` to `parameters`, wraps in `{"type": "function", ...}`
- Converts messages: `tool_result` blocks to `role: "tool"` messages
- Streams text deltas via `on_event`
- Same retry logic as Anthropic provider

### Agent Loop Simplification

The main loop in `agent.py` shrinks from ~170 lines to ~50:

```python
async def run(self, prompt):
    self.messages = [{"role": "user", "content": prompt}]
    for iteration in range(self.max_iterations):
        result = await self.provider.complete(
            system=SYSTEM_PROMPT,
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            max_tokens=self.config.max_tokens,
            on_event=self._handle_stream_event,
        )
        self.messages.append(self.provider.make_assistant_message(result.raw_content))
        self._update_tokens(result)
        if result.stop_reason == "end_turn":
            break
        tool_results = await self._execute_tools(result.tool_calls)
        self.messages.append(
            self.provider.make_tool_result_message(result.tool_calls, tool_results)
        )
```

### Parallel Tool Execution

`_execute_tools` runs all tool calls from a single response concurrently:

```python
async def _execute_tools(self, tool_calls):
    tasks = [self._execute_one(tc) for tc in tool_calls]
    return await asyncio.gather(*tasks)
```

### Tool Timeouts

Each dispatch wrapped in `asyncio.wait_for(dispatch(...), timeout=timeout)`. Default 60s. Slow tools like `start_services` get 300s. On timeout, return `"Error: tool timed out after Ns"`.

### Error Detection

Replace `"error" in result.lower()[:50]` with prefix-based detection. All tool implementations already return results starting with known error prefixes (`"Error: "`, `"Failed: "`, `"Could not "`, `"Timeout "`, `"No browser page open"`, `"Unknown tool"`). Check for these prefixes instead of substring matching.

### Message History Management

When the message list grows large (estimated token count exceeds a configurable budget, default ~150k tokens), compress old turns:

- Summarize old tool results to their first line
- Truncate large outputs (logs, page text, diffs) to 200 chars
- Keep full fidelity for the last N turns (default: 10)
- Never compress the system prompt or the current turn

Token estimation: rough heuristic of `len(json.dumps(messages)) / 4`.

### Retry with Backoff

Built into each provider. 3 attempts with exponential backoff (1s, 2s, 4s) on:

- Rate limit errors (429)
- Server errors (500, 502, 503)
- Connection errors

Non-retryable errors (400, 401, 403) raise immediately.

### Config Changes

New fields on `Config`:

- `provider: str` — `"anthropic"` (default) or `"openai"`
- `openai_api_key: str` — for OpenAI provider
- `openai_base_url: str` — for OpenAI-compatible endpoints
- `openai_model: str` — model name for OpenAI provider
- `max_tokens: int` — default 16384 (up from 4096)

CLI additions: `--provider`, `--openai-model`.

### File Changes

New files:
- `autonomous_tester/llm/__init__.py`
- `autonomous_tester/llm/base.py`
- `autonomous_tester/llm/anthropic.py`
- `autonomous_tester/llm/openai.py`
- `tests/test_llm_base.py`
- `tests/test_llm_anthropic.py`
- `tests/test_llm_openai.py`

Modified files:
- `autonomous_tester/agent.py` — replace streaming logic with provider calls, add parallel execution, tool timeouts, message management, error detection
- `autonomous_tester/config.py` — new provider/openai fields, max_tokens
- `autonomous_tester/run.py` — provider selection, new CLI args
- `autonomous_tester/tool_registry.py` — add timeout metadata per tool
- `pyproject.toml` — add `openai` dependency
- `tests/test_agent.py` — update for provider-based agent

### Dependencies

Add `openai` package to `pyproject.toml`. No other new dependencies.
