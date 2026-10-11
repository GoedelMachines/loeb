from unittest.mock import MagicMock

from autonomous_tester.agent import SYSTEM_PROMPT, Agent
from autonomous_tester.llm.base import is_tool_error


def make_agent():
    provider = MagicMock()
    registry = MagicMock()
    config = MagicMock()
    config.max_tokens = 16384
    config.model = "claude-sonnet-4-6"
    agent = Agent(config=config, registry=registry, provider=provider)
    return agent


def test_agent_init():
    agent = make_agent()
    assert agent.max_iterations == 200


def test_agent_system_prompt_includes_key_info():
    assert "Löb" in SYSTEM_PROMPT
    assert "voice" in SYSTEM_PROMPT.lower()
    assert "backend" in SYSTEM_PROMPT.lower()


def test_agent_accepts_event_callback():
    agent = make_agent()
    assert agent.on_event is None
    cb = MagicMock()
    agent.on_event = cb
    assert agent.on_event is cb


def test_agent_emit_calls_callback():
    agent = make_agent()
    cb = MagicMock()
    agent.on_event = cb
    event = {"type": "test"}
    agent._emit(event)
    cb.assert_called_once_with(event)


def test_agent_emit_noop_when_no_callback():
    agent = make_agent()
    assert agent.on_event is None
    agent._emit({"type": "test"})


def test_is_tool_error_used_in_agent():
    """Verify the shared is_tool_error function works as expected."""
    assert is_tool_error("Error: something broke") is True
    assert is_tool_error("Browser launched.") is False


def test_play_sound_noop_when_ci_set(monkeypatch):
    """_play_sound does nothing when CI env var is set."""
    monkeypatch.setenv("CI", "true")
    from autonomous_tester.agent import _play_sound

    _play_sound("/System/Library/Sounds/Glass.aiff")


def test_play_sound_noop_on_non_darwin(monkeypatch):
    """_play_sound does nothing on non-Darwin platforms."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("autonomous_tester.agent.sys.platform", "linux")
    from autonomous_tester.agent import _play_sound

    _play_sound("/System/Library/Sounds/Glass.aiff")


def test_build_system_prompt_appends_target_context(tmp_path):
    from autonomous_tester.agent import build_system_prompt

    target = tmp_path / "target.md"
    target.write_text("Selector: `.orb`")
    config = MagicMock()
    config.target_context = str(target)
    prompt = build_system_prompt(config)
    assert prompt.startswith(SYSTEM_PROMPT)
    assert "# Target" in prompt and ".orb" in prompt
