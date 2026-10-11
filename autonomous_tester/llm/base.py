from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class CompletionResult:
    stop_reason: str  # "end_turn" | "tool_use"
    tool_calls: list[ToolCall]
    raw_content: Any  # provider-native content for message history
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class StreamEvent:
    type: str  # "thinking" | "tool_start" | "error"
    text: str = ""
    tool_name: str = ""


_ERROR_PREFIXES = (
    "Error:",
    "ERROR:",
    "Failed ",
    "Could not ",
    "Timeout ",
    "No browser page open",
    "Unknown tool:",
    "Upload failed:",
    "Slack API error:",
    "Audio injection failed:",
    "Silence injection failed:",
    "Token login failed:",
    "Browser login failed:",
    "API request failed:",
    "Database query failed:",
    "Redis query failed:",
    "Failed to ",
)


def is_tool_error(result: str) -> bool:
    """Check if a tool result indicates an error using known prefixes."""
    return any(result.startswith(p) for p in _ERROR_PREFIXES)


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: ~4 chars per token on JSON-serialized messages."""
    return len(json.dumps(messages, default=str)) // 4


_TRUNCATE_THRESHOLD = 500
_TRUNCATE_TO = 200


def compress_messages(
    messages: list[dict],
    keep_recent: int = 10,
) -> list[dict]:
    """Truncate old message content to reduce token usage.

    Args:
        messages: The full message list.
        keep_recent: Number of recent messages to keep at full fidelity.
    """
    if not messages:
        return messages
    result = copy.deepcopy(messages)
    cutoff = max(0, len(result) - keep_recent)
    for msg in result[:cutoff]:
        content = msg.get("content")
        if isinstance(content, str) and len(content) > _TRUNCATE_THRESHOLD:
            msg["content"] = content[:_TRUNCATE_TO] + "... [truncated]"
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    val = block.get("content", "")
                    if isinstance(val, str) and len(val) > _TRUNCATE_THRESHOLD:
                        block["content"] = val[:_TRUNCATE_TO] + "... [truncated]"
    return result


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 16384,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> CompletionResult:
        """Stream a completion and return the final result.

        Args:
            system: System prompt text (plain string, provider adds formatting).
            messages: Conversation history in provider-native format.
            tools: Tool definitions in Anthropic canonical format
                   (name, description, input_schema). Provider converts as needed.
            max_tokens: Maximum output tokens.
            on_event: Optional callback for streaming events (thinking text, tool starts).
        """
        ...

    @abstractmethod
    def make_tool_result_message(
        self, tool_calls: list[ToolCall], results: list[str]
    ) -> list[dict]:
        """Create message(s) containing tool results in provider-native format."""
        ...

    @abstractmethod
    def make_assistant_message(self, raw_content: Any) -> dict:
        """Create an assistant message from raw provider content."""
        ...
