from __future__ import annotations

from autonomous_tester.ui.events import (
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


def test_thinking_delta():
    e = ThinkingDelta(text="chunk")
    assert e.text == "chunk"


def test_thinking_finished():
    e = ThinkingFinished(summary="done thinking")
    assert e.summary == "done thinking"


def test_tool_started():
    e = ToolStarted(name="browser", input_preview="goto(url)")
    assert e.name == "browser"
    assert e.input_preview == "goto(url)"


def test_tool_completed_defaults():
    e = ToolCompleted(name="browser", elapsed_ms=120, result_preview="ok", is_error=False)
    assert e.name == "browser"
    assert e.elapsed_ms == 120
    assert e.result_preview == "ok"
    assert e.is_error is False
    assert e.full_result == ""


def test_tool_completed_with_full_result():
    e = ToolCompleted(
        name="git",
        elapsed_ms=500,
        result_preview="diff...",
        is_error=True,
        full_result="full diff output here",
    )
    assert e.is_error is True
    assert e.full_result == "full diff output here"


def test_iteration_started():
    e = IterationStarted(iteration=3, max_iterations=10)
    assert e.iteration == 3
    assert e.max_iterations == 10


def test_tokens_updated():
    e = TokensUpdated(input_tokens=100, output_tokens=200, cache_read=50, cache_creation=25)
    assert e.input_tokens == 100
    assert e.output_tokens == 200
    assert e.cache_read == 50
    assert e.cache_creation == 25


def test_bug_filed():
    e = BugFiled(title="Login fails on mobile")
    assert e.title == "Login fails on mobile"


def test_agent_started():
    e = AgentStarted(prompt="test app login", model="claude-sonnet-4-20250514")
    assert e.prompt == "test app login"
    assert e.model == "claude-sonnet-4-20250514"


def test_run_completed_defaults():
    e = RunCompleted(iterations=5, elapsed_seconds=120.5)
    assert e.iterations == 5
    assert e.elapsed_seconds == 120.5
    assert e.bugs_found == []
    assert e.cost == 0.0
    assert e.session_dump_path == ""


def test_run_completed_full():
    e = RunCompleted(
        iterations=8,
        elapsed_seconds=300.0,
        bugs_found=["bug1", "bug2"],
        cost=1.23,
        session_dump_path="/tmp/session.json",
    )
    assert e.bugs_found == ["bug1", "bug2"]
    assert e.cost == 1.23
    assert e.session_dump_path == "/tmp/session.json"


def test_run_completed_bugs_found_no_mutable_default_sharing():
    e1 = RunCompleted(iterations=1, elapsed_seconds=1.0)
    e2 = RunCompleted(iterations=2, elapsed_seconds=2.0)
    e1.bugs_found.append("oops")
    assert e2.bugs_found == []


def test_phase_changed():
    e = PhaseChanged(phase_index=2, phase_name="browser-testing")
    assert e.phase_index == 2
    assert e.phase_name == "browser-testing"
