from unittest.mock import MagicMock, patch

import pytest

from autonomous_tester.tools.reporter import Reporter


@pytest.fixture
def config():
    mock = MagicMock()
    mock.slack_bot_token = "xoxb-test"
    mock.slack_channel = "#alerts"
    mock.github_repo = "example-org/example-app"
    return mock


def test_reporter_init(config):
    r = Reporter(config)
    assert r.config.slack_channel == "#alerts"


def test_file_github_issue(config):
    mock_result = MagicMock()
    mock_result.stdout = "https://github.com/example-org/example-app/issues/42"
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result):
        r = Reporter(config)
        result = r.file_github_issue("Test bug", "Description here", ["bug"])
        assert "issues/42" in result


def test_file_github_issue_failure(config):
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "auth error"
    mock_result.returncode = 1
    with patch("subprocess.run", return_value=mock_result):
        r = Reporter(config)
        result = r.file_github_issue("Test bug", "Desc", [])
        assert "Failed" in result
