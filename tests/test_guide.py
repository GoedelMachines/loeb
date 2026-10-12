"""`loeb guide`, `loeb schema`, the bundled skill and its repo copies."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from loeb.cli import main
from loeb.config import PATH_VARS
from loeb.guide import (
    REPO_COPIES,
    SKILL_NAME,
    json_schema,
    pyproject_version,
    render_guide,
    render_skill,
)
from loeb.profile import parse_profile

ROOT = Path(__file__).resolve().parent.parent


def run_cli(*argv) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


@pytest.mark.parametrize("rel", sorted(REPO_COPIES))
def test_repo_copies_are_current(rel):
    """Edit loeb/guide.md or loeb/profile.py, then run `make generated`."""
    expected = REPO_COPIES[rel](pyproject_version(ROOT))
    assert (ROOT / rel).read_text() == expected, f"{rel} is stale: run `make generated`"


def test_guide_names_its_version_and_the_loop():
    text = render_guide("9.9.9")
    assert "(loeb 9.9.9)" in text and "{version}" not in text
    for step in ("loeb init", "loeb check --json", "loeb run", "loeb install", "loeb schema"):
        assert step in text


def test_skill_frontmatter_is_valid():
    text = render_skill("1.0")
    head, _, body = text.removeprefix("---\n").partition("\n---\n")
    fields = dict(line.split(": ", 1) for line in head.splitlines())
    assert fields["name"] == SKILL_NAME
    description = json.loads(fields["description"])  # quoted: it contains ": "
    assert "loeb check --json" in description
    assert body.strip() == render_guide("1.0").strip()


def test_schema_describes_the_profile():
    schema = json_schema()
    assert schema["additionalProperties"] is False
    for field in ("$schema", "app_kind", "repos", "checks", "pages", "auth", "transcription"):
        assert field in schema["properties"]
    assert schema["properties"]["app_kind"]["enum"] == ["web", "voice"]


def test_profile_may_point_at_its_schema():
    assert parse_profile({"$schema": "./schema/loeb.schema.json"}).app_kind == "web"


def test_example_profiles_validate():
    for path in ROOT.glob("examples/*/loeb.json"):
        parse_profile(json.loads(path.read_text()), source=path)


def test_guide_schema_and_version_commands(capsys):
    assert run_cli("guide") == 0
    assert capsys.readouterr().out.startswith("# Setting up Löb for this project (loeb ")
    assert run_cli("schema") == 0
    assert json.loads(capsys.readouterr().out)["title"].startswith("Löb target profile")
    assert run_cli("--version") == 0
    assert capsys.readouterr().out.startswith("loeb ")


def test_help_points_agents_at_the_guide(capsys):
    assert run_cli("--help") == 0
    assert "Have your coding agent run `loeb guide`" in capsys.readouterr().out


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in PATH_VARS:
        os.environ.pop(var, None)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_writes_the_skill_for_any_agent(app_dir):
    assert run_cli("init") == 0
    skill = app_dir / ".agents/skills/loeb-setup/SKILL.md"
    assert skill.read_text() == render_skill()
    assert not (app_dir / ".claude").exists()


def test_init_claude_also_writes_claude_skill(app_dir):
    assert run_cli("init", "--claude") == 0
    assert (app_dir / ".claude/skills/loeb-setup/SKILL.md").read_text() == render_skill()


def test_init_keeps_an_edited_skill_unless_forced(app_dir, capsys):
    skill = app_dir / ".agents/skills/loeb-setup/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("my edits")
    assert run_cli("init") == 0
    assert skill.read_text() == "my edits"
    assert "kept" in capsys.readouterr().out
    assert run_cli("init") == 0  # unchanged files are reported as such
    assert "same     loeb.json" in capsys.readouterr().out
    assert run_cli("init", "--force") == 0
    assert skill.read_text() == render_skill()
