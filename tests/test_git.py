import subprocess

import pytest

from loeb.tools.git import git_diff, resolve_base


def _run(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _run(r, "init", "-q")
    (r / "foo.py").write_text("old\n")
    _run(r, "add", "foo.py")
    _run(r, "commit", "-qm", "first")
    (r / "foo.py").write_text("old\nnew line\n")
    _run(r, "commit", "-qam", "second")
    return r


def test_git_diff_returns_diff(repo):
    result = git_diff(str(repo))
    assert "+new line" in result
    assert "second" in result
    assert "foo.py" in result


def test_git_diff_no_changes(repo):
    assert "No changes" in git_diff(str(repo), "HEAD")


@pytest.mark.parametrize("base", ["--output={victim}", "-p", "--no-index", "-"])
def test_git_diff_refuses_option_like_base(repo, tmp_path, base):
    victim = tmp_path / "victim.txt"
    victim.write_text("important data\n")
    result = git_diff(str(repo), base.format(victim=victim))
    assert result.startswith("Error:")
    assert victim.read_text() == "important data\n"


def test_git_diff_output_option_writes_nothing(repo, tmp_path):
    target = tmp_path / "created-by-git.txt"
    result = git_diff(str(repo), f"--output={target}")
    assert result.startswith("Error:")
    assert not target.exists()


def test_git_diff_unknown_ref_is_an_error(repo):
    assert git_diff(str(repo), "no-such-branch").startswith("Error:")


def test_resolve_base_returns_sha(repo):
    sha = resolve_base(str(repo), "HEAD~1")
    assert sha and len(sha) == 40 and not sha.startswith("-")
    assert resolve_base(str(repo), "--output=/tmp/x") is None
    assert resolve_base(str(repo), "") is None


def test_git_diff_unset_dir_is_an_error():
    assert git_diff("") == "Error: no repo directory configured."


def test_git_diff_missing_dir_is_an_error(tmp_path):
    assert "does not exist" in git_diff(str(tmp_path / "nope"))


def test_git_diff_plain_directory_is_not_reported_as_clean(tmp_path):
    result = git_diff(str(tmp_path))
    assert result == f"Error: {tmp_path} is not a git repository."


def test_git_diff_single_commit_repo_explains_head_1(tmp_path):
    r = tmp_path / "one"
    r.mkdir()
    _run(r, "init", "-q")
    (r / "a").write_text("a")
    _run(r, "add", "a")
    _run(r, "commit", "-qm", "only")
    result = git_diff(str(r))
    assert result.startswith("Error:") and "base='HEAD'" in result
