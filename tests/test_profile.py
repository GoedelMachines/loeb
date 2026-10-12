"""Target profile: schema validation, legacy compatibility, path resolution, wiring."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from loeb.profile import (
    Profile,
    ProfileError,
    load_profile,
    parse_profile,
    profile_problems,
)

EXAMPLE = Path(__file__).parent.parent / "examples/todo/loeb.json"


def make_config(**kw):
    config = MagicMock()
    config.target_profile = ""
    config.target_services = ""
    config.target_context = ""
    config.backend_dir = ""
    config.frontend_dir = ""
    config.profile = None
    config.api_base_url = "http://api.test"
    config.website_url = "http://web.test"
    for k, v in kw.items():
        setattr(config, k, v)
    return config


def write(tmp_path, data, name="loeb.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return p


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


# --- schema ------------------------------------------------------------------


def test_example_profile_is_valid():
    profile = parse_profile(json.loads(EXAMPLE.read_text()), EXAMPLE)
    assert profile.app_kind == "web" and profile.auth is None
    assert profile.pages == {"/": ["#new-todo", "#add", "#todo-list", "#count"]}


def test_empty_profile_is_valid():
    assert parse_profile({}) == Profile()


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"check": []}, "check: unknown field (typo?)"),
        ({"checks": [{"name": "X", "kind": "https", "probe": None}]}, "checks[0].kind"),
        ({"checks": [{"kind": "http"}]}, "checks[0].name: Field required"),
        ({"checks": [{"name": "DB", "kind": "tcp", "probe": "localhost"}]},
         "checks[0]: tcp probe must be [host, port] or 'host:port'"),
        ({"checks": [{"name": "DB", "kind": "tcp", "probe": ["h", "5432"]}]},
         "tcp probe must be"),
        ({"checks": [{"name": "W", "kind": "http", "probe": "localhost:3000"}]},
         "http probe must be a http(s) URL"),
        ({"checks": [{"name": "U", "kind": "unit"}]}, "unit probe must be"),
        ({"api_health_path": "healthz"}, "api_health_path must start with '/'"),
        ({"auth": {"login_url": "/login"}}, "auth.login_url: unknown field"),
        ({"repos": {"api": ""}}, "repo names and paths must be non-empty"),
    ],
)
def test_invalid_profiles_name_the_field(data, expected):
    with pytest.raises(ProfileError) as e:
        parse_profile(data, Path("loeb.json"))
    assert expected in str(e.value)
    assert str(e.value).startswith("loeb.json is invalid")


def test_tcp_probe_accepts_host_port_string():
    profile = parse_profile({"checks": [{"name": "DB", "kind": "tcp", "probe": "db:5432"}]})
    assert profile.checks[0].probe == ["db", 5432]


def test_source_cannot_be_set_from_json():
    with pytest.raises(ProfileError, match="unknown field"):
        parse_profile({"source": "/etc"})


# --- loading -----------------------------------------------------------------


def test_loeb_json_in_cwd_is_found_by_default(tmp_path):
    write(tmp_path, {"api_health_path": "/healthz"})
    assert load_profile(make_config()).api_health_path == "/healthz"


def test_no_profile_anywhere_gives_empty_profile():
    assert load_profile(make_config()) == Profile()


def test_missing_profile_file_is_a_clear_error(tmp_path):
    with pytest.raises(ProfileError, match="cannot read target profile .*nope.json"):
        load_profile(make_config(target_profile=str(tmp_path / "nope.json")))


def test_bad_json_is_a_clear_error(tmp_path):
    p = write(tmp_path, '{"checks": [', name="bad.json")
    with pytest.raises(ProfileError, match="bad.json is not valid JSON"):
        load_profile(make_config(target_profile=str(p)))


def test_relative_paths_resolve_against_profile_dir(tmp_path, monkeypatch):
    prof_dir = tmp_path / "app" / ".loeb"
    prof_dir.mkdir(parents=True)
    (prof_dir / "target.md").write_text("ctx")
    p = write(prof_dir, {"context": "target.md", "repos": {"app": ".."}})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    profile = load_profile(make_config(target_profile=str(p)))
    assert profile.repos == {"app": str(tmp_path / "app")}
    assert profile.context == str(prof_dir / "target.md")


def test_legacy_services_file_with_env_repos(tmp_path):
    """An old TARGET_SERVICES file (checks + log sources, no repos) keeps working."""
    legacy = write(tmp_path, {
        "checks": [{"name": "API", "kind": "http", "probe": None, "fix": "start it"}],
        "systemd_units": ["app-worker"],
        "docker_containers": {"redis": "app-redis-1"},
    }, name="services.json")
    profile = load_profile(make_config(
        target_services=str(legacy), backend_dir=str(tmp_path / "b"), frontend_dir="",
    ))
    assert profile.repos == {"backend": str(tmp_path / "b")}
    assert profile.systemd_units == ["app-worker"]
    assert profile.checks[0].probe is None


def test_target_profile_wins_over_target_services(tmp_path):
    a = write(tmp_path, {"api_health_path": "/a"}, name="a.json")
    b = write(tmp_path, {"api_health_path": "/b"}, name="b.json")
    profile = load_profile(make_config(target_profile=str(a), target_services=str(b)))
    assert profile.api_health_path == "/a"


def test_target_context_env_overrides_profile_context(tmp_path):
    (tmp_path / "env.md").write_text("from env")
    p = write(tmp_path, {"context": "profile.md"})
    profile = load_profile(make_config(target_profile=str(p), target_context="env.md"))
    assert profile.context == str(tmp_path / "env.md")


def test_profile_problems_reports_missing_context_and_non_git_repo(tmp_path):
    (tmp_path / "plain").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    p = write(tmp_path, {"context": "missing.md",
                         "repos": {"plain": "plain", "repo": "repo", "gone": "gone"}})
    problems = profile_problems(load_profile(make_config(target_profile=str(p))))
    assert any("missing.md does not exist" in x for x in problems)
    assert any(x.startswith("repo 'plain'") and "not a git repository" in x for x in problems)
    assert any(x.startswith("repo 'gone'") and "does not exist" in x for x in problems)
    assert not any(x.startswith("repo 'repo'") for x in problems)


# --- wiring ------------------------------------------------------------------


def test_tool_definitions_follow_profile_repos():
    from loeb.tool_registry import TOOL_DEFINITIONS, tool_definitions

    tools = {t["name"]: t for t in tool_definitions(Profile(repos={"api": "/a", "web": "/w"}))}
    enum = tools["git_diff"]["input_schema"]["properties"]["repo"]["enum"]
    assert enum == ["api", "web"]
    assert "read_transcription" not in tools
    # the module-level definitions are not mutated
    base = next(t for t in TOOL_DEFINITIONS if t["name"] == "git_diff")
    assert base["input_schema"]["properties"]["repo"]["enum"] == []


def test_tool_definitions_without_repos_drop_git_diff_and_keep_transcription_if_set():
    from loeb.tool_registry import tool_definitions

    profile = parse_profile({"app_kind": "voice", "transcription": {"agent_selector": ".bot"}})
    names = {t["name"] for t in tool_definitions(profile)}
    assert "git_diff" not in names and "read_transcription" in names


def test_web_apps_get_no_audio_tools_or_voice_prompt():
    from loeb.agent import VOICE_PROMPT, build_system_prompt
    from loeb.tool_registry import VOICE_TOOLS, tool_definitions

    web, voice = parse_profile({}), parse_profile({"app_kind": "voice"})
    assert web.app_kind == "web"
    assert not VOICE_TOOLS & {t["name"] for t in tool_definitions(web)}
    voice_names = {t["name"] for t in tool_definitions(voice)}
    assert {"inject_audio", "inject_silence"} <= voice_names
    assert "read_transcription" not in voice_names  # no selectors configured
    assert VOICE_PROMPT not in build_system_prompt(make_config(profile=web))
    assert VOICE_PROMPT in build_system_prompt(make_config(profile=voice))


def test_transcription_without_voice_is_rejected():
    with pytest.raises(ProfileError, match='need "app_kind": "voice"'):
        parse_profile({"transcription": {"agent_selector": ".bot"}})
    with pytest.raises(ProfileError, match="app_kind"):
        parse_profile({"app_kind": "chat"})


@pytest.mark.asyncio
async def test_git_diff_dispatch_uses_repos_map(tmp_path):
    from loeb.tool_registry import ToolRegistry

    config = make_config(profile=Profile(repos={"api": str(tmp_path)}))
    reg = ToolRegistry(services=MagicMock(), browser=MagicMock(), audio=MagicMock(),
                       backend=MagicMock(), reporter=MagicMock(), config=config)
    assert "not a git repository" in await reg.dispatch("git_diff", {"repo": "api"})
    assert (await reg.dispatch("git_diff", {"repo": "frontend"})).startswith(
        "Error: unknown repo 'frontend'. Configured repos: api."
    )


def test_system_prompt_lists_repos_log_sources_and_context(tmp_path):
    from loeb.agent import build_system_prompt

    (tmp_path / "t.md").write_text("The app has a checkout page.")
    profile = parse_profile({"systemd_units": ["app-worker"],
                             "docker_containers": {"db": "pg"}})
    profile.repos = {"shop": "/x"}
    profile.context = str(tmp_path / "t.md")
    prompt = build_system_prompt(make_config(profile=profile))
    assert "git_diff repo=...): shop" in prompt
    assert "Log sources for read_logs: app-worker, db" in prompt
    assert "checkout page" in prompt


@pytest.mark.asyncio
async def test_start_all_uses_explicit_probes_and_health_path():
    from loeb.tools.services import ServiceManager

    profile = parse_profile({
        "api_health_path": "/healthz",
        "checks": [
            {"name": "Backend", "kind": "http", "probe": "api"},
            {"name": "Front", "kind": "http", "probe": "website"},
            {"name": "DB", "kind": "tcp", "probe": "127.0.0.1:1"},
        ],
    })
    sm = ServiceManager(make_config(profile=profile))
    sm._check_http = AsyncMock(return_value=True)
    sm._check_tcp = AsyncMock(return_value=False)
    out = await sm.start_all()
    urls = [c.args[0] for c in sm._check_http.call_args_list]
    assert urls == ["http://api.test/healthz", "http://web.test"]
    assert "✗ DB  (127.0.0.1:1)" in out


@pytest.mark.asyncio
async def test_legacy_null_probe_rule_still_applies():
    from loeb.tools.services import ServiceManager

    profile = parse_profile({"checks": [{"name": "API x", "kind": "http", "probe": None},
                                        {"name": "Site", "kind": "http", "probe": None}]})
    sm = ServiceManager(make_config(profile=profile))
    sm._check_http = AsyncMock(return_value=True)
    await sm.start_all()
    urls = [c.args[0] for c in sm._check_http.call_args_list]
    assert urls == ["http://api.test/api/health", "http://web.test"]


@pytest.mark.asyncio
async def test_browser_login_uses_profile_auth():
    from loeb.tools.browser import BrowserTools

    profile = parse_profile({"auth": {"login_path": "/login", "email_selector": "#user",
                                      "password_selector": "#pw", "submit_selector": "#go",
                                      "success_url_glob": "**/dashboard"}})
    config = make_config(profile=profile, test_email="t@e.st", test_password="pw",
                         supabase_url="", supabase_anon_key="")
    bt = BrowserTools(config)
    bt.page = MagicMock()
    for m in ("goto", "fill", "click", "wait_for_url"):
        setattr(bt.page, m, AsyncMock())
    result = await bt.login()  # no Supabase -> browser by default
    assert result.startswith("Logged in")
    assert bt.page.goto.call_args.args[0] == "http://web.test/login"
    assert [c.args[0] for c in bt.page.fill.call_args_list] == ["#user", "#pw"]
    bt.page.click.assert_awaited_once_with("#go", timeout=5000)
    assert bt.page.wait_for_url.call_args.args[0] == "**/dashboard"


@pytest.mark.asyncio
async def test_login_without_credentials_is_an_error():
    from loeb.llm.base import is_tool_error
    from loeb.tools.browser import BrowserTools

    bt = BrowserTools(make_config(profile=Profile(), test_email="", test_password=""))
    bt.page = MagicMock()
    assert is_tool_error(await bt.login())


@pytest.mark.asyncio
async def test_read_transcription_unconfigured_is_an_error():
    from loeb.tools.browser import BrowserTools

    bt = BrowserTools(make_config(profile=Profile()))
    bt.page = MagicMock()
    assert (await bt.read_transcription()).startswith("Error: no transcription selectors")


def test_query_tools_follow_configured_data_stores():
    from loeb.profile import Profile
    from loeb.tool_registry import tool_definitions

    def names(**kw):
        return {t["name"] for t in tool_definitions(Profile(), **kw)}

    assert {"query_db", "query_redis"} <= names()
    assert not {"query_db", "query_redis"} & names(postgres=False, redis=False)
    assert "query_db" in names(postgres=True, redis=False) - names(postgres=False, redis=False)


def test_extra_origins_must_be_http_origins():
    import pytest as _pytest
    from pydantic import ValidationError

    from loeb.profile import Profile

    assert Profile(extra_origins=["https://accounts.google.com"]).extra_origins
    for bad in (["accounts.google.com"], ["file:///etc"], ["https://"]):
        with _pytest.raises(ValidationError):
            Profile(extra_origins=bad)


def test_system_prompt_names_the_app_url(tmp_path, monkeypatch):
    from loeb.agent import build_system_prompt
    from loeb.profile import Profile

    config = type("C", (), {"website_url": "http://127.0.0.1:8765",
                            "api_base_url": "http://127.0.0.1:9000"})()
    monkeypatch.setattr("loeb.profile.profile_of", lambda c: Profile())
    prompt = build_system_prompt(config)
    assert "http://127.0.0.1:8765" in prompt and "http://127.0.0.1:9000" in prompt


def test_login_tool_follows_a_way_to_sign_in():
    from loeb.profile import Profile
    from loeb.tool_registry import tool_definitions

    assert "login" in {t["name"] for t in tool_definitions(Profile())}
    assert "login" not in {t["name"] for t in tool_definitions(Profile(), login=False)}
