import subprocess
from pathlib import Path


def _git(repo_dir: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )


def resolve_base(repo_dir: str, base: str) -> str | None:
    """Resolve a model-supplied ref to a commit SHA, or None if it is not one.

    `base` comes from the model, so it must never reach git as an option
    (`--output=PATH` makes `git diff` write to an arbitrary file). Refs that start
    with '-' are rejected outright; anything else is resolved with
    `--end-of-options`, and only the resulting SHA is passed on.
    """
    if not base or base.startswith("-"):
        return None
    result = _git(repo_dir, "rev-parse", "--verify", "--quiet", "--end-of-options",
                  f"{base}^{{commit}}")
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        return None
    return sha


def check_repo(repo_dir: str) -> str | None:
    """None if repo_dir is a git work tree, else an "Error: ..." explaining why not."""
    if not repo_dir:
        return "Error: no repo directory configured."
    if not Path(repo_dir).is_dir():
        return f"Error: repo directory {repo_dir} does not exist."
    result = _git(repo_dir, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        return f"Error: {repo_dir} is not a git repository."
    return None


def git_diff(repo_dir: str, base: str = "HEAD~1") -> str:
    problem = check_repo(repo_dir)
    if problem:
        return problem
    sha = resolve_base(repo_dir, base)
    if sha is None:
        hint = " (a repo with a single commit has no HEAD~1; try base='HEAD')" \
            if base == "HEAD~1" else ""
        return f"Error: '{base}' is not a commit in {repo_dir}{hint}."

    stat = _git(repo_dir, "diff", "--stat", sha, "--").stdout.strip()
    result = _git(repo_dir, "diff", sha, "--")
    if result.returncode != 0:
        return f"Error: git diff failed in {repo_dir}: {result.stderr.strip()}"
    diff = result.stdout.strip()

    if not diff:
        return "No changes detected in the repository."

    log = _git(repo_dir, "log", "--oneline", f"{sha}..HEAD", "--").stdout.strip()

    parts = []
    if log:
        parts.append(f"Recent commits:\n{log}")
    if stat:
        parts.append(f"Changed files:\n{stat}")
    parts.append(f"Full diff:\n{diff}")
    return "\n\n".join(parts)
