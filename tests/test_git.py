from unittest.mock import MagicMock, patch

from autonomous_tester.tools.git import git_diff


def test_git_diff_returns_diff():
    mock_result = MagicMock()
    mock_result.stdout = "diff --git a/foo.py b/foo.py\n+new line"
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = git_diff("/tmp/repo")
        assert "+new line" in result
        mock_run.assert_called()


def test_git_diff_no_changes():
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result):
        result = git_diff("/tmp/repo")
        assert "No changes" in result
