"""Attach to an externally managed target stack instead of spinning a private one.

Löb does not start or stop the app under test. `start_services` *verifies* the
stack — runs every health check in the target profile (see loeb/profile.py
and docs/profile.md) and reports what is down and how to start it — and
`stop_services` refuses, because the stack is shared.

Check kinds: "http" (GET; any HTTP answer counts as alive), "tcp" (connect to
[host, port]), "unit" (`systemctl --user is-active <name>`).
"""

import asyncio
import shutil
import subprocess

import httpx

from loeb.config import Config
from loeb.profile import Check, profile_of

# Used when the profile lists no checks: just the API and the website.
DEFAULT_CHECKS = [
    Check(name="API", kind="http", probe="api", fix="start the API server"),
    Check(name="Website", kind="http", probe="website", fix="start the web app"),
]


def http_probe_url(config: Config, check: Check) -> str:
    """The URL an http check probes; "api"/"website"/null resolve against the config."""
    probe = check.probe
    if probe is None:  # legacy rule
        probe = "api" if check.name.startswith("API") else "website"
    if probe == "api":
        return f"{config.api_base_url}{profile_of(config).api_health_path}"
    if probe == "website":
        return config.website_url
    return probe


class ServiceManager:
    def __init__(self, config: Config):
        self.config = config

    async def start_all(self) -> str:
        """Verify the externally-managed stack; never start or rebuild it."""
        checks = profile_of(self.config).checks or DEFAULT_CHECKS
        lines = []
        all_up = True
        for check in checks:
            ok, detail = await self.run_check(check)
            line = f"{'✓' if ok else '✗'} {check.name}"
            if not ok:
                line += f"  ({detail})" if detail else ""
                line += f"  → {check.fix}" if check.fix else ""
            lines.append(line)
            all_up = all_up and ok
        header = (
            "All services up (externally managed; nothing was started by Löb)."
            if all_up
            else "Some services are DOWN. Löb does not manage this stack — report the ✗ lines "
            "with their start commands rather than trying to start anything yourself."
        )
        return header + "\n" + "\n".join(lines)

    async def run_check(self, check: Check) -> tuple[bool, str]:
        """(ok, what was probed) for one validated check."""
        if check.kind == "http":
            url = http_probe_url(self.config, check)
            return await self._check_http(url), url
        if check.kind == "tcp":
            host, port = check.probe
            return await self._check_tcp(host, port), f"{host}:{port}"
        if shutil.which("systemctl") is None:
            return False, "systemctl not available on this machine"
        return self._check_unit(check.probe), f"unit {check.probe}"

    async def _check_http(self, url: str) -> bool:
        # Any HTTP answer counts as alive: several services 404 bare GETs.
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(url)
                return True
        except Exception:
            return False

    async def _check_tcp(self, host: str, port: int) -> bool:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
            writer.close()
            return True
        except Exception:
            return False

    def _check_unit(self, unit: str) -> bool:
        try:
            out = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return out.stdout.strip() == "active"
        except Exception:
            return False

    def stop_all(self) -> str:
        return (
            "Refusing: the target stack is shared and externally managed. "
            "Löb must not stop it. If a test truly needs a restart of one service, "
            "report which one and why instead."
        )
