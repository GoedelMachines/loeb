"""`loeb` CLI: init -> check round trip, check exit codes, run routing."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import AsyncMock, patch

import pytest

from loeb.cli import main
from loeb.config import PATH_VARS


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    """An app checkout (a git repo) as cwd, with an isolated environment."""
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in (*PATH_VARS, "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER",
                "WEBSITE_URL", "API_BASE_URL"):
        os.environ.pop(var, None)
    monkeypatch.setattr("loeb.config._CHECKOUT_ENV", tmp_path / "none.env")
    app = tmp_path / "shop"
    app.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=app, check=True)
    monkeypatch.chdir(app)
    monkeypatch.setattr("loeb.check._probe_postgres", lambda c: None)
    monkeypatch.setattr("loeb.check._probe_redis", lambda c: None)
    monkeypatch.setattr("loeb.check.browser_problem", lambda: None)
    return app


def run_cli(*argv) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


@pytest.fixture
def http_server():
    class Ok(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Ok)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_init_writes_a_profile_that_validates(app_dir, capsys):
    assert run_cli("init") == 0
    profile = json.loads((app_dir / "loeb.json").read_text())
    assert profile["repos"] == {"shop": "."}
    assert (app_dir / "loeb-target.md").exists()
    assert "ANTHROPIC_API_KEY=" in (app_dir / ".env").read_text()

    # Without a key, check reports the provider problem: exit 2.
    assert run_cli("check", "--no-services") == 2
    assert "ANTHROPIC_API_KEY required" in capsys.readouterr().out

    # With a key in the generated .env, the round trip passes.
    env = (app_dir / ".env").read_text().replace("ANTHROPIC_API_KEY=", "ANTHROPIC_API_KEY=sk-x")
    (app_dir / ".env").write_text(env)
    os.environ.pop("ANTHROPIC_API_KEY")  # the first check loaded the empty value
    assert run_cli("check", "--no-services") == 0
    out = capsys.readouterr().out
    assert "✓ profile   " in out and "✓ repo      shop  (" in out


def test_init_never_overwrites_existing_env_and_needs_force_for_profile(app_dir, capsys):
    (app_dir / ".env").write_text("APP_SECRET=keep-me\n")
    (app_dir / "loeb.json").write_text("{}")
    assert run_cli("init", "--force") == 0
    assert (app_dir / ".env").read_text() == "APP_SECRET=keep-me\n"
    assert "ANTHROPIC_API_KEY=" in capsys.readouterr().out  # printed for the user to add
    assert json.loads((app_dir / "loeb.json").read_text())["repos"]


def test_init_detects_repo_subdirectories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("api", "web"):
        (tmp_path / name).mkdir()
        subprocess.run(["git", "init", "-q"], cwd=tmp_path / name, check=True)
    (tmp_path / "notes").mkdir()
    assert run_cli("init") == 0
    assert json.loads((tmp_path / "loeb.json").read_text())["repos"] == {"api": "api",
                                                                        "web": "web"}


def test_check_invalid_profile_exits_2_with_field_error(app_dir, capsys):
    os.environ["ANTHROPIC_API_KEY"] = "sk-x"
    (app_dir / "loeb.json").write_text(json.dumps(
        {"checks": [{"name": "DB", "kind": "tcp", "probe": "localhost"}]}))
    assert run_cli("check") == 2
    assert "checks[0]: tcp probe must be" in capsys.readouterr().out


def test_check_missing_repo_exits_2(app_dir, capsys):
    os.environ["ANTHROPIC_API_KEY"] = "sk-x"
    (app_dir / "loeb.json").write_text(json.dumps({"repos": {"api": "../nope"}}))
    assert run_cli("check") == 2
    assert "repo 'api'" in capsys.readouterr().out


def test_check_service_down_exits_1_and_up_exits_0(app_dir, http_server, capsys):
    os.environ["ANTHROPIC_API_KEY"] = "sk-x"
    profile = {"checks": [{"name": "Web", "kind": "http", "probe": http_server}]}
    (app_dir / "loeb.json").write_text(json.dumps(profile))
    assert run_cli("check") == 0
    profile["checks"].append({"name": "DB", "kind": "tcp", "probe": "127.0.0.1:1",
                              "fix": "start postgres"})
    (app_dir / "loeb.json").write_text(json.dumps(profile))
    assert run_cli("check") == 1
    assert "✗ service   DB  127.0.0.1:1  → start postgres" in capsys.readouterr().out


def test_bare_prompt_routes_to_run():
    with patch("loeb.run.main", new=AsyncMock()) as run_main:
        main(["Test the cart", "--ci"])
    run_main.assert_awaited_once_with(["Test the cart", "--ci"], prog="loeb run")


def test_run_subcommand_passes_flags_through():
    with patch("loeb.run.main", new=AsyncMock()) as run_main:
        main(["run", "--dry-run"])
    run_main.assert_awaited_once_with(["--dry-run"], prog="loeb run")


def test_loeb_console_script_is_declared():
    from pathlib import Path

    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    assert '[tool.poetry.scripts]\nloeb = "loeb.cli:main"' in pyproject


def test_check_missing_browser_exits_2_and_names_the_fix(app_dir, monkeypatch, capsys):
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    monkeypatch.setattr("loeb.check.browser_problem", lambda: "Chromium is not installed")
    assert run_cli("check", "--no-services") == 2
    out = capsys.readouterr().out
    assert "✗ browser   chromium  Chromium is not installed  → run `loeb install`" in out


def test_browser_problem_reports_a_missing_executable(monkeypatch, tmp_path):
    from loeb import check as cli

    class FakeChromium:
        executable_path = str(tmp_path / "no-chrome")

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    assert "Chromium is not installed" in cli.browser_problem()
    (tmp_path / "no-chrome").write_text("")
    assert cli.browser_problem() is None


@pytest.mark.parametrize("flags,extra", [([], []), (["--with-deps"], ["--with-deps"])])
def test_install_runs_playwright_install_chromium(flags, extra):
    import sys

    with patch("loeb.cli.subprocess.run") as run:
        run.return_value.returncode = 0
        assert run_cli("install", *flags) == 0
    assert run.call_args.args[0] == [sys.executable, "-m", "playwright", "install",
                                     "chromium", *extra]


def test_install_failure_exits_2():
    with patch("loeb.cli.subprocess.run") as run:
        run.return_value.returncode = 1
        assert run_cli("install") == 2
