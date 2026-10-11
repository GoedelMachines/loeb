"""Tests for CI run mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_parse_args_ci_flag():
    """--ci flag is parsed correctly."""
    from autonomous_tester.run import parse_args

    with patch("sys.argv", ["run", "--ci", "Test login"]):
        args = parse_args()
    assert args.ci is True
    assert args.prompt == "Test login"


def test_parse_args_ci_default():
    """--ci defaults to False."""
    from autonomous_tester.run import parse_args

    with patch("sys.argv", ["run", "Test login"]):
        args = parse_args()
    assert args.ci is False


@pytest.mark.asyncio
async def test_run_ci_returns_exit_code_0_no_bugs():
    """CI mode returns 0 when agent finds no bugs."""
    from autonomous_tester.run import _run_ci

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock()
    mock_agent.bugs_found = []
    mock_agent._print_summary = MagicMock()
    mock_agent._dump_session = MagicMock()

    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()

    mock_services = MagicMock()

    with patch("autonomous_tester.run._build_stack", return_value=(mock_services, mock_browser, mock_agent)):
        code = await _run_ci(MagicMock(), prompt="Test login", headless=True)

    assert code == 0
    mock_agent.run.assert_awaited_once_with(prompt="Test login")
    mock_browser.close.assert_awaited_once()
    mock_services.stop_all.assert_called_once()


@pytest.mark.asyncio
async def test_run_ci_returns_exit_code_1_bugs_found():
    """CI mode returns 1 when agent finds bugs."""
    from autonomous_tester.run import _run_ci

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock()
    mock_agent.bugs_found = ["Login button broken"]
    mock_agent._print_summary = MagicMock()
    mock_agent._dump_session = MagicMock()

    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()

    mock_services = MagicMock()

    with patch("autonomous_tester.run._build_stack", return_value=(mock_services, mock_browser, mock_agent)):
        code = await _run_ci(MagicMock(), prompt="Test login", headless=True)

    assert code == 1


@pytest.mark.asyncio
async def test_run_ci_returns_exit_code_2_on_crash():
    """CI mode returns 2 when agent crashes."""
    from autonomous_tester.run import _run_ci

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("stack crashed"))
    mock_agent.bugs_found = []
    mock_agent._print_summary = MagicMock()
    mock_agent._dump_session = MagicMock()

    mock_browser = MagicMock()
    mock_browser.close = AsyncMock()

    mock_services = MagicMock()

    with patch("autonomous_tester.run._build_stack", return_value=(mock_services, mock_browser, mock_agent)):
        code = await _run_ci(MagicMock(), prompt="Test login", headless=True)

    assert code == 2
    # Cleanup still happens on crash
    mock_browser.close.assert_awaited_once()
    mock_services.stop_all.assert_called_once()
