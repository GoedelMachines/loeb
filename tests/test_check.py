"""`loeb check` live checks (real Chromium, local pages) and the --json output."""

from __future__ import annotations

import functools
import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from loeb import check
from loeb.check import Result, browser_problem, exit_code, page_url
from loeb.cli import main
from loeb.config import PATH_VARS

needs_chromium = pytest.mark.skipif(browser_problem() is not None,
                                    reason="Chromium not installed (`loeb install`)")

PAGES = {
    "/": b"<html><body><input id='new-todo'><ul class='todos'></ul></body></html>",
    "/sign-in": b"""<html><body><form action="/app" method="get">
        <input id="email"><input id="password" type="password">
        <button type="submit">Sign in</button></form></body></html>""",
    "/app": b"<html><body>signed in</body></html>",
}


class Pages(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path.split("?")[0])
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body or b"not found")

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    server = HTTPServer(("127.0.0.1", 0), Pages)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def app_dir(tmp_path, monkeypatch, site):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in (*PATH_VARS, "OPENAI_API_KEY", "LLM_PROVIDER", "TEST_EMAIL", "TEST_PASSWORD",
                "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
                "POSTGRES_PASSWORD", "REDIS_HOST", "REDIS_PORT"):
        os.environ.pop(var, None)
    os.environ.update(ANTHROPIC_API_KEY="sk-x", WEBSITE_URL=site)
    monkeypatch.setattr("loeb.config._CHECKOUT_ENV", tmp_path / "none.env")
    monkeypatch.setattr("loeb.check._probe_postgres", lambda c: None)
    monkeypatch.setattr("loeb.check._probe_redis", lambda c: None)
    # Short waits: a missing selector or a failed login costs timeout_ms (x3 for URLs).
    monkeypatch.setattr("loeb.check.live_checks",
                        functools.partial(check.live_checks, timeout_ms=1000))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_profile(app_dir, **fields):
    profile = {"checks": [{"name": "Website", "kind": "http", "probe": "website"}], **fields}
    (app_dir / "loeb.json").write_text(json.dumps(profile))


def check_json(capsys) -> tuple[int, dict]:
    with pytest.raises(SystemExit) as e:
        main(["check", "--json"])
    return e.value.code, json.loads(capsys.readouterr().out)


def statuses(report, check):
    return {r["name"]: r["status"] for r in report["results"] if r["check"] == check}


def test_exit_code_from_failures():
    assert exit_code([Result("page", "/", "pass")]) == 0
    assert exit_code([Result("page", "/", "fail", severity="service")]) == 1
    assert exit_code([Result("page", "/", "fail", severity="service"),
                      Result("selector", "/ #x", "fail")]) == 2
    assert exit_code([Result("redis", "redis", "warn")]) == 0


def test_page_url_joins_paths_and_keeps_urls():
    assert page_url("http://x:3000", "/sign-in") == "http://x:3000/sign-in"
    assert page_url("http://x:3000/", "/") == "http://x:3000/"
    assert page_url("http://x", "https://y/z") == "https://y/z"


@needs_chromium
def test_matching_selectors_pass_and_json_has_the_documented_shape(app_dir, capsys):
    write_profile(app_dir, pages={"/": ["#new-todo", "ul.todos"]})
    code, report = check_json(capsys)
    assert code == 0 and report["ok"] is True and report["exit_code"] == 0
    assert report["schema"] == 1 and "loeb_version" in report
    assert set(report["results"][0]) == {"check", "name", "status", "detail", "fix"}
    assert statuses(report, "selector") == {"/ #new-todo": "pass", "/ ul.todos": "pass"}


@needs_chromium
def test_selector_that_does_not_match_is_a_config_error(app_dir, capsys):
    write_profile(app_dir, pages={"/": ["#new-todo", "#missing"]})
    code, report = check_json(capsys)
    assert code == 2
    bad = next(r for r in report["results"] if r["name"] == "/ #missing")
    assert bad["status"] == "fail" and bad["fix"]
    assert "no element matches after 1s" in bad["detail"]


@needs_chromium
def test_page_that_404s_is_a_config_error(app_dir, capsys):
    write_profile(app_dir, pages={"/nope": ["#x"]})
    code, report = check_json(capsys)
    assert code == 2
    assert statuses(report, "page") == {"/nope": "fail"}


@needs_chromium
def test_app_down_is_exit_1_and_selectors_are_skipped(app_dir, capsys):
    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    os.environ["WEBSITE_URL"] = f"http://127.0.0.1:{port}"
    write_profile(app_dir, checks=[], pages={"/": ["#new-todo"]})
    code, report = check_json(capsys)
    assert code == 1
    assert statuses(report, "page") == {"/": "fail"}
    assert statuses(report, "selector") == {"/ #new-todo": "skip"}


AUTH = {"login_path": "/sign-in", "email_selector": "#email",
        "password_selector": "#password", "submit_selector": "button[type='submit']",
        "success_url_glob": "**/app**"}


@needs_chromium
def test_login_is_skipped_without_credentials(app_dir, capsys):
    write_profile(app_dir, auth=AUTH)
    code, report = check_json(capsys)
    assert code == 0
    assert statuses(report, "login") == {"sign in": "skip"}


@needs_chromium
def test_login_succeeds_with_credentials(app_dir, capsys):
    os.environ.update(TEST_EMAIL="t@example.com", TEST_PASSWORD="pw")
    write_profile(app_dir, auth=AUTH)
    code, report = check_json(capsys)
    assert code == 0, report
    assert statuses(report, "login") == {"sign in": "pass"}


@needs_chromium
def test_login_that_does_not_reach_success_url_fails(app_dir, capsys):
    os.environ.update(TEST_EMAIL="t@example.com", TEST_PASSWORD="pw")
    write_profile(app_dir, auth={**AUTH, "success_url_glob": "**/dashboard**"})
    code, report = check_json(capsys)
    assert code == 2
    assert statuses(report, "login") == {"sign in": "fail"}


def test_no_services_skips_live_checks(app_dir, capsys, monkeypatch):
    monkeypatch.setattr("loeb.check.browser_problem", lambda: None)
    monkeypatch.setattr("loeb.check.live_checks", lambda *a: pytest.fail("ran live checks"))
    write_profile(app_dir, pages={"/": ["#x"]})
    with pytest.raises(SystemExit) as e:
        main(["check", "--no-services", "--json"])
    assert e.value.code == 0
    assert json.loads(capsys.readouterr().out)["results"]


def test_pages_must_be_paths_or_urls():
    from loeb.profile import ProfileError, parse_profile

    with pytest.raises(ProfileError, match="must be a path starting with '/'"):
        parse_profile({"pages": {"sign-in": ["#x"]}})
    with pytest.raises(ProfileError, match="selectors must be non-empty"):
        parse_profile({"pages": {"/": [""]}})


def test_data_stores_are_skipped_unless_configured(app_dir, capsys, monkeypatch):
    probed = []
    monkeypatch.setattr("loeb.check._probe_postgres", lambda c: probed.append("pg"))
    monkeypatch.setattr("loeb.check._probe_redis", lambda c: probed.append("redis"))
    write_profile(app_dir)
    code, out = check_json(capsys)
    stores = {r["check"]: r["status"] for r in out["results"]
              if r["check"] in ("postgres", "redis")}
    assert code == 0 and stores == {"postgres": "skip", "redis": "skip"} and probed == []

    os.environ["REDIS_HOST"] = "127.0.0.1"
    code, out = check_json(capsys)
    stores = {r["check"]: r["status"] for r in out["results"]
              if r["check"] in ("postgres", "redis")}
    assert stores == {"postgres": "skip", "redis": "pass"} and probed == ["redis"]
