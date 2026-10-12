"""`loeb` command line: init (scaffold a profile), check (validate it, no LLM), run.

    loeb guide           print the setup guide for a coding agent (matches this version)
    loeb schema          print the JSON Schema of loeb.json
    loeb install         download the Chromium build Playwright drives
    loeb init [DIR]      write loeb.json, loeb-target.md, .env and the setup skill into DIR
    loeb check           validate the setup and probe the running app; no LLM, no tokens
    loeb run [...]       the test run (same flags as before); `loeb [...]` means `loeb run`

check exits 0 when everything passes, 1 when the setup is valid but the app is not
fully up, 2 when the setup is wrong (see loeb/check.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from loeb.profile import DEFAULT_PROFILE_NAME

CONTEXT_NAME = "loeb-target.md"

CONTEXT_TEMPLATE = """\
<!-- Löb appends this file to its system prompt. Write what a new tester would need. -->

## How the app works
- What the app is for and who uses it
- The main pages and flows (e.g. sign in -> dashboard -> create an order)

## Key DOM selectors
- (buttons, inputs and status elements the agent should use)

## Data to verify
- Postgres tables / Redis key patterns that change when users act (if any)

## Key API endpoints
- GET /api/health
"""

ENV_TEMPLATE = """\
# Löb settings. Relative paths here resolve against this file's directory.
LOEB_PROFILE=loeb.json
ANTHROPIC_API_KEY=
# LLM_PROVIDER=openai
# OPENAI_API_KEY=
# OPENAI_BASE_URL=
# OPENAI_MODEL=gpt-4o

WEBSITE_URL={website_url}
API_BASE_URL={api_url}
# GITHUB_REPO=owner/name        # where bugs are filed (needs `gh auth login`)

# TEST_EMAIL=
# TEST_PASSWORD=
# POSTGRES_HOST=localhost       # for query_db
# REDIS_HOST=localhost          # for query_redis
"""


def _is_git_repo(path: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path, capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def detect_repos(directory: Path) -> dict[str, str]:
    """The directory itself if it is a git repo, else its git-repo subdirectories."""
    if _is_git_repo(directory):
        return {directory.resolve().name or "app": "."}
    return {
        child.name: child.name
        for child in sorted(directory.iterdir())
        if child.is_dir() and not child.name.startswith(".") and (child / ".git").exists()
    }


def scaffold_profile(repos: dict[str, str]) -> dict:
    return {
        "context": CONTEXT_NAME,
        "repos": repos,
        "api_health_path": "/api/health",
        "checks": [
            {"name": "API", "kind": "http", "probe": "api", "fix": "start the API server"},
            {"name": "Website", "kind": "http", "probe": "website", "fix": "start the web app"},
        ],
        "systemd_units": [],
        "docker_containers": {},
        "pages": {"/": []},
    }


def cmd_init(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"Error: {directory} is not a directory.", file=sys.stderr)
        return 2
    files = {
        directory / DEFAULT_PROFILE_NAME:
            json.dumps(scaffold_profile(detect_repos(directory)), indent=2) + "\n",
        directory / CONTEXT_NAME: CONTEXT_TEMPLATE,
        # .env is never overwritten, even with --force.
        directory / ".env": ENV_TEMPLATE.format(website_url=args.website_url,
                                                api_url=args.api_url),
    }
    from loeb.guide import SKILL_DIRS, SKILL_NAME, render_skill

    skill = render_skill()
    for agent in ["agents"] + (["claude"] if args.claude else []):
        files[directory / SKILL_DIRS[agent] / SKILL_NAME / "SKILL.md"] = skill
    for path, content in files.items():
        if path.exists() and path.read_text() == content:
            print(f"same     {path}")
            continue
        if path.exists() and (not args.force or path.name == ".env"):
            if path.name == ".env":  # never clobber an app's own .env
                print(f"kept     {path}  (exists; add these Löb settings to it:)\n")
                print("  " + content.replace("\n", "\n  ").rstrip())
            else:
                print(f"kept     {path}  (exists; --force to overwrite)")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"wrote    {path}")
    repos = json.loads((directory / DEFAULT_PROFILE_NAME).read_text()).get("repos", {})
    print(f"\nrepos:   {', '.join(repos) or 'none found — add them to loeb.json'}")
    print("next:    have your coding agent run `loeb guide` (or use the loeb-setup skill),"
          "\n         or edit loeb.json and loeb-target.md yourself; then `loeb check`")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    command = [sys.executable, "-m", "playwright", "install", "chromium"]
    if args.with_deps:
        command.append("--with-deps")  # also installs system libraries; may ask for sudo
    print("running  " + " ".join(command[1:]).replace("-m playwright", "playwright"))
    return 0 if subprocess.run(command).returncode == 0 else 2


def cmd_check(args: argparse.Namespace) -> int:
    from loeb.check import exit_code, render_json, render_text, run_checks

    results, env_label = run_checks(args.env_file, services=not args.no_services)
    print(render_json(results, env_label) if args.json else render_text(results, env_label))
    return exit_code(results)


def cmd_guide(args: argparse.Namespace) -> int:
    from loeb.guide import render_guide

    print(render_guide(), end="")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from loeb.guide import render_schema

    print(render_schema(), end="")
    return 0


EPILOG = "Have your coding agent run `loeb guide` to set Löb up for this project."
COMMANDS = ("guide", "schema", "install", "init", "check", "run")


def build_parser() -> argparse.ArgumentParser:
    from loeb.check import loeb_version

    parser = argparse.ArgumentParser(prog="loeb", description=__doc__.split("\n\n")[0],
                                     epilog=EPILOG)
    parser.add_argument("--version", action="version", version=f"loeb {loeb_version()}")
    sub = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}")

    sub.add_parser("guide", help="print the setup guide for a coding agent")
    sub.add_parser("schema", help="print the JSON Schema of loeb.json")

    install = sub.add_parser("install", help="download the Chromium build Playwright drives")
    install.add_argument("--with-deps", action="store_true",
                         help="also install the system libraries Chromium needs (Linux)")

    init = sub.add_parser("init", help="write loeb.json, loeb-target.md, .env and the skill")
    init.add_argument("dir", nargs="?", default=".", help="where to write (default: .)")
    init.add_argument("--website-url", default="http://localhost:3000")
    init.add_argument("--api-url", default="http://localhost:8000")
    init.add_argument("--force", action="store_true",
                      help="overwrite existing files (never .env)")
    init.add_argument("--claude", action="store_true",
                      help="also write the skill to .claude/skills/ for Claude Code")

    check = sub.add_parser("check", help="validate the profile and probe the stack (no LLM)")
    check.add_argument("--env-file", default=None)
    check.add_argument("--no-services", action="store_true",
                       help="skip everything that needs the app running: health checks,"
                            " databases, pages, selectors and sign-in")
    check.add_argument("--json", action="store_true",
                       help="print one JSON object (schema in docs/profile.md)")

    sub.add_parser("run", help="run the tester (see `loeb run --help`)", add_help=False)
    return parser


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in (*COMMANDS, "-h", "--help", "--version"):
        argv.insert(0, "run")  # `loeb "Test the cart"` == `loeb run "Test the cart"`
    if argv[0] == "run":
        from loeb.run import main as run_main

        asyncio.run(run_main(argv[1:], prog="loeb run"))
        return
    args = build_parser().parse_args(argv)
    commands = {"guide": cmd_guide, "schema": cmd_schema, "install": cmd_install,
                "init": cmd_init, "check": cmd_check}
    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
