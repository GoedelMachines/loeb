"""examples/todo: `loeb check` passes against it, and its planted bug is really there."""

from __future__ import annotations

import functools
import json
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

from loeb.check import browser_problem
from loeb.cli import main
from loeb.config import PATH_VARS

EXAMPLE = Path(__file__).resolve().parent.parent / "examples/todo"

pytestmark = pytest.mark.skipif(browser_problem() is not None,
                                reason="Chromium not installed (`loeb install`)")


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def todo_url():
    handler = functools.partial(Quiet, directory=str(EXAMPLE))
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_loeb_check_passes_against_the_example(todo_url, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in (*PATH_VARS, "LLM_PROVIDER", "TEST_EMAIL", "TEST_PASSWORD"):
        os.environ.pop(var, None)
    os.environ.update(ANTHROPIC_API_KEY="sk-x", WEBSITE_URL=todo_url)
    monkeypatch.setattr("loeb.config._CHECKOUT_ENV", tmp_path / "none.env")
    monkeypatch.setattr("loeb.check._probe_postgres", lambda c: None)
    monkeypatch.setattr("loeb.check._probe_redis", lambda c: None)
    monkeypatch.chdir(EXAMPLE)
    with pytest.raises(SystemExit) as e:
        main(["check", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert e.value.code == 0, report
    selectors = [r for r in report["results"] if r["check"] == "selector"]
    assert len(selectors) == 4 and all(r["status"] == "pass" for r in selectors)


def test_the_planted_bug_deletes_the_wrong_item(todo_url):
    """Deleting the newest of two items removes the oldest. Keep it: it's the demo."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(todo_url)
        for text in ("first", "second"):
            page.fill("#new-todo", text)
            page.click("#add")
        assert page.locator(".todo-text").all_inner_texts() == ["second", "first"]
        page.click("button[aria-label='Delete second']")
        remaining = page.locator(".todo-text").all_inner_texts()
        browser.close()
    assert remaining == ["second"]  # correct behaviour would leave ["first"]
