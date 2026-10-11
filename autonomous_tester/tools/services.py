"""Attach to an externally managed target stack instead of spinning a private one.

Löb does not start or stop the app under test. `start_services` *verifies* the
stack — runs every health check listed in the target services file
(TARGET_SERVICES, JSON; see examples/) and reports what is down and how to
start it — and `stop_services` refuses, because the stack is shared.

Check kinds: "http" (GET; any HTTP answer counts as alive), "tcp" (connect to
[host, port]), "unit" (`systemctl --user is-active <name>`). An "http" check
with probe null uses the configured API health URL or website URL.
"""

import asyncio
import json
import subprocess
from pathlib import Path

import httpx

from autonomous_tester.config import Config

# Used when no TARGET_SERVICES file is configured: just the API and the website.
DEFAULT_CHECKS = [
    ("API", "http", None, "start the API server"),
    ("Website", "http", None, "start the web app"),
]


def load_target_services(config: Config) -> dict:
    """Read the target services JSON file, or return {} if none is configured."""
    path = getattr(config, "target_services", "")
    if not isinstance(path, str) or not path:
        return {}
    return json.loads(Path(path).expanduser().read_text())


def load_checks(config: Config) -> list[tuple]:
    data = load_target_services(config)
    checks = data.get("checks")
    if not checks:
        return DEFAULT_CHECKS
    return [
        (
            c["name"],
            c["kind"],
            tuple(c["probe"]) if isinstance(c.get("probe"), list) else c.get("probe"),
            c.get("fix", ""),
        )
        for c in checks
    ]


class ServiceManager:
    def __init__(self, config: Config):
        self.config = config

    async def start_all(self) -> str:
        """Verify the externally-managed stack; never start or rebuild it."""
        try:
            checks = load_checks(self.config)
        except Exception as e:
            return f"Could not read TARGET_SERVICES file: {e}"
        lines = []
        all_up = True
        for name, kind, probe, fix in checks:
            if kind == "http":
                url = probe
                if url is None:  # config-driven URLs
                    url = (
                        f"{self.config.api_base_url}/api/health"
                        if name.startswith("API")
                        else self.config.website_url
                    )
                ok = await self._check_http(url)
            elif kind == "tcp":
                ok = await self._check_tcp(*probe)
            else:
                ok = self._check_unit(probe)
            lines.append(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"  → {fix}"))
            all_up = all_up and ok
        header = (
            "All services up (externally managed; nothing was started by Löb)."
            if all_up
            else "Some services are DOWN. Löb does not manage this stack — report the ✗ lines "
            "with their start commands rather than trying to start anything yourself."
        )
        return header + "\n" + "\n".join(lines)

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
