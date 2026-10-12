from unittest.mock import MagicMock

import pytest

from loeb.tool_registry import (
    DEFAULT_TOOL_TIMEOUT,
    TOOL_DEFINITIONS,
    TOOL_TIMEOUTS,
    ToolRegistry,
)


def test_tool_definitions_are_valid():
    assert len(TOOL_DEFINITIONS) > 0
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool


def test_tool_names_unique():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_dispatch_unknown_tool():
    registry = ToolRegistry(
        services=MagicMock(),
        browser=MagicMock(),
        audio=MagicMock(),
        backend=MagicMock(),
        reporter=MagicMock(),
        config=MagicMock(),
    )
    result = await registry.dispatch("nonexistent_tool", {})
    assert "Unknown tool" in result


def test_tool_timeouts_exist():
    assert isinstance(TOOL_TIMEOUTS, dict)
    assert DEFAULT_TOOL_TIMEOUT == 60


def test_slow_tools_have_longer_timeout():
    assert TOOL_TIMEOUTS["start_services"] >= 300
    assert TOOL_TIMEOUTS["stop_services"] >= 120


def test_all_defined_tools_have_valid_timeout():
    for tool in TOOL_DEFINITIONS:
        timeout = TOOL_TIMEOUTS.get(tool["name"], DEFAULT_TOOL_TIMEOUT)
        assert timeout > 0


def _registry(backend_dir="", frontend_dir=""):
    config = MagicMock()
    config.backend_dir = backend_dir
    config.frontend_dir = frontend_dir
    return ToolRegistry(
        services=MagicMock(), browser=MagicMock(), audio=MagicMock(),
        backend=MagicMock(), reporter=MagicMock(), config=config,
    )


@pytest.mark.asyncio
async def test_git_diff_unset_frontend_is_an_error_result_not_a_crash(tmp_path):
    reg = _registry(backend_dir=str(tmp_path))
    reg.config.target_profile = reg.config.target_services = reg.config.target_context = ""
    reg.config.profile = None
    result = await reg.dispatch("git_diff", {"repo": "frontend"})
    assert result == "Error: unknown repo 'frontend'. Configured repos: backend."


@pytest.mark.asyncio
async def test_git_diff_unknown_repo_name():
    result = await _registry().dispatch("git_diff", {"repo": "mobile"})
    assert result.startswith("Error: unknown repo 'mobile'")


def test_configured_repos_skips_unset():
    from loeb.tool_registry import configured_repos

    config = _registry(backend_dir="/x").config
    config.target_profile = config.target_services = config.target_context = ""
    config.profile = None
    assert configured_repos(config) == ["backend"]
