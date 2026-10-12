"""The setup guide for coding agents, the skill that carries it, and the profile schema.

One source, loeb/guide.md, rendered three ways: `loeb guide` prints it, `loeb init`
writes it as an Agent Skill (SKILL.md), and the repo keeps a copy under skills/ for
`npx skills add`. tests/test_guide.py fails if that copy drifts.
"""

from __future__ import annotations

import json
from importlib.resources import files

from loeb.check import loeb_version

SKILL_NAME = "loeb-setup"
SKILL_DESCRIPTION = (
    "Set up Löb, the end-to-end tester, for this project: write loeb.json and"
    " loeb-target.md from the codebase, then loop on `loeb check --json` until it passes."
    " Use when asked to set up, configure or run Löb (the `loeb` command)."
)
# Where `loeb init` writes the skill: the cross-agent location, and Claude Code's.
SKILL_DIRS = {"agents": ".agents/skills", "claude": ".claude/skills"}


def render_guide(version: str | None = None) -> str:
    text = files("loeb").joinpath("guide.md").read_text(encoding="utf-8")
    return text.replace("{version}", version or loeb_version())


def render_skill(version: str | None = None) -> str:
    return (
        # A JSON string is a valid YAML double-quoted scalar; the description has ": ".
        f"---\nname: {SKILL_NAME}\n"
        f"description: {json.dumps(SKILL_DESCRIPTION, ensure_ascii=False)}\n---\n\n"
        + render_guide(version)
    )


def json_schema() -> dict:
    from loeb.profile import Profile

    schema = Profile.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Löb target profile (loeb.json)"
    return schema


def render_schema() -> str:
    return json.dumps(json_schema(), indent=2, ensure_ascii=False) + "\n"


# Copies kept in the repo, regenerated with `make generated` after editing guide.md or
# the profile model: {path relative to the repo root: renderer}.
REPO_COPIES = {
    f"skills/{SKILL_NAME}/SKILL.md": render_skill,
    "schema/loeb.schema.json": lambda version=None: render_schema(),
}


def pyproject_version(root) -> str:
    import re
    from pathlib import Path

    text = (Path(root) / "pyproject.toml").read_text()
    return re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)


if __name__ == "__main__":  # python -m loeb.guide: rewrite the repo copies
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    version = pyproject_version(root)
    for rel, render in REPO_COPIES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(version))
        print(f"wrote {rel}")
