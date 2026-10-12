from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from openai import AsyncOpenAI

from loeb.llm.base import (
    CompletionResult,
    LLMProvider,
    StreamEvent,
    ToolCall,
)


class OpenAIProvider(LLMProvider):
    """LLM provider for OpenAI models (GPT-4o, o3, etc.)."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 3}
        if base_url is not None:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

    # -- format conversion helpers --

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Convert Anthropic-format tool defs to OpenAI function calling format."""
        converted = []
        for tool in tools:
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                }
            )
        return converted

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list[dict]:
        """Passthrough -- messages are already in OpenAI format."""
        return messages

    # -- main completion --

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 16384,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> CompletionResult:
        openai_messages = [{"role": "system", "content": system}] + self._convert_messages(
            messages
        )
        openai_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        stream = await self.client.chat.completions.create(**kwargs)

        # Accumulate streamed response
        text_parts: list[str] = []
        # tool_calls indexed by their stream index
        tool_call_acc: dict[int, dict[str, Any]] = {}
        input_tokens = 0
        output_tokens = 0
        finish_reason: str | None = None

        async for chunk in stream:
            # Usage comes on the final chunk
            if chunk.usage is not None:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason

            delta = choice.delta

            # Text content
            if delta.content:
                text_parts.append(delta.content)
                if on_event:
                    on_event(StreamEvent(type="thinking", text=delta.content))

            # Tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_acc:
                        tool_call_acc[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    acc = tool_call_acc[idx]
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc["name"] = tc_delta.function.name
                            if on_event:
                                on_event(
                                    StreamEvent(
                                        type="tool_start",
                                        tool_name=tc_delta.function.name,
                                    )
                                )
                        if tc_delta.function.arguments:
                            acc["arguments"] += tc_delta.function.arguments

        # Build tool calls list
        parsed_tool_calls: list[ToolCall] = []
        raw_tool_calls: list[dict] | None = None
        if tool_call_acc:
            raw_tool_calls = []
            for idx in sorted(tool_call_acc):
                acc = tool_call_acc[idx]
                try:
                    args = json.loads(acc["arguments"]) if acc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                parsed_tool_calls.append(ToolCall(id=acc["id"], name=acc["name"], input=args))
                raw_tool_calls.append(
                    {
                        "id": acc["id"],
                        "type": "function",
                        "function": {
                            "name": acc["name"],
                            "arguments": acc["arguments"],
                        },
                    }
                )

        text = "".join(text_parts) or None
        stop_reason = {
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "content_filter": "refusal",
        }.get(finish_reason, "end_turn")

        return CompletionResult(
            stop_reason=stop_reason,
            tool_calls=parsed_tool_calls,
            raw_content={"content": text, "tool_calls": raw_tool_calls},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # -- message builders --

    def make_assistant_message(self, raw_content: Any) -> dict:
        msg: dict[str, Any] = {"role": "assistant"}
        if raw_content.get("content") is not None:
            msg["content"] = raw_content["content"]
        if raw_content.get("tool_calls") is not None:
            msg["tool_calls"] = raw_content["tool_calls"]
        return msg

    def make_tool_result_message(
        self, tool_calls: list[ToolCall], results: list[str]
    ) -> list[dict]:
        return [
            {"role": "tool", "tool_call_id": tc.id, "content": result}
            for tc, result in zip(tool_calls, results)
        ]
