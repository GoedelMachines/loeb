import subprocess

import httpx

from loeb.config import Config


class Reporter:
    def __init__(self, config: Config):
        self.config = config

    def file_github_issue(self, title: str, body: str, labels: list[str]) -> str:
        if not self.config.github_repo:
            return (
                "Error: GITHUB_REPO not configured (owner/name), so the issue was not filed."
                " Put the bug and its evidence in your final summary instead."
            )
        safe_labels = ["loeb"] + [lbl for lbl in labels if lbl != "loeb"]

        def create(with_labels: list[str]) -> subprocess.CompletedProcess:
            # Model text only ever goes in as an option value (--title=...) or on stdin.
            cmd = ["gh", "issue", "create", f"--repo={self.config.github_repo}",
                   f"--title={title}", "--body-file=-"]
            cmd += [f"--label={label}" for label in with_labels]
            return subprocess.run(cmd, input=body, capture_output=True, text=True, timeout=30)

        try:
            result = create(safe_labels)
            if result.returncode == 0:
                return f"GitHub issue created: {result.stdout.strip()}"
            # A label that does not exist on the repo (e.g. "loeb" on a fresh repo) fails
            # the whole create; file it without labels rather than not at all.
            if "label" in result.stderr.lower():
                retry = create([])
                if retry.returncode == 0:
                    return f"GitHub issue created (no labels): {retry.stdout.strip()}"
                return f"Failed to create issue: {retry.stderr.strip()}"
            return f"Failed to create issue: {result.stderr.strip()}"
        except Exception as e:
            return f"Failed to create issue: {e}"

    async def send_slack(self, message: str) -> str:
        if not self.config.slack_bot_token:
            return "Slack not configured (SLACK_BOT_TOKEN not set). Skipped."
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.config.slack_bot_token}"},
                    json={"channel": self.config.slack_channel, "text": message},
                )
                data = resp.json()
                if data.get("ok"):
                    return f"Slack message sent to {self.config.slack_channel}."
                return f"Slack API error: {data.get('error', 'unknown')}"
        except Exception as e:
            return f"Failed to send Slack message: {e}"
