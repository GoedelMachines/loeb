from loeb.llm.base import ToolCall
from loeb.llm.openai import OpenAIProvider


def _make_provider(**kwargs):
    defaults = {"model": "gpt-4o", "api_key": "test-key"}
    defaults.update(kwargs)
    return OpenAIProvider(**defaults)


def test_init():
    provider = _make_provider()
    assert provider.model == "gpt-4o"
    assert provider.client.api_key == "test-key"


def test_init_with_base_url():
    provider = _make_provider(base_url="https://custom.api.example.com/v1")
    assert provider.model == "gpt-4o"
    assert str(provider.client.base_url) == "https://custom.api.example.com/v1/"


def test_convert_tools():
    anthropic_tools = [
        {
            "name": "git_diff",
            "description": "Show recent git changes",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository path"},
                },
                "required": ["repo"],
            },
        },
        {
            "name": "screenshot",
            "description": "Take a screenshot",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
    ]
    result = OpenAIProvider._convert_tools(anthropic_tools)
    assert len(result) == 2

    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "git_diff"
    assert result[0]["function"]["description"] == "Show recent git changes"
    assert result[0]["function"]["parameters"] == anthropic_tools[0]["input_schema"]

    assert result[1]["function"]["name"] == "screenshot"
    assert result[1]["function"]["parameters"] == anthropic_tools[1]["input_schema"]


def test_make_assistant_message():
    provider = _make_provider()
    raw = {
        "content": "I'll check the diff.",
        "tool_calls": [
            {
                "id": "call_abc",
                "type": "function",
                "function": {
                    "name": "git_diff",
                    "arguments": '{"repo": "backend"}',
                },
            }
        ],
    }
    msg = provider.make_assistant_message(raw)
    assert msg["role"] == "assistant"
    assert msg["content"] == "I'll check the diff."
    assert len(msg["tool_calls"]) == 1
    assert msg["tool_calls"][0]["id"] == "call_abc"


def test_make_assistant_message_no_tools():
    provider = _make_provider()
    raw = {"content": "All done.", "tool_calls": None}
    msg = provider.make_assistant_message(raw)
    assert msg["role"] == "assistant"
    assert msg["content"] == "All done."
    assert "tool_calls" not in msg


def test_make_tool_result_message():
    provider = _make_provider()
    tool_calls = [
        ToolCall(id="call_1", name="git_diff", input={"repo": "backend"}),
        ToolCall(id="call_2", name="screenshot", input={}),
    ]
    results = ["diff output here", "Screenshot saved to s1.png"]
    msgs = provider.make_tool_result_message(tool_calls, results)

    assert len(msgs) == 2
    assert msgs[0] == {"role": "tool", "tool_call_id": "call_1", "content": "diff output here"}
    assert msgs[1] == {
        "role": "tool",
        "tool_call_id": "call_2",
        "content": "Screenshot saved to s1.png",
    }


def test_convert_messages_plain_user():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = OpenAIProvider._convert_messages(messages)
    assert result is messages  # passthrough, same object
