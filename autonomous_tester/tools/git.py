import subprocess


def git_diff(repo_dir: str, base: str = "HEAD~1") -> str:
    result = subprocess.run(
        ["git", "diff", base, "--stat"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    stat = result.stdout.strip()

    result = subprocess.run(
        ["git", "diff", base],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    diff = result.stdout.strip()

    if not diff:
        return "No changes detected in the repository."

    log_result = subprocess.run(
        ["git", "log", "--oneline", f"{base}..HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    log = log_result.stdout.strip()

    parts = []
    if log:
        parts.append(f"Recent commits:\n{log}")
    if stat:
        parts.append(f"Changed files:\n{stat}")
    parts.append(f"Full diff:\n{diff}")
    return "\n\n".join(parts)
