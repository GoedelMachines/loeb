import base64
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from loeb.config import Config
from loeb.profile import profile_of

SCREENSHOTS_DIR = Path("screenshots")

# navigate() only goes to web pages. file:// (and chrome://, data:, ...) would let
# the model read local files such as .env into its context and then into an issue.
_ALLOWED_SCHEMES = {"http", "https"}


def _origin(url: str) -> str:
    """scheme://host[:port], lowercased, with default ports dropped."""
    p = urlparse(url)
    port = f":{p.port}" if p.port and p.port != {"http": 80, "https": 443}.get(p.scheme) else ""
    return f"{p.scheme.lower()}://{(p.hostname or '').lower()}{port}"


def _safe_screenshot_name(name: str) -> str:
    """A model-supplied screenshot name reduced to a plain file stem (no paths)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name).name).lstrip(".")

# Injected before any page script. Overrides getUserMedia so we control the
# microphone MediaStream via Web Audio API, and exposes __injectAudioPCM /
# __injectSilence for feeding audio into the stream at runtime.
_AUDIO_INIT_SCRIPT = """
(function() {
    let audioCtx = null;
    let destination = null;

    function getAudioCtx() {
        if (!audioCtx) {
            audioCtx = new AudioContext({ sampleRate: 48000 });
            destination = audioCtx.createMediaStreamDestination();
        }
        if (audioCtx.state === 'suspended') { audioCtx.resume(); }
        return { audioCtx, destination };
    }

    const _origGetUserMedia = navigator.mediaDevices.getUserMedia.bind(
        navigator.mediaDevices
    );

    navigator.mediaDevices.getUserMedia = async function(constraints) {
        if (constraints && constraints.audio) {
            const { destination } = getAudioCtx();
            const audioTracks = destination.stream.getAudioTracks();
            if (constraints.video) {
                const real = await _origGetUserMedia({ video: constraints.video });
                return new MediaStream([
                    ...audioTracks,
                    ...real.getVideoTracks()
                ]);
            }
            return new MediaStream(audioTracks);
        }
        return _origGetUserMedia(constraints);
    };

    // Feed raw PCM-16 LE audio (base64-encoded) into the overridden stream.
    window.__injectAudioPCM = function(b64, sampleRate) {
        sampleRate = sampleRate || 48000;
        const { audioCtx, destination } = getAudioCtx();
        const raw = atob(b64);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

        const view = new DataView(bytes.buffer);
        const float32 = new Float32Array(bytes.length / 2);
        for (let i = 0; i < float32.length; i++) {
            float32[i] = view.getInt16(i * 2, true) / 32768.0;
        }

        const buf = audioCtx.createBuffer(1, float32.length, sampleRate);
        buf.copyToChannel(float32, 0);
        const src = audioCtx.createBufferSource();
        src.buffer = buf;
        src.connect(destination);
        src.start();
        return { duration: float32.length / sampleRate, samples: float32.length };
    };

    window.__injectSilence = function(seconds) {
        const { audioCtx, destination } = getAudioCtx();
        const sr = 48000;
        const buf = audioCtx.createBuffer(1, Math.floor(sr * seconds), sr);
        const src = audioCtx.createBufferSource();
        src.buffer = buf;
        src.connect(destination);
        src.start();
        return { duration: seconds };
    };
})();
"""


class BrowserTools:
    def __init__(self, config: Config, headless: bool = True):
        self.config = config
        self.headless = headless
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._playwright = None
        self._screenshot_count = 0
        self._console_messages: list[str] = []

    async def launch(self) -> str:
        SCREENSHOTS_DIR.mkdir(exist_ok=True)
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-web-security",
            ],
        )
        self.context = await self.browser.new_context(
            permissions=["microphone"],
            viewport={"width": 1280, "height": 720},
        )
        # Override getUserMedia before any page script runs
        await self.context.add_init_script(_AUDIO_INIT_SCRIPT)
        self.page = await self.context.new_page()
        self.page.on(
            "console",
            lambda msg: self._console_messages.append(f"[{msg.type}] {msg.text}"),
        )
        return "Browser launched with virtual audio device."

    # ------------------------------------------------------------------
    # Audio injection (via Web Audio API in the browser)
    # ------------------------------------------------------------------

    async def inject_audio_pcm(self, pcm_bytes: bytes) -> dict:
        """Send raw PCM-16 LE audio into the overridden getUserMedia stream."""
        if not self.page:
            raise RuntimeError("No browser page open.")
        b64 = base64.b64encode(pcm_bytes).decode("ascii")
        result = await self.page.evaluate(f"window.__injectAudioPCM('{b64}', 48000)")
        return result

    async def inject_silence(self, duration_seconds: float) -> dict:
        """Inject silence into the overridden getUserMedia stream."""
        if not self.page:
            raise RuntimeError("No browser page open.")
        result = await self.page.evaluate(f"window.__injectSilence({duration_seconds})")
        return result

    # ------------------------------------------------------------------
    # Navigation & interaction
    # ------------------------------------------------------------------

    def allowed_origins(self) -> set[str]:
        from loeb.profile import profile_of

        urls = [self.config.website_url, self.config.api_base_url,
                *profile_of(self.config).extra_origins]
        return {_origin(u) for u in urls if u}

    async def navigate(self, url: str) -> str:
        if not self.page:
            return "No browser page open. Call launch() first."
        if url != "about:blank":
            url = urljoin(self.config.website_url.rstrip("/") + "/", url)
            if urlparse(url).scheme.lower() not in _ALLOWED_SCHEMES:
                return f"Error: navigate only opens http(s) URLs, not '{url}'."
            allowed = self.allowed_origins()
            if _origin(url) not in allowed:
                return (f"Error: {url} is outside the app under test. navigate opens only "
                        f"{', '.join(sorted(allowed))} (others go in the profile's "
                        "extra_origins).")
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        return f"Navigated to {url}. Title: {await self.page.title()}"

    async def click(self, selector: str) -> str:
        if not self.page:
            return "No browser page open."
        try:
            el = self.page.locator(selector).first
            if await el.count() > 0:
                await el.click(timeout=5000)
                return f"Clicked element: {selector}"
        except Exception:
            pass
        try:
            el = self.page.get_by_text(selector).first
            await el.click(timeout=5000)
            return f"Clicked element with text: {selector}"
        except Exception as e:
            return f"Could not click '{selector}': {e}"

    async def type_text(self, selector: str, text: str) -> str:
        if not self.page:
            return "No browser page open."
        try:
            await self.page.fill(selector, text, timeout=5000)
            return f"Typed '{text}' into {selector}"
        except Exception as e:
            return f"Could not type into '{selector}': {e}"

    async def screenshot(self, name: str = "") -> str:
        if not self.page:
            return "No browser page open. Call launch() first."
        self._screenshot_count += 1
        filename = _safe_screenshot_name(name) or f"screenshot_{self._screenshot_count}"
        path = SCREENSHOTS_DIR / f"{filename}.png"
        await self.page.screenshot(path=path, full_page=False)
        return f"Screenshot saved to {path}"

    async def read_transcription(self) -> str:
        if not self.page:
            return "No browser page open."
        selectors = profile_of(self.config).transcription
        if not selectors.configured:
            return (
                "Error: no transcription selectors in the target profile"
                " (transcription.user_selector / agent_selector)."
            )
        try:
            parts = []
            for label, selector in (("User said", selectors.user_selector),
                                    ("Agent said", selectors.agent_selector)):
                if not selector:
                    continue
                el = self.page.locator(selector)
                text = await el.first.text_content(timeout=2000) if await el.count() > 0 else ""
                if text:
                    parts.append(f"{label}: {text}")
            return "\n".join(parts) if parts else "No transcription visible."
        except Exception as e:
            return f"Error reading transcription: {e}"

    async def read_console(self) -> str:
        if not self._console_messages:
            return "No console messages captured."
        return "\n".join(self._console_messages[-50:])

    async def get_page_text(self) -> str:
        if not self.page:
            return "No browser page open."
        return await self.page.inner_text("body")

    async def upload_file(self, selector: str, file_path: str) -> str:
        if not self.page:
            return "No browser page open."
        try:
            await self.page.set_input_files(selector, file_path, timeout=5000)
            return f"Uploaded {file_path} to {selector}"
        except Exception as e:
            return f"Upload failed: {e}"

    async def get_element_state(self, selector: str) -> str:
        if not self.page:
            return "No browser page open."
        try:
            el = self.page.locator(selector).first
            if await el.count() == 0:
                return f"Element '{selector}' not found."
            visible = await el.is_visible()
            text = await el.text_content()
            classes = await el.get_attribute("class") or ""
            return f"selector={selector} visible={visible} text='{text}' classes='{classes}'"
        except Exception as e:
            return f"Error checking element: {e}"

    async def wait_for_selector(self, selector: str, timeout_ms: int = 10000) -> str:
        if not self.page:
            return "No browser page open."
        try:
            await self.page.wait_for_selector(selector, timeout=timeout_ms)
            return f"Element '{selector}' appeared."
        except Exception as e:
            return f"Timeout waiting for '{selector}': {e}"

    def default_login_method(self) -> str:
        """Token login only when Supabase is configured; otherwise the sign-in form."""
        if self.config.supabase_url and self.config.supabase_anon_key:
            return "token"
        return "browser"

    async def login(self, method: str | None = None) -> str:
        """Sign in as the test user. 'token' injects session, 'browser' uses UI."""
        if not self.config.test_email or not self.config.test_password:
            return "Error: TEST_EMAIL / TEST_PASSWORD not set; cannot sign in."
        method = method or self.default_login_method()
        if method == "token":
            return await self._login_via_token()
        return await self._login_via_browser()

    async def _login_via_token(self) -> str:
        """Sign in by calling Supabase Auth API and injecting the session into localStorage."""
        if not self.page:
            return "No browser page open. Call launch() and navigate() first."
        if not self.config.supabase_url or not self.config.supabase_anon_key:
            return (
                "Error: SUPABASE_URL / SUPABASE_ANON_KEY not configured, so token login is"
                " unavailable. Use method='browser'."
            )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.config.supabase_url}/auth/v1/token?grant_type=password",
                    headers={
                        "apikey": self.config.supabase_anon_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "email": self.config.test_email,
                        "password": self.config.test_password,
                    },
                )
                resp.raise_for_status()
                session = resp.json()

            # Extract project ref from the Supabase URL (https://<ref>.supabase.co)
            project_ref = self.config.supabase_url.split("//")[1].split(".")[0]
            storage_key = f"sb-{project_ref}-auth-token"

            await self.page.evaluate(
                f"localStorage.setItem('{storage_key}', JSON.stringify({json.dumps(session)}))"
            )
            await self.page.reload(wait_until="networkidle")
            return (
                f"Logged in as {self.config.test_email} via token injection."
                f" Session stored in localStorage['{storage_key}']."
            )
        except Exception as e:
            return f"Token login failed: {e}"

    async def _login_via_browser(self) -> str:
        """Sign in by filling in the sign-in form in the browser."""
        if not self.page:
            return "No browser page open. Call launch() and navigate() first."
        auth = profile_of(self.config).auth
        if auth is None:
            return (
                'Error: the profile has no sign-in form ("auth"), so browser login is'
                " unavailable. If the app needs one, add it to the profile."
            )
        try:
            await self.page.goto(
                f"{self.config.website_url}{auth.login_path}",
                wait_until="networkidle",
                timeout=15000,
            )
            await self.page.fill(auth.email_selector, self.config.test_email, timeout=5000)
            await self.page.fill(auth.password_selector, self.config.test_password, timeout=5000)
            await self.page.click(auth.submit_selector, timeout=5000)
            await self.page.wait_for_url(auth.success_url_glob, timeout=15000)
            return f"Logged in as {self.config.test_email} via browser sign-in form."
        except Exception as e:
            return f"Browser login failed: {e}"

    async def close(self) -> str:
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self.browser = None
        self.page = None
        return "Browser closed."
