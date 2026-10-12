from unittest.mock import MagicMock

import pytest

from loeb.tools.audio import AudioSystem


@pytest.fixture
def config():
    mock = MagicMock()
    mock.deepgram_api_key = "test-key"
    return mock


def test_audio_system_init(config):
    audio = AudioSystem(config)
    assert audio.browser is None


def test_audio_system_init_with_browser(config):
    browser = MagicMock()
    audio = AudioSystem(config, browser=browser)
    assert audio.browser is browser


@pytest.mark.asyncio
async def test_inject_audio_without_any_tts():
    # Local TTS unreachable and no Deepgram key -> a clear message, no raise.
    config = MagicMock()
    config.deepgram_api_key = ""
    config.tts_url = "http://127.0.0.1:1"  # nothing listens here
    browser = MagicMock()
    browser.page = MagicMock()
    audio = AudioSystem(config, browser=browser)
    result = await audio.inject_audio("hello")
    assert "no Deepgram API key" in result and "Local TTS" in result


def test_wav_to_pcm48k_resamples():
    import struct

    from loeb.tools.audio import AudioSystem as A

    rate, n = 44100, 4410  # 0.1s of silence, mono int16
    pcm = b"\x00\x00" * n
    wav = (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )
    out = A._wav_to_pcm48k(wav)
    assert abs(len(out) // 2 - 4800) <= 2  # ~0.1s at 48k


def _wav(pcm: bytes, rate: int, channels: int) -> bytes:
    import struct

    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * 2 * channels, 2 * channels, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


def test_wav_to_pcm48k_keeps_tone_pitch_and_level():
    import numpy as np

    from loeb.tools.audio import AudioSystem as A

    rate, freq = 24000, 440.0
    t = np.arange(rate) / rate  # 1 s
    tone = (10000 * np.sin(2 * np.pi * freq * t)).astype("<i2").tobytes()
    out = np.frombuffer(A._wav_to_pcm48k(_wav(tone, rate, 1)), dtype="<i2")
    assert len(out) == 48000
    peak_hz = np.argmax(np.abs(np.fft.rfft(out))) * 48000 / len(out)
    assert abs(peak_hz - freq) <= 1
    assert 9500 <= np.abs(out).max() <= 10000


def test_wav_to_pcm48k_averages_stereo_to_mono():
    import numpy as np

    from loeb.tools.audio import AudioSystem as A

    frames = np.array([[1000, 3000], [-2000, 0], [32767, 32767]] * 100, dtype="<i2")
    out = np.frombuffer(A._wav_to_pcm48k(_wav(frames.tobytes(), 48000, 2)), dtype="<i2")
    assert list(out[:3]) == [2000, -1000, 32767]


@pytest.mark.asyncio
async def test_inject_audio_without_browser():
    config = MagicMock()
    config.deepgram_api_key = "test-key"
    audio = AudioSystem(config, browser=None)
    result = await audio.inject_audio("hello")
    assert "No browser page open" in result


@pytest.mark.asyncio
async def test_inject_silence_without_browser():
    config = MagicMock()
    config.deepgram_api_key = "test-key"
    audio = AudioSystem(config, browser=None)
    result = await audio.inject_silence(2.0)
    assert "No browser page open" in result
