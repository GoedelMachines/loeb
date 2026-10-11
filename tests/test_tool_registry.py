from unittest.mock import MagicMock

import pytest

from autonomous_tester.tool_registry import (
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
