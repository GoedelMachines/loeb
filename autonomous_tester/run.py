import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

from autonomous_tester.agent import DEFAULT_PROMPT, Agent
from autonomous_tester.config import Config
from autonomous_tester.tool_registry import ToolRegistry
from autonomous_tester.tools.audio import AudioSystem
from autonomous_tester.tools.backend import BackendTools
from autonomous_tester.tools.browser import BrowserTools
from autonomous_tester.tools.git import git_diff
from autonomous_tester.tools.reporter import Reporter
from autonomous_tester.tools.services import ServiceManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Löb — autonomous agentic end-to-end tester")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="What to test (e.g. 'Test the mute button'). Omit for interactive mode.",
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
        type=int,
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
        "--ci",
        action="store_true",
        help="Run full test loop without TUI. Exit 0=pass, 1=bugs found, 2=error.",
    )
    return parser.parse_args()


def _get_diff_summary(repo_dir: str, repo_name: str) -> str:
    """Get a short diff summary for the interactive wizard."""
    try:
        diff = git_diff(repo_dir, "HEAD~1")
        lines = diff.split("\n")
        stat = next((ln for ln in lines if "file" in ln and "changed" in ln), "no changes")
        return f"{repo_name}: {stat.strip()}"
    except Exception:
        return f"{repo_name}: unable to read diff"


async def _run_dry(config: Config) -> None:
    """Dry run: read diffs and print a test plan proposal."""
    from rich.console import Console
    from rich.panel import Panel

    from autonomous_tester.llm import create_provider

    console = Console()
    console.print(Panel("[bold]Dry Run Mode[/bold]", border_style="yellow"))

    backend_diff = git_diff(config.backend_dir, "HEAD~1")
    frontend_diff = git_diff(config.frontend_dir, "HEAD~1")

    console.print("\n[bold cyan]backend diff:[/bold cyan]")
    console.print(backend_diff[:2000] if len(backend_diff) > 2000 else backend_diff)
    console.print("\n[bold cyan]frontend diff:[/bold cyan]")
    console.print(frontend_diff[:2000] if len(frontend_diff) > 2000 else frontend_diff)

    provider = create_provider(config)
    prompt = (
        "You are reviewing these git diffs for the app under test. "
        "Propose a test plan: what should be tested, what edge cases to check, "
        "and what backend side effects to verify. Be specific.\n\n"
        f"backend diff:\n{backend_diff[:3000]}\n\n"
        f"frontend diff:\n{frontend_diff[:3000]}"
    )
    result = await provider.complete(
        system="You are a QA engineer reviewing code changes.",
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
    from autonomous_tester.llm import create_provider

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
    services, browser, agent = _build_stack(config, headless)
    if max_iterations is not None:
        agent.max_iterations = max_iterations
    try:
        await agent.run(prompt=prompt)
    except Exception as e:
        from rich.console import Console

        Console().print(f"[bold red]CI run failed:[/bold red] {e}")
        return 2
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        services.stop_all()

    return 1 if agent.bugs_found else 0


async def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    args = parse_args()
    config = Config()

    if args.model:
        config.model = args.model
    if args.provider:
        config.provider = args.provider
    if args.openai_model:
        config.provider = "openai"
        config.openai_model = args.openai_model

    # Dry run — no TUI, just print plan
    if args.dry_run:
        await _run_dry(config)
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
    services, browser, agent = _build_stack(config, headless)

    if args.max_iterations:
        agent.max_iterations = args.max_iterations

    prompt = args.prompt

    # Interactive mode — no prompt given
    if prompt is None:
        from autonomous_tester.ui.app import TesterApp

        backend_summary = _get_diff_summary(config.backend_dir, "backend")
        frontend_summary = _get_diff_summary(config.frontend_dir, "frontend")

        app = TesterApp(
            agent=agent,
            prompt="",
            headless=headless,
            verbose=args.verbose,
        )
        app._interactive = True
        app._backend_summary = backend_summary
        app._frontend_summary = frontend_summary

        try:
            await app.run_async()
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            services.stop_all()
        return

    # Direct mode — prompt given, launch TUI
    from autonomous_tester.ui.app import TesterApp

    default_prompt = "Begin testing. Read git diffs to decide what to test."
    app = TesterApp(
        agent=agent,
        prompt=prompt or default_prompt,
        headless=headless,
        verbose=args.verbose,
        auto_exit=True,  # one-shot run: exit the TUI when the agent finishes
    )

    try:
        await app.run_async()
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        services.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
