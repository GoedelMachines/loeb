"""`loeb check`: validate the setup and probe the running app, with no LLM call.

Every check yields one Result. The exit code follows from the failures:

    2  configuration is wrong: provider key, browser, profile, repos, a selector that
       does not match, a login that does not succeed
    1  configuration is fine but the app is not fully up (a health check or page fails)
    0  everything passed

`--json` prints one object (schema version 1, documented in docs/profile.md):

    {"schema": 1, "loeb_version": "0.1.0", "exit_code": 0, "ok": true,
     "results": [{"check": "selector", "name": "/ #new-todo", "status": "pass",
                  "detail": "1 match", "fix": null}, ...]}

status is "pass", "fail", "skip" or "warn"; only "fail" affects the exit code.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urljoin

SCHEMA_VERSION = 1
CONFIG, SERVICE = "config", "service"  # what a failure means for the exit code


@dataclass
class Result:
    check: str  # provider | browser | profile | repo | service | postgres | redis |
    #             page | selector | login | transcription
    name: str
    status: str  # pass | fail | skip | warn
    detail: str = ""
    fix: str | None = None
    severity: str = CONFIG

    def public(self) -> dict:
        d = asdict(self)
        d.pop("severity")
        return d


def loeb_version() -> str:
    try:
        return version("loeb")
    except PackageNotFoundError:
        return "unknown"


def exit_code(results: list[Result]) -> int:
    failed = [r for r in results if r.status == "fail"]
    if any(r.severity == CONFIG for r in failed):
        return 2
    return 1 if failed else 0


def page_url(website_url: str, page: str) -> str:
    if page.startswith(("http://", "https://")):
        return page
    return urljoin(website_url.rstrip("/") + "/", page.lstrip("/"))


async def live_checks(config, profile, timeout_ms: int = 5000) -> list[Result]:
    """Open the app in Chromium: every profile selector must match on its page, and
    the sign-in form must log the test user in when credentials are set."""
    from playwright.async_api import async_playwright

    results: list[Result] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            for path, selectors in profile.pages.items():
                results += await _check_page(page, page_url(config.website_url, path),
                                             path, selectors, timeout_ms)
            if profile.auth is not None:
                results += await _check_login(page, config, profile.auth, timeout_ms)
        finally:
            await browser.close()
    if profile.transcription.configured:
        results.append(Result(
            "transcription", "transcription selectors", "skip",
            "they appear only during a session; `loeb run` uses them", severity=CONFIG))
    return results


async def _goto(page, url: str, label: str, timeout_ms: int) -> Result | None:
    try:
        response = await page.goto(url, wait_until="load", timeout=timeout_ms * 3)
    except Exception as e:
        return Result("page", label, "fail", f"{url} did not load: {_first_line(e)}",
                      "start the web app (WEBSITE_URL)", SERVICE)
    if response is not None and response.status >= 400:
        return Result("page", label, "fail", f"{url} returned HTTP {response.status}",
                      "check the path in the profile's pages", CONFIG)
    return None


async def _check_page(page, url: str, label: str, selectors: list[str],
                      timeout_ms: int) -> list[Result]:
    problem = await _goto(page, url, label, timeout_ms)
    if problem:
        skipped = [Result("selector", f"{label} {s}", "skip", "page did not load")
                   for s in selectors]
        return [problem, *skipped]
    results = [Result("page", label, "pass", url)]
    for selector in selectors:
        results.append(await _check_selector(page, label, selector, timeout_ms))
    return results


async def _check_selector(page, label: str, selector: str, timeout_ms: int) -> Result:
    name = f"{label} {selector}"
    try:
        await page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
        count = await page.locator(selector).count()
    except Exception as e:
        message = _first_line(e)
        if "Timeout" in message:
            message = f"no element matches after {timeout_ms / 1000:g}s"
        return Result("selector", name, "fail", message,
                      "fix the selector in the profile (read the page's markup)")
    return Result("selector", name, "pass", f"{count} match" + ("" if count == 1 else "es"))


async def _check_login(page, config, auth, timeout_ms: int) -> list[Result]:
    url = page_url(config.website_url, auth.login_path)
    selectors = [auth.email_selector, auth.password_selector, auth.submit_selector]
    results = await _check_page(page, url, auth.login_path, selectors, timeout_ms)
    if any(r.status == "fail" for r in results):
        return results + [Result("login", "sign in", "skip", "the sign-in form is not usable")]
    if not (config.test_email and config.test_password):
        return results + [Result("login", "sign in", "skip",
                                 "set TEST_EMAIL and TEST_PASSWORD to check sign-in")]
    try:
        await page.fill(auth.email_selector, config.test_email, timeout=timeout_ms)
        await page.fill(auth.password_selector, config.test_password, timeout=timeout_ms)
        await page.click(auth.submit_selector, timeout=timeout_ms)
        await page.wait_for_url(auth.success_url_glob, timeout=timeout_ms * 3)
    except Exception as e:
        return results + [Result(
            "login", "sign in", "fail",
            f"did not reach {auth.success_url_glob}: {_first_line(e)} (now at {page.url})",
            "check TEST_EMAIL/TEST_PASSWORD, the auth selectors and success_url_glob")]
    return results + [Result("login", "sign in", "pass", f"signed in, now at {page.url}")]


def _first_line(e: Exception) -> str:
    text = str(e).strip()
    return text.splitlines()[0] if text else type(e).__name__


def _probe_postgres(config) -> str | None:
    import psycopg2

    try:
        psycopg2.connect(config.postgres_dsn, connect_timeout=3).close()
        return None
    except Exception as e:
        return str(e).strip().splitlines()[0]


def _probe_redis(config) -> str | None:
    import redis

    try:
        redis.Redis(host=config.redis_host, port=config.redis_port,
                    socket_connect_timeout=3, socket_timeout=3).ping()
        return None
    except Exception as e:
        return str(e)


def browser_problem() -> str | None:
    """None if Playwright's Chromium is installed, else what is wrong."""
    from pathlib import Path

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
    except Exception as e:
        return f"Playwright cannot start: {_first_line(e)}"
    if not Path(path).exists():
        return f"Chromium is not installed (expected {path})"
    return None


def run_checks(env_file: str | None, services: bool = True) -> tuple[list[Result], str]:
    """All checks, in order. Returns the results and the .env that was loaded."""
    from loeb.config import Config, load_env
    from loeb.llm import create_provider
    from loeb.profile import ProfileError, load_profile, profile_problems
    from loeb.tools.services import DEFAULT_CHECKS, ServiceManager

    results: list[Result] = []
    try:
        env = load_env(env_file)
        config = Config()
    except ValueError as e:
        return [Result("profile", "configuration", "fail", str(e))], ""
    env_label = str(env) if env else "none (environment only)"

    try:
        create_provider(config)
        results.append(Result("provider", config.provider, "pass"))
    except ValueError as e:
        results.append(Result("provider", config.provider, "fail", str(e),
                              "set the key in .env"))
    problem = browser_problem()
    results.append(Result("browser", "chromium", "fail" if problem else "pass",
                          problem or "", "run `loeb install`" if problem else None))
    try:
        profile = load_profile(config)
    except ProfileError as e:
        results.append(Result("profile", "profile", "fail", str(e), "edit the profile"))
        return results, env_label
    config.profile = profile
    results.append(Result("profile", "profile", "pass",
                          str(profile.source or "none (defaults; run `loeb init`)")))
    problems = profile_problems(profile)
    for problem in problems:
        results.append(Result("repo" if problem.startswith("repo ") else "profile",
                              problem.split(":")[0], "fail", problem))
    for name, path in profile.repos.items():
        if not any(p.startswith(f"repo '{name}'") for p in problems):
            results.append(Result("repo", name, "pass", path))
    if not profile.repos:
        results.append(Result("repo", "repos", "skip", "none configured; git_diff is off"))
    if exit_code(results) == 2 or not services:
        return results, env_label

    manager = ServiceManager(config)
    for check in profile.checks or DEFAULT_CHECKS:
        ok, detail = asyncio.run(manager.run_check(check))
        results.append(Result("service", check.name, "pass" if ok else "fail", detail,
                              None if ok else check.fix or None, SERVICE))
    for label, probe, configured, prefix in (
        ("postgres", _probe_postgres, config.postgres_configured, "POSTGRES_*"),
        ("redis", _probe_redis, config.redis_configured, "REDIS_*"),
    ):
        if not configured:
            results.append(Result(label, label, "skip",
                                  f"not configured (set {prefix} to enable its query tool)"))
            continue
        problem = probe(config)
        results.append(Result(label, label, "pass" if problem is None else "warn",
                              "reachable" if problem is None else
                              f"not reachable ({problem}); query tools will fail"))
    if profile.pages or profile.auth is not None or profile.transcription.configured:
        try:
            results += asyncio.run(live_checks(config, profile))
        except Exception as e:
            results.append(Result("browser", "live checks", "fail", _first_line(e),
                                  "run `loeb install`"))
    return results, env_label


SYMBOL = {"pass": "✓", "fail": "✗", "skip": "-", "warn": "!"}


def render_text(results: list[Result], env_label: str) -> str:
    lines = [f"  {'env':9} {env_label}"] if env_label else []
    for r in results:
        parts = [r.name] if r.name != r.check else []
        if r.detail:
            parts.append(f"({r.detail})" if r.status == "pass" and parts else r.detail)
        if r.fix and r.status == "fail":
            parts.append(f"→ {r.fix}")
        lines.append(f"{SYMBOL[r.status]} {r.check:9} " + "  ".join(parts))
    return "\n".join(lines)


def render_json(results: list[Result], env_label: str) -> str:
    code = exit_code(results)
    return json.dumps({
        "schema": SCHEMA_VERSION,
        "loeb_version": loeb_version(),
        "exit_code": code,
        "ok": code == 0,
        "env": env_label or None,
        "results": [r.public() for r in results],
    }, indent=2)
