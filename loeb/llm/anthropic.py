"""Anthropic Claude LLM provider."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import anthropic

from loeb.llm.base import (
    CompletionResult,
    LLMProvider,
    StreamEvent,
    ToolCall,
    is_tool_error,
)


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API with streaming."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)

    # ------------------------------------------------------------------
    # Core completion
    # ------------------------------------------------------------------

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 16384,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> CompletionResult:
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        prepared = self._prepare_messages(messages)
        converted_tools = self._convert_tools(tools)

        tool_use_blocks: list[dict] = []
        current_tool_block: dict | None = None
        current_tool_json = ""
        text_chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cache_read = 0
        cache_creation = 0

        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system_blocks,
            tools=converted_tools,
            messages=prepared,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        text_chunks = []
                    elif event.content_block.type == "tool_use":
                        current_tool_block = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                        }
                        current_tool_json = ""
                        if on_event:
                            on_event(
                                StreamEvent(
                                    type="tool_start",
                                    tool_name=event.content_block.name,
                                )
                            )

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        text_chunks.append(event.delta.text)
                        if on_event:
                            on_event(StreamEvent(type="thinking", text=event.delta.text))
                    elif event.delta.type == "input_json_delta":
                        current_tool_json += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if text_chunks:
                        text_chunks = []

                    if current_tool_block is not None:
                        try:
                            tool_input = json.loads(current_tool_json)
                        except json.JSONDecodeError:
                            tool_input = {}
                        current_tool_block["input"] = tool_input
                        tool_use_blocks.append(current_tool_block)
                        current_tool_block = None
                        current_tool_json = ""

                elif event.type == "message_start":
                    msg_usage = event.message.usage
                    input_tokens += msg_usage.input_tokens
                    cache_read += getattr(msg_usage, "cache_read_input_tokens", 0) or 0
                    cache_creation += getattr(msg_usage, "cache_creation_input_tokens", 0) or 0

                elif event.type == "message_delta":
                    if event.usage:
                        output_tokens += event.usage.output_tokens

            response = stream.get_final_message()

        tool_calls = [
            ToolCall(id=tb["id"], name=tb["name"], input=tb["input"]) for tb in tool_use_blocks
        ]

        # Pass max_tokens / pause_turn / refusal through: mapping them to end_turn made a
        # truncated reply look like a finished run.
        stop_reason = response.stop_reason or "end_turn"
        if stop_reason == "stop_sequence":
            stop_reason = "end_turn"

        return CompletionResult(
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            raw_content=response.content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def make_assistant_message(self, raw_content: Any) -> dict:
        return {"role": "assistant", "content": raw_content}

    def make_tool_result_message(
        self, tool_calls: list[ToolCall], results: list[str]
    ) -> list[dict]:
        blocks = []
        for tc, result in zip(tool_calls, results):
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            }
            if is_tool_error(result):
                block["is_error"] = True
            blocks.append(block)
        return [{"role": "user", "content": blocks}]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Anthropic format is canonical — pass through unchanged."""
        return tools

    @staticmethod
    def _prepare_messages(messages: list[dict]) -> list[dict]:
        """Add cache breakpoint to the second-to-last user message.

        The system prompt is always cached. For conversation history, we cache
        up to the previous turn so only the latest exchange is uncached.
        """
        msgs = list(messages)
        user_indices = [i for i, m in enumerate(msgs) if m["role"] == "user"]
        if len(user_indices) >= 2:
            idx = user_indices[-2]
            msg = msgs[idx]
            content = msg["content"]
            if isinstance(content, list):
                content = [*content]  # shallow copy
                last = {**content[-1], "cache_control": {"type": "ephemeral"}}
                content[-1] = last
                msgs[idx] = {**msg, "content": content}
            elif isinstance(content, str):
                msgs[idx] = {
                    **msg,
                    "content": [
                        {
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
        return msgs
