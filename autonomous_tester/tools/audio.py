from __future__ import annotations

import audioop
import struct
from typing import TYPE_CHECKING

import httpx

from autonomous_tester.config import Config

if TYPE_CHECKING:
    from autonomous_tester.tools.browser import BrowserTools

# The browser injector plays PCM at this rate (see browser.py __injectAudioPCM).
INJECT_RATE = 48000


class AudioSystem:
    """TTS for inject_audio.

    Primary: a local TTS server at TTS_URL (e.g. Kokoro-82M behind
    POST /v1/tts -> mono int16 WAV). Fallback: Deepgram, only when a key is
    configured. A local server needs no external key and can be the same TTS
    service the app under test already runs.
    """

    def __init__(self, config: Config, browser: BrowserTools | None = None):
        self.config = config
        self.browser = browser

    async def inject_audio(self, text: str) -> str:
        if not self.browser or not self.browser.page:
            return "No browser page open. Launch browser before injecting audio."
        try:
            try:
                pcm_bytes = await self._tts_local(text)
                source = f"local TTS {self.config.tts_url}"
            except Exception as local_err:
                if not self.config.deepgram_api_key:
                    return (
                        f"Local TTS at {self.config.tts_url} failed ({local_err}) "
                        "and no Deepgram API key is configured."
                    )
                pcm_bytes = await self._tts_deepgram(text)
                source = "Deepgram"
            result = await self.browser.inject_audio_pcm(pcm_bytes)
            duration = result.get("duration", 0)
            return (
                f"Audio injected into browser mic via {source}: '{text}' "
                f"({len(pcm_bytes)} bytes, {duration:.1f}s)"
            )
        except Exception as e:
            return f"Audio injection failed: {e}"

    async def _tts_local(self, text: str) -> bytes:
        """Kokoro server: whole-utterance WAV (blocking path), resampled to 48k."""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.config.tts_url}/v1/tts",
                json={"text": text, "streaming": False},
            )
            resp.raise_for_status()
        return self._wav_to_pcm48k(resp.content)

    @staticmethod
    def _wav_to_pcm48k(wav: bytes) -> bytes:
        """Parse a simple RIFF WAV (16-bit mono PCM) and resample to INJECT_RATE."""
        if len(wav) < 44 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
            raise ValueError("not a RIFF WAV response")
        # fmt chunk at offset 12 in the server's fixed 44-byte header layout.
        channels, rate = struct.unpack_from("<HI", wav, 22)
        pcm = wav[44:]
        if channels != 1:
            pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
        if rate != INJECT_RATE:
            pcm, _ = audioop.ratecv(pcm, 2, 1, rate, INJECT_RATE, None)
        return pcm

    async def _tts_deepgram(self, text: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/speak",
                headers={
                    "Authorization": f"Token {self.config.deepgram_api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
                params={
                    "model": "aura-asteria-en",
                    "encoding": "linear16",
                    "sample_rate": "48000",
                },
            )
            resp.raise_for_status()
            return resp.content

    async def inject_silence(self, duration_seconds: float = 2.0) -> str:
        if not self.browser or not self.browser.page:
            return "No browser page open. Launch browser before injecting silence."
        try:
            result = await self.browser.inject_silence(duration_seconds)
            duration = result.get("duration", duration_seconds)
            return f"Injected {duration}s of silence into browser mic."
        except Exception as e:
            return f"Silence injection failed: {e}"
