import subprocess

import httpx

from autonomous_tester.config import Config


class Reporter:
    def __init__(self, config: Config):
        self.config = config

    def file_github_issue(self, title: str, body: str, labels: list[str]) -> str:
        if not self.config.github_repo:
            return "GITHUB_REPO not configured (owner/name). Issue not filed."
        safe_labels = ["löb"] + [lbl for lbl in labels if lbl != "löb"]
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            self.config.github_repo,
            "--title",
            title,
            "--body",
            body,
        ]
        for label in safe_labels:
            cmd.extend(["--label", label])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                url = result.stdout.strip()
                return f"GitHub issue created: {url}"
            # Retry without labels if label fails
            if "label" in result.stderr.lower():
                cmd_no_labels = cmd[:7] + [title, "--body", body]
                retry = subprocess.run(cmd_no_labels, capture_output=True, text=True, timeout=30)
                if retry.returncode == 0:
                    return f"GitHub issue created (no labels): {retry.stdout.strip()}"
            return f"Failed to create issue: {result.stderr}"
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
