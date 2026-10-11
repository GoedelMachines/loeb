from autonomous_tester.llm.base import (
    CompletionResult,
    StreamEvent,
    ToolCall,
    compress_messages,
    estimate_tokens,
    is_tool_error,
)


def test_tool_call_fields():
    tc = ToolCall(id="1", name="git_diff", input={"repo": "backend"})
    assert tc.id == "1"
    assert tc.name == "git_diff"
    assert tc.input == {"repo": "backend"}


def test_completion_result_defaults():
    r = CompletionResult(
        stop_reason="end_turn",
        tool_calls=[],
        raw_content=None,
        input_tokens=100,
        output_tokens=50,
    )
    assert r.cache_read_tokens == 0
    assert r.cache_creation_tokens == 0


def test_stream_event_defaults():
    e = StreamEvent(type="thinking")
    assert e.text == ""
    assert e.tool_name == ""


def test_is_tool_error_detects_known_prefixes():
    assert is_tool_error("Error: something broke") is True
    assert is_tool_error("Failed to create issue: timeout") is True
    assert is_tool_error("Could not click '.btn': not found") is True
    assert is_tool_error("Timeout waiting for '.btn': 10s") is True
    assert is_tool_error("No browser page open.") is True
    assert is_tool_error("Unknown tool: foo") is True
    assert is_tool_error("ERROR: docker-compose failed") is True


def test_is_tool_error_rejects_normal_results():
    assert is_tool_error("Browser launched with virtual audio device.") is False
    assert is_tool_error("Navigated to http://localhost. Title: Example App") is False
    assert is_tool_error("No errors found in console.") is False
    assert is_tool_error("Query returned 0 rows.") is False
    assert is_tool_error("Screenshot saved to screenshots/s1.png") is False


def test_estimate_tokens():
    assert estimate_tokens([]) == 0
    msg = {"role": "user", "content": "hello world"}
    tokens = estimate_tokens([msg])
    assert tokens > 0
    assert isinstance(tokens, int)


def test_compress_messages_keeps_recent():
    msgs = [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": "thinking"},
        {"role": "user", "content": "x" * 1000},
        {"role": "assistant", "content": "y" * 1000},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    compressed = compress_messages(msgs, keep_recent=2)
    # Last 2 messages (1 turn) kept intact
    assert compressed[-1]["content"] == "recent answer"
    assert compressed[-2]["content"] == "recent question"
    # Older messages truncated
    assert len(compressed[2]["content"]) < 1000
    assert len(compressed[3]["content"]) < 1000


def test_compress_messages_preserves_short_content():
    msgs = [
        {"role": "user", "content": "short"},
        {"role": "assistant", "content": "also short"},
    ]
    compressed = compress_messages(msgs, keep_recent=0)
    assert compressed[0]["content"] == "short"
    assert compressed[1]["content"] == "also short"


def test_compress_messages_handles_list_content():
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "x" * 1000},
                {"type": "tool_result", "tool_use_id": "2", "content": "short"},
            ],
        },
        {"role": "assistant", "content": "recent"},
    ]
    compressed = compress_messages(msgs, keep_recent=1)
    block = compressed[0]["content"][0]
    assert len(block["content"]) < 1000
    # Short content untouched
    assert compressed[0]["content"][1]["content"] == "short"
