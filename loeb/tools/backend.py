import json
import subprocess

import httpx
import psycopg2
import redis

from loeb.config import Config
from loeb.profile import profile_of


class BackendTools:
    def __init__(self, config: Config):
        self.config = config

    async def check_api(self, method: str, path: str, body: str = "") -> str:
        url = f"{self.config.api_base_url}{path}"
        try:
            kwargs: dict = {"method": method, "url": url, "timeout": 15}
            if body:
                kwargs["json"] = json.loads(body)
            async with httpx.AsyncClient() as client:
                resp = await client.request(**kwargs)
                return (
                    f"HTTP {resp.status_code}\n"
                    f"Headers: {dict(resp.headers)}\n"
                    f"Body: {resp.text[:2000]}"
                )
        except Exception as e:
            return f"API request failed: {e}"

    async def query_db(self, sql: str) -> str:
        try:
            conn = psycopg2.connect(self.config.postgres_dsn)
            conn.set_session(readonly=True, autocommit=True)
            cur = conn.cursor()
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
            cur.close()
            conn.close()
            if not rows:
                return f"Query returned 0 rows.\nColumns: {columns}"
            lines = [" | ".join(columns)]
            lines.append("-" * len(lines[0]))
            for row in rows[:50]:
                lines.append(" | ".join(str(v) for v in row))
            return "\n".join(lines)
        except Exception as e:
            return f"Database query failed: {e}"

    async def query_redis(self, pattern: str) -> str:
        try:
            r = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                decode_responses=True,
            )
            keys = list(r.scan_iter(match=pattern, count=100))[:20]
            if not keys:
                return f"No Redis keys matching '{pattern}'."
            results = []
            for key in keys:
                key_type = r.type(key)
                if key_type == "string":
                    val = r.get(key)
                elif key_type == "hash":
                    val = json.dumps(r.hgetall(key))
                elif key_type == "list":
                    val = json.dumps(r.lrange(key, 0, 10))
                elif key_type == "set":
                    val = json.dumps(list(r.smembers(key)))
                else:
                    val = f"<{key_type}>"
                results.append(f"{key} ({key_type}): {val}")
            r.close()
            return "\n".join(results)
        except Exception as e:
            return f"Redis query failed: {e}"

    # Log sources come from the target profile:
    #   "systemd_units": names read via `journalctl --user -u <unit>`
    #   "docker_containers": {alias: container} read via `docker logs <container>`
    # Anything else falls through to `docker compose logs` in the first repo.
    async def read_logs(self, service: str, lines: int = 50) -> str:
        try:
            profile = profile_of(self.config)
            units = set(profile.systemd_units)
            containers = dict(profile.docker_containers)
            if service in units:
                cmd = ["journalctl", "--user", "-u", service, "-n", str(int(lines)), "--no-pager"]
                cwd = None
            elif service in containers:
                cmd = ["docker", "logs", "--tail", str(int(lines)), containers[service]]
                cwd = None
            elif service.startswith("-"):
                return f"Error: invalid service name '{service}'."
            else:
                cmd = ["docker", "compose", "logs", "--tail", str(int(lines)), "--", service]
                repos = list(profile_of(self.config).repos.values())
                cwd = repos[0] if repos else None
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15)
            output = result.stdout or result.stderr
            return output[:5000] if output else f"No logs for service '{service}'."
        except Exception as e:
            return f"Failed to read logs: {e}"
