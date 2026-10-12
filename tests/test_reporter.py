import json
import os
from unittest.mock import MagicMock, patch

import pytest

from loeb.tools.reporter import Reporter


@pytest.fixture
def config():
    mock = MagicMock()
    mock.slack_bot_token = "xoxb-test"
    mock.slack_channel = "#alerts"
    mock.github_repo = "o/r"
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


FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_GH_LOG"]
body = sys.stdin.read() if "--body-file=-" in args else None
with open(log, "a") as f:
    f.write(json.dumps({"argv": args, "stdin": body}) + "\n")
# Like real gh: positional arguments after `issue create` are rejected.
positional = [a for a in args[2:] if not a.startswith("--")]
if positional:
    sys.stderr.write(f'unknown argument "{positional[0]}"; please quote all values\n')
    sys.exit(1)
labels = [a.split("=", 1)[1] for a in args if a.startswith("--label=")]
missing = [lbl for lbl in labels if lbl not in os.environ.get("FAKE_GH_LABELS", "").split(",")]
if missing:
    sys.stderr.write(f"could not add label: '{missing[0]}' not found\n")
    sys.exit(1)
print("https://github.com/o/r/issues/7")
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return calls


def test_issue_filed_without_labels_on_repo_lacking_loeb_label(config, fake_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_LABELS", "bug")  # repo has "bug" but not "loeb"
    result = Reporter(config).file_github_issue("Bug T", "Body B", ["bug"])
    assert result == "GitHub issue created (no labels): https://github.com/o/r/issues/7"
    first, retry = fake_gh()
    assert "--label=loeb" in first["argv"]
    assert not any(a.startswith("--label") for a in retry["argv"])
    assert retry["argv"].count("--title=Bug T") == 1
    assert retry["stdin"] == "Body B"


def test_issue_filed_with_labels_when_they_exist(config, fake_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_LABELS", "loeb,bug")
    result = Reporter(config).file_github_issue("Bug", "Body", ["bug"])
    assert result == "GitHub issue created: https://github.com/o/r/issues/7"
    assert len(fake_gh()) == 1


def test_option_like_title_stays_a_value(config, fake_gh, monkeypatch):
    monkeypatch.setenv("FAKE_GH_LABELS", "loeb")
    result = Reporter(config).file_github_issue("--web", "--repo=evil/x", [])
    assert result.startswith("GitHub issue created")
    (call,) = fake_gh()
    assert "--title=--web" in call["argv"] and "--repo=evil/x" not in call["argv"]
    assert call["stdin"] == "--repo=evil/x"


def test_missing_github_repo_is_an_error(config):
    from loeb.llm.base import is_tool_error

    config.github_repo = ""
    assert is_tool_error(Reporter(config).file_github_issue("t", "b", []))
