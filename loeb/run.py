import argparse
import asyncio
import sys

from loeb.agent import DEFAULT_PROMPT, Agent
from loeb.config import Config, load_env
from loeb.tool_registry import ToolRegistry
from loeb.tools.audio import AudioSystem
from loeb.tools.backend import BackendTools
from loeb.tools.browser import BrowserTools
from loeb.tools.git import git_diff
from loeb.tools.reporter import Reporter
from loeb.tools.services import ServiceManager

EXIT_PASS, EXIT_BUGS, EXIT_ERROR = 0, 1, 2


def exit_code(agent: Agent) -> int:
    """0 = the model finished and reported no bugs; 1 = bugs reported; 2 = the run
    did not finish (crash, iteration cap, refusal) — an unfinished run is never a pass."""
    if agent.error or not agent.finished:
        return EXIT_ERROR
    return EXIT_BUGS if agent.bugs_found else EXIT_PASS


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _fail(message: str) -> int:
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/bold red] {message}")
    return EXIT_ERROR


def parse_args(argv: list[str] | None = None, prog: str | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog, description="Löb — autonomous agentic end-to-end tester"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help=(
            "What to test (e.g. 'Test the mute button'). Omit to let the agent decide from"
            " the diffs, with the dashboard left open afterwards."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the Claude model (e.g. claude-opus-4-20250514)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["anthropic", "openai"],
        help="LLM provider (default: anthropic)",
    )
    parser.add_argument(
        "--openai-model",
        default=None,
        help="OpenAI model name (e.g. gpt-4o, o3). Implies --provider openai.",
    )
    parser.add_argument(
        "--max-iterations",
        type=_positive_int,
        default=None,
        help="Max agent loop iterations (default: 200)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window (default: headless)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read diff and propose test plan without executing. No services or browser.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Start with verbose mode on (full tool results in log).",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Load settings from this .env (default: ./.env, else the Löb checkout's .env).",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help=(
            "Run full test loop without TUI. Exit 0 = finished, no bugs; 1 = bugs found;"
            " 2 = error or unfinished run (setup error, crash, iteration cap)."
        ),
    )
    return parser.parse_args(argv)


async def _run_dry(config: Config) -> None:
    """Dry run: read the profile's repo diffs and print a test plan proposal."""
    from rich.console import Console
    from rich.panel import Panel

    from loeb.agent import build_system_prompt
    from loeb.llm import create_provider
    from loeb.profile import load_profile

    console = Console()
    console.print(Panel("[bold]Dry Run Mode[/bold]", border_style="yellow"))

    config.profile = load_profile(config)
    system = build_system_prompt(config)  # includes the target description
    provider = create_provider(config)

    diffs = {name: git_diff(path, "HEAD~1") for name, path in config.profile.repos.items()}
    for name, diff in diffs.items():
        console.print(f"\n[bold cyan]{name} diff:[/bold cyan]")
        console.print(diff[:2000])
    if not diffs:
        console.print("\n[yellow]No repos configured; planning from the target description.")

    prompt = (
        "Do not call any tools. Propose a test plan for the app described in your"
        " instructions: what should be tested, what edge cases to check, and what backend"
        " side effects to verify. Be specific.\n\n"
        + "\n\n".join(f"{name} diff:\n{diff[:3000]}" for name, diff in diffs.items())
    )
    result = await provider.complete(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        max_tokens=2048,
    )
    content = result.raw_content
    if isinstance(content, list):
        plan = next((b.text for b in content if hasattr(b, "text")), str(content))
    elif isinstance(content, dict):
        plan = content.get("content") or str(content)
    else:
        plan = str(content)
    console.print("\n[bold green]Proposed Test Plan:[/bold green]")
    console.print(Panel(plan, border_style="green"))


def _build_stack(config: Config, headless: bool):
    """Build the tool stack (services, browser, audio, backend, reporter, registry, agent)."""
    from loeb.llm import create_provider
    from loeb.profile import load_profile

    config.profile = load_profile(config)  # validated once; ProfileError on a bad profile
    services = ServiceManager(config)
    browser = BrowserTools(config, headless=headless)
    audio = AudioSystem(config, browser=browser)
    backend = BackendTools(config)
    reporter = Reporter(config)
    registry = ToolRegistry(
        services=services,
        browser=browser,
        audio=audio,
        backend=backend,
        reporter=reporter,
        config=config,
    )
    provider = create_provider(config)
    agent = Agent(config, registry, provider)
    return services, browser, agent


async def _run_ci(
    config: Config, prompt: str, headless: bool, max_iterations: int | None = None,
) -> int:
    """Run the full agent loop without TUI. Returns exit code: 0=pass, 1=bugs, 2=error."""
    from rich.console import Console

    try:
        services, browser, agent = _build_stack(config, headless)
    except Exception as e:
        return _fail(f"setup failed: {e}")
    if max_iterations is not None:
        agent.max_iterations = max_iterations
    try:
        await agent.run(prompt=prompt)
    except Exception as e:
        Console().print(f"[bold red]CI run failed:[/bold red] {e}")
        if agent.bugs_found:
            Console().print(f"Bugs reported before the failure: {len(agent.bugs_found)}")
        return EXIT_ERROR
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        services.stop_all()

    code = exit_code(agent)
    if code == EXIT_ERROR:
        Console().print(f"[bold red]Run did not finish:[/bold red] {agent.stop_problem}")
    return code


async def main(argv: list[str] | None = None, prog: str | None = None):
    args = parse_args(argv, prog)
    try:
        load_env(args.env_file)
        config = Config()
    except ValueError as e:
        sys.exit(_fail(f"bad configuration: {e}"))

    if args.model:
        config.model = args.model
    if args.provider:
        config.provider = args.provider
    if args.openai_model:
        config.provider = "openai"
        config.openai_model = args.openai_model

    # Dry run — no TUI, just print plan
    if args.dry_run:
        try:
            await _run_dry(config)
        except Exception as e:
            sys.exit(_fail(f"dry run failed: {e}"))
        return

    # CI mode — full run, no TUI
    if args.ci:
        headless = not args.no_headless
        prompt = args.prompt or DEFAULT_PROMPT
        code = await _run_ci(
            config, prompt=prompt, headless=headless, max_iterations=args.max_iterations
        )
        sys.exit(code)

    headless = not args.no_headless
    try:
        services, browser, agent = _build_stack(config, headless)
    except Exception as e:
        sys.exit(_fail(f"setup failed: {e}"))

    if args.max_iterations:
        agent.max_iterations = args.max_iterations

    from loeb.ui.app import TesterApp

    # No prompt: the agent starts from DEFAULT_PROMPT (diff-driven) and the dashboard
    # stays open afterwards. With a prompt: one-shot run, the TUI exits when done.
    app = TesterApp(
        agent=agent,
        prompt=args.prompt or "",
        headless=headless,
        verbose=args.verbose,
        auto_exit=args.prompt is not None,
    )
    try:
        await app.run_async()
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        services.stop_all()
    # The TUI only flashes a toast on failure; say it again on the terminal it left.
    if app.agent_error:
        sys.exit(_fail(f"run failed: {app.agent_error}"))


if __name__ == "__main__":
    asyncio.run(main())
