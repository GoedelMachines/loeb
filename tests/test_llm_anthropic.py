"""Tests for the Anthropic LLM provider helper methods."""

import copy

from loeb.llm.anthropic import AnthropicProvider
from loeb.llm.base import ToolCall


def _make_provider() -> AnthropicProvider:
    # api_key doesn't need to be valid for helper method tests
    return AnthropicProvider(api_key="sk-ant-test-key", model="claude-sonnet-4-20250514")


def test_init():
    provider = _make_provider()
    assert provider.model == "claude-sonnet-4-20250514"
    assert provider.client is not None
    assert provider.client.api_key == "sk-ant-test-key"


def test_make_assistant_message():
    provider = _make_provider()
    raw = [{"type": "text", "text": "Hello world"}]
    msg = provider.make_assistant_message(raw)
    assert msg == {"role": "assistant", "content": raw}


def test_make_tool_result_message():
    provider = _make_provider()
    tool_calls = [
        ToolCall(id="tc_1", name="git_diff", input={"repo": "backend"}),
        ToolCall(id="tc_2", name="screenshot", input={}),
    ]
    results = ["diff output here", "Error: screenshot failed"]
    msgs = provider.make_tool_result_message(tool_calls, results)

    assert len(msgs) == 1
    msg = msgs[0]
    assert msg["role"] == "user"
    assert len(msg["content"]) == 2

    # First result: no error
    assert msg["content"][0]["type"] == "tool_result"
    assert msg["content"][0]["tool_use_id"] == "tc_1"
    assert msg["content"][0]["content"] == "diff output here"
    assert "is_error" not in msg["content"][0]

    # Second result: error detected
    assert msg["content"][1]["type"] == "tool_result"
    assert msg["content"][1]["tool_use_id"] == "tc_2"
    assert msg["content"][1]["content"] == "Error: screenshot failed"
    assert msg["content"][1]["is_error"] is True


def test_convert_tools_passthrough():
    provider = _make_provider()
    tools = [
        {
            "name": "git_diff",
            "description": "Get the git diff",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "screenshot",
            "description": "Take a screenshot",
            "input_schema": {"type": "object", "properties": {}},
        },
    ]
    result = provider._convert_tools(tools)
    assert result is tools  # exact same object, not a copy


def test_prepare_messages_adds_cache_control():
    provider = _make_provider()
    messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second answer"},
        {"role": "user", "content": "third question"},
    ]

    original = copy.deepcopy(messages)
    prepared = provider._prepare_messages(messages)

    # Original should not be mutated
    assert messages == original

    # Second-to-last user message (index 2, "second question") should have cache_control
    cached_msg = prepared[2]
    assert isinstance(cached_msg["content"], list)
    assert cached_msg["content"][0]["type"] == "text"
    assert cached_msg["content"][0]["text"] == "second question"
    assert cached_msg["content"][0]["cache_control"] == {"type": "ephemeral"}

    # Other user messages should be unchanged
    assert prepared[0]["content"] == "first question"
    assert prepared[4]["content"] == "third question"


def test_prepare_messages_list_content_adds_cache_control():
    """When the second-to-last user message has list content, cache_control goes on last block."""
    provider = _make_provider()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "result1"},
                {"type": "tool_result", "tool_use_id": "2", "content": "result2"},
            ],
        },
        {"role": "assistant", "content": "response"},
        {"role": "user", "content": "latest question"},
    ]

    original = copy.deepcopy(messages)
    prepared = provider._prepare_messages(messages)

    # Original not mutated
    assert messages == original

    # First user message (second-to-last user) should have cache_control on last block
    cached_content = prepared[0]["content"]
    assert isinstance(cached_content, list)
    assert "cache_control" not in cached_content[0]
    assert cached_content[1]["cache_control"] == {"type": "ephemeral"}


def test_prepare_messages_single_user_no_cache():
    """With only one user message, no cache_control is added."""
    provider = _make_provider()
    messages = [{"role": "user", "content": "only question"}]
    prepared = provider._prepare_messages(messages)
    assert prepared[0]["content"] == "only question"
