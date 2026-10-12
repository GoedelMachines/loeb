"""Tests for CI run mode and the exit-code contract (0 pass, 1 bugs, 2 error)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fake_llm import ScriptedProvider


def test_parse_args_ci_flag():
    """--ci flag is parsed correctly."""
    from loeb.run import parse_args

    with patch("sys.argv", ["run", "--ci", "Test login"]):
        args = parse_args()
    assert args.ci is True
    assert args.prompt == "Test login"


def test_parse_args_ci_default():
    """--ci defaults to False."""
    from loeb.run import parse_args

    with patch("sys.argv", ["run", "Test login"]):
        args = parse_args()
    assert args.ci is False


@pytest.mark.parametrize("n", ["0", "-3"])
def test_parse_args_rejects_non_positive_max_iterations(n):
    from loeb.run import parse_args

    with patch("sys.argv", ["run", "--ci", "--max-iterations", n]), pytest.raises(SystemExit):
        parse_args()


def _mock_stack(*, bugs=(), finished=True, run_side_effect=None):
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=run_side_effect)
    agent.bugs_found = list(bugs)
    agent.finished = finished
    agent.error = None
    agent.stop_problem = None if finished else "hit the iteration cap (5) before finishing"
    browser = MagicMock()
    browser.close = AsyncMock()
    services = MagicMock()
    return services, browser, agent


async def _ci_with(stack):
    from loeb.run import _run_ci

    with patch("loeb.run._build_stack", return_value=stack):
        return await _run_ci(MagicMock(), prompt="Test login", headless=True)


@pytest.mark.asyncio
async def test_run_ci_returns_exit_code_0_no_bugs():
    stack = _mock_stack()
    assert await _ci_with(stack) == 0
    services, browser, agent = stack
    agent.run.assert_awaited_once_with(prompt="Test login")
    browser.close.assert_awaited_once()
    services.stop_all.assert_called_once()


@pytest.mark.asyncio
async def test_run_ci_returns_exit_code_1_bugs_found():
    assert await _ci_with(_mock_stack(bugs=["Login button broken"])) == 1


@pytest.mark.asyncio
async def test_run_ci_returns_exit_code_2_on_crash():
    stack = _mock_stack(run_side_effect=RuntimeError("stack crashed"))
    assert await _ci_with(stack) == 2
    services, browser, _ = stack
    browser.close.assert_awaited_once()  # cleanup still happens on crash
    services.stop_all.assert_called_once()


@pytest.mark.asyncio
async def test_run_ci_unfinished_run_is_not_a_pass():
    assert await _ci_with(_mock_stack(finished=False)) == 2


@pytest.mark.asyncio
async def test_run_ci_setup_failure_is_exit_2_not_1():
    from loeb.run import _run_ci

    with patch("loeb.run._build_stack", side_effect=FileNotFoundError("/nope.md")):
        assert await _run_ci(MagicMock(), prompt="x", headless=True) == 2


# --- end to end through the real _build_stack / Agent, with a scripted LLM ---


@pytest.fixture
def ci_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CI", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for var in ("LOEB_CONTEXT", "TARGET_SERVICES", "BACKEND_DIR", "FRONTEND_DIR"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


async def _real_ci(turns, max_iterations=None):
    from loeb.config import Config
    from loeb.run import _run_ci

    provider = ScriptedProvider(turns)
    with patch("loeb.llm.create_provider", return_value=provider):
        return await _run_ci(Config(), "go", headless=True, max_iterations=max_iterations)


@pytest.mark.asyncio
async def test_e2e_finished_run_passes(ci_env):
    assert await _real_ci(["end"]) == 0
    assert list((ci_env / "runs").glob("*.json"))


@pytest.mark.asyncio
async def test_e2e_iteration_cap_is_exit_2(ci_env):
    turns = [[("stop_services", {})]] * 5
    assert await _real_ci(turns, max_iterations=3) == 2


@pytest.mark.asyncio
async def test_e2e_missing_target_context_is_exit_2(ci_env, monkeypatch):
    monkeypatch.setenv("LOEB_CONTEXT", str(ci_env / "nope.md"))
    assert await _real_ci(["end"]) == 2


@pytest.mark.asyncio
async def test_e2e_missing_anthropic_key_is_exit_2(ci_env, monkeypatch):
    from loeb.config import Config
    from loeb.run import _run_ci

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert await _run_ci(Config(), "go", headless=True) == 2


@pytest.mark.asyncio
async def test_e2e_crash_still_writes_session_dump(ci_env):
    from loeb.config import Config
    from loeb.run import _run_ci

    class Exploding(ScriptedProvider):
        async def complete(self, *a, **k):
            raise RuntimeError("Error code: 401 authentication_error")

    with patch("loeb.llm.create_provider", return_value=Exploding([])):
        assert await _run_ci(Config(), "go", headless=True) == 2
    (dump,) = (ci_env / "runs").glob("*.json")
    assert "401" in dump.read_text()


@pytest.mark.asyncio
async def test_e2e_truncated_reply_is_continued_not_treated_as_done(ci_env):
    from loeb.llm.base import CompletionResult

    class Truncating(ScriptedProvider):
        async def complete(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                return CompletionResult("max_tokens", [], "half a repl", 1, 1)
            return CompletionResult("end_turn", [], "done", 1, 1)

    provider = Truncating([])
    from loeb.config import Config
    from loeb.run import _run_ci

    with patch("loeb.llm.create_provider", return_value=provider):
        assert await _run_ci(Config(), "go", headless=True) == 0
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_e2e_refusal_is_exit_2(ci_env):
    from loeb.llm.base import CompletionResult

    class Refusing(ScriptedProvider):
        async def complete(self, *a, **k):
            return CompletionResult("refusal", [], "", 1, 1)

    from loeb.config import Config
    from loeb.run import _run_ci

    with patch("loeb.llm.create_provider", return_value=Refusing([])):
        assert await _run_ci(Config(), "go", headless=True) == 2
