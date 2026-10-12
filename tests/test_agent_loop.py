"""Agent.run driven end to end by a scripted provider (no API, no browser)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from loeb.agent import Agent
from tests.fake_llm import ScriptedProvider


class StubRegistry:
    """Dispatch that raises for chosen tools and echoes for the rest."""

    def __init__(self, raises: dict[str, Exception] | None = None):
        self.raises = raises or {}
        self.browser = None

    async def dispatch(self, tool_name, tool_input):
        if tool_name in self.raises:
            raise self.raises[tool_name]
        if tool_name == "click":
            return f"Clicked element: {tool_input['selector']}"
        return f"ok {tool_name}"


def make_agent(registry, provider):
    config = MagicMock()
    config.max_tokens = 1024
    config.model = "claude-sonnet-4-6"
    config.provider = "anthropic"
    config.target_context = ""
    return Agent(config=config, registry=registry, provider=provider)


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CI", "1")


@pytest.mark.asyncio
async def test_tool_exception_becomes_error_result_and_run_continues():
    provider = ScriptedProvider([
        [("navigate", {"url": "http://localhost:1"})],
        [("get_page_text", {})],
        "end",
    ])
    registry = StubRegistry(raises={"navigate": RuntimeError("net::ERR_CONNECTION_REFUSED")})
    agent = make_agent(registry, provider)
    await agent.run("go")
    assert provider.calls == 3
    first = provider.tool_results[0][0]
    assert first.startswith("Error: navigate raised RuntimeError")
    assert "ERR_CONNECTION_REFUSED" in first
    assert agent.tool_errors == 1 and agent.tool_successes == 1


@pytest.mark.asyncio
async def test_missing_argument_is_reported_not_raised():
    provider = ScriptedProvider([[("click", {})], "end"])
    agent = make_agent(StubRegistry(), provider)
    await agent.run("go")
    assert provider.tool_results[0][0] == "Error: click is missing required argument 'selector'"


@pytest.mark.asyncio
async def test_one_failing_tool_does_not_sink_parallel_siblings():
    provider = ScriptedProvider([
        [("git_diff", {"repo": "frontend"}), ("start_services", {})],
        "end",
    ])
    registry = StubRegistry(raises={"git_diff": FileNotFoundError("No such file: ''")})
    agent = make_agent(registry, provider)
    await agent.run("go")
    results = provider.tool_results[0]
    assert results[0].startswith("Error: git_diff raised FileNotFoundError")
    assert results[1] == "ok start_services"


@pytest.mark.asyncio
async def test_bug_counted_but_not_filed_when_filing_fails():
    class Reg(StubRegistry):
        async def dispatch(self, tool_name, tool_input):
            if tool_name == "file_github_issue":
                return "Error: GITHUB_REPO not configured, so the issue was not filed."
            return await super().dispatch(tool_name, tool_input)

    provider = ScriptedProvider([
        [("file_github_issue", {"title": "Mute broken", "body": "b", "labels": []})],
        "end",
    ])
    agent = make_agent(Reg(), provider)
    await agent.run("go")
    assert agent.bugs_found == ["Mute broken"]
    assert agent.issues_filed == []


def test_cap_tool_result():
    from loeb.agent import cap_tool_result

    assert cap_tool_result("short", 10) == "short"
    capped = cap_tool_result("x" * 25, 10)
    assert capped.startswith("x" * 10) and "[truncated 15 more characters]" in capped


@pytest.mark.asyncio
async def test_huge_tool_result_is_capped_before_reaching_the_model():
    from loeb.agent import MAX_TOOL_RESULT_CHARS

    class Huge(StubRegistry):
        async def dispatch(self, tool_name, tool_input):
            return "+" * 8_000_000  # an 8 MB diff

    provider = ScriptedProvider([[("git_diff", {"repo": "backend"})], "end"])
    agent = make_agent(Huge(), provider)
    await agent.run("go")
    assert len(provider.tool_results[0][0]) < MAX_TOOL_RESULT_CHARS + 100


@pytest.mark.asyncio
async def test_request_stop_ends_the_run_at_the_next_checkpoint():
    import asyncio

    provider = ScriptedProvider([[("get_page_text", {})]] * 50 + ["end"])
    agent = make_agent(StubRegistry(), provider)

    class StopAfterTwo(StubRegistry):
        async def dispatch(self, tool_name, tool_input):
            if provider.calls == 2:
                agent.request_stop()
            await asyncio.sleep(0)
            return "ok"

    agent.registry = StopAfterTwo()
    await agent.run("go")
    assert provider.calls == 2
    assert agent.finished is False and agent.stop_problem == "stopped by the user"


@pytest.mark.asyncio
async def test_pause_holds_the_loop_until_resumed():
    import asyncio

    provider = ScriptedProvider([[("get_page_text", {})]] * 3 + ["end"])
    agent = make_agent(StubRegistry(), provider)
    agent.pause()
    run = asyncio.create_task(agent.run("go"))
    await asyncio.sleep(0.3)
    assert provider.calls == 0 and not run.done()
    agent.resume()
    await asyncio.wait_for(run, 5)
    assert provider.calls == 4 and agent.finished is True


@pytest.mark.asyncio
async def test_cancel_after_stop_request_is_a_clean_stop():
    import asyncio

    class Hanging(ScriptedProvider):
        async def complete(self, *a, **k):
            self.calls += 1
            await asyncio.sleep(3600)

    provider = Hanging([])
    agent = make_agent(StubRegistry(), provider)
    run = asyncio.create_task(agent.run("go"))
    await asyncio.sleep(0.05)
    agent.request_stop()
    run.cancel()
    await asyncio.wait_for(run, 5)  # no CancelledError escapes
    assert agent.stop_problem == "stopped by the user" and agent.error is None


def test_agent_offers_login_only_with_a_way_to_sign_in(monkeypatch):
    from loeb.profile import Auth, Profile

    def names(profile, supabase_url=""):
        monkeypatch.setattr("loeb.profile.profile_of", lambda c: profile)
        agent = make_agent(StubRegistry(), ScriptedProvider(["end"]))
        agent.config.supabase_url = supabase_url
        agent.config.supabase_anon_key = "anon" if supabase_url else ""
        from loeb.agent import Agent
        return {t["name"] for t in Agent(agent.config, agent.registry, agent.provider).tools}

    assert "login" not in names(Profile())
    assert "login" in names(Profile(), supabase_url="https://x.supabase.co")
    assert "login" in names(Profile(auth=Auth()))
