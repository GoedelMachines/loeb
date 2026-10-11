from autonomous_tester.config import Config
from autonomous_tester.tools.audio import AudioSystem
from autonomous_tester.tools.backend import BackendTools
from autonomous_tester.tools.browser import BrowserTools
from autonomous_tester.tools.git import git_diff
from autonomous_tester.tools.reporter import Reporter
from autonomous_tester.tools.services import ServiceManager

TOOL_DEFINITIONS = [
    {
        "name": "git_diff",
        "description": (
            "Read the git diff to see what changed in the target app's repos."
            " Use this first to decide what to test."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "enum": ["backend", "frontend"],
                    "description": "Which repo to diff.",
                },
                "base": {
                    "type": "string",
                    "description": "Git ref to diff against. Default: HEAD~1.",
                    "default": "HEAD~1",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "start_services",
        "description": (
            "Verify the target stack is up (health checks for API, website, and any services"
            " listed in the target config). Löb never starts the stack; down services are"
            " reported with their start commands. Call this before any testing."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "stop_services",
        "description": (
            "Release the target stack when testing is complete"
            " (Löb never stops a shared stack)."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "launch_browser",
        "description": (
            "Launch a headless Chrome browser with virtual audio device."
            " Must call before any browser actions."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "navigate",
        "description": "Navigate the browser to a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": "Click an element in the browser by CSS selector or visible text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector or visible text to click.",
                },
            },
            "required": ["selector"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into an input field.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the input.",
                },
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "screenshot",
        "description": "Take a screenshot of the current browser page. Returns the file path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Optional name for the screenshot file.",
                },
            },
        },
    },
    {
        "name": "read_transcription",
        "description": (
            "Read the current transcription/subtitle text from the voice session page."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_console",
        "description": "Read browser console messages (JS errors, warnings, logs).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_page_text",
        "description": "Get all visible text content from the current page.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_element_state",
        "description": "Check if a DOM element exists, is visible, and get its classes/text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector to check.",
                },
            },
            "required": ["selector"],
        },
    },
    {
        "name": "wait_for_selector",
        "description": "Wait for a DOM element to appear on the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector to wait for.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Max wait time in ms. Default: 10000.",
                    "default": 10000,
                },
            },
            "required": ["selector"],
        },
    },
    {
        "name": "upload_file",
        "description": "Upload a file via a file input element in the browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the file input.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to upload.",
                },
            },
            "required": ["selector", "file_path"],
        },
    },
    {
        "name": "inject_audio",
        "description": (
            "Generate TTS audio from text and inject it as microphone input to the browser."
            " This is how you speak to the app."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to say to the app."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "inject_silence",
        "description": "Inject a period of silence into the audio stream.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_seconds": {
                    "type": "number",
                    "description": "How long to be silent. Default: 2.0.",
                    "default": 2.0,
                },
            },
        },
    },
    {
        "name": "check_api",
        "description": (
            "Make an HTTP request to the target app's backend API and return the response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "description": "HTTP method.",
                },
                "path": {
                    "type": "string",
                    "description": "API path (e.g. /api/health).",
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON body for POST/PUT.",
                },
            },
            "required": ["method", "path"],
        },
    },
    {
        "name": "query_db",
        "description": (
            "Execute a read-only SQL query against the target app's PostgreSQL database"
            " (conversation history, session titles)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL SELECT query to execute.",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "query_redis",
        "description": (
            "Scan Redis for keys matching a pattern and return their values."
            " Key patterns: user_config:*, tool:*, active_room:*, huey:worker:heartbeat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Redis key pattern (e.g. 'tool:*', 'user_config:*').",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_logs",
        "description": (
            "Read logs for a target service (systemd unit, docker container, or docker"
            " compose service, as listed in the target config)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name (unit, container alias, or compose service).",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines. Default: 50.",
                    "default": 50,
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "file_github_issue",
        "description": (
            "Create a GitHub issue on the configured repo (GITHUB_REPO)"
            " with title, body, and labels."
            " Use for bug reports with evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Issue title."},
                "body": {
                    "type": "string",
                    "description": (
                        "Issue body (markdown). Include: commit hash, steps to reproduce,"
                        " screenshots, logs, likely root cause."
                    ),
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to apply (e.g. ['bug', 'löb']).",
                },
            },
            "required": ["title", "body", "labels"],
        },
    },
    {
        "name": "login",
        "description": (
            "Sign in to the app as the test user. method='token' (default) injects a Supabase"
            " session into the browser — fast, no UI interaction needed. method='browser'"
            " fills in the sign-in form — tests the actual sign-in flow. Call after"
            " launch_browser and navigate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["token", "browser"],
                    "description": (
                        "Auth method. 'token' = inject session. 'browser' = use sign-in form."
                    ),
                    "default": "token",
                },
            },
        },
    },
    {
        "name": "send_slack",
        "description": (
            "Send a message to the team Slack channel. Use for test summaries and alerts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message text (supports Slack mrkdwn).",
                },
            },
            "required": ["message"],
        },
    },
]

DEFAULT_TOOL_TIMEOUT = 60  # seconds

TOOL_TIMEOUTS: dict[str, int] = {
    "start_services": 300,
    "stop_services": 120,
    "launch_browser": 60,
    "navigate": 30,
    "inject_audio": 30,
    "inject_silence": 10,
    "wait_for_selector": 30,
    "read_logs": 30,
}


class ToolRegistry:
    def __init__(
        self,
        services: ServiceManager,
        browser: BrowserTools,
        audio: AudioSystem,
        backend: BackendTools,
        reporter: Reporter,
        config: Config,
    ):
        self.services = services
        self.browser = browser
        self.audio = audio
        self.backend = backend
        self.reporter = reporter
        self.config = config

    async def dispatch(self, tool_name: str, tool_input: dict) -> str:
        match tool_name:
            # Git
            case "git_diff":
                repo = tool_input["repo"]
                base = tool_input.get("base", "HEAD~1")
                repo_dir = (
                    self.config.backend_dir if repo == "backend" else self.config.frontend_dir
                )
                return git_diff(repo_dir, base)

            # Services
            case "start_services":
                return await self.services.start_all()
            case "stop_services":
                return self.services.stop_all()

            # Browser
            case "launch_browser":
                return await self.browser.launch()
            case "navigate":
                return await self.browser.navigate(tool_input["url"])
            case "click":
                return await self.browser.click(tool_input["selector"])
            case "type_text":
                return await self.browser.type_text(tool_input["selector"], tool_input["text"])
            case "screenshot":
                return await self.browser.screenshot(tool_input.get("name", ""))
            case "read_transcription":
                return await self.browser.read_transcription()
            case "read_console":
                return await self.browser.read_console()
            case "get_page_text":
                return await self.browser.get_page_text()
            case "get_element_state":
                return await self.browser.get_element_state(tool_input["selector"])
            case "wait_for_selector":
                return await self.browser.wait_for_selector(
                    tool_input["selector"],
                    tool_input.get("timeout_ms", 10000),
                )
            case "upload_file":
                return await self.browser.upload_file(
                    tool_input["selector"], tool_input["file_path"]
                )
            case "login":
                return await self.browser.login(tool_input.get("method", "token"))

            # Audio
            case "inject_audio":
                return await self.audio.inject_audio(tool_input["text"])
            case "inject_silence":
                return await self.audio.inject_silence(tool_input.get("duration_seconds", 2.0))

            # Backend
            case "check_api":
                return await self.backend.check_api(
                    tool_input["method"],
                    tool_input["path"],
                    tool_input.get("body", ""),
                )
            case "query_db":
                return await self.backend.query_db(tool_input["sql"])
            case "query_redis":
                return await self.backend.query_redis(tool_input["pattern"])
            case "read_logs":
                return await self.backend.read_logs(
                    tool_input["service"],
                    tool_input.get("lines", 50),
                )

            # Reporter
            case "file_github_issue":
                return self.reporter.file_github_issue(
                    tool_input["title"],
                    tool_input["body"],
                    tool_input.get("labels", []),
                )
            case "send_slack":
                return await self.reporter.send_slack(tool_input["message"])

            case _:
                return f"Unknown tool: {tool_name}"
