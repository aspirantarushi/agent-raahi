"""Speech to text with Sarvam AI (model saaras:v4), the main service for "Speak the story".

- Only the recording is sent, only to turn it into text. It is never saved, by this app or here.
- The REST service takes at most 30 seconds of audio, so a longer WAV recording is split into parts
  under 30 seconds, at pauses (the quietest moment near the end of each part), sent one by one, and
  the text is joined in order.
- The text goes through the same personal-number filter as typed notes.
- Mode by the notes language: Hindi is written as spoken in Devanagari ("transcribe"); Hinglish uses
  "translit" (Hindi in English letters); English uses "transcribe" with the language detected, so English
  speech comes out in English and Hindi speech is written as spoken, never translated (tested live: with
  "en-IN", a Hindi recording was sometimes translated into English).
The key is SARVAM_API_KEY (environment, .env or the host's secret settings), never in the code.
Errors raise SarvamUnavailable; multilingual.py then falls back to Gemini, then to typing.
"""

import array
import io
import json
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import privacy
import storage

URL = "https://api.sarvam.ai/speech-to-text"
MODEL = "saaras:v4"
NAME = f"Sarvam AI ({MODEL})"
MAX_SECONDS = 30          # the REST limit
PART_SECONDS = 27.0       # aim for parts a little under the limit
SEARCH_SECONDS = 9.0      # look for a pause in the last 9 seconds of each part
TIMEOUT = 40

HINGLISH = "hi-Latn"
# notes language -> (language_code, mode)
MODES = {"en": ("unknown", "transcribe"), "hi": ("hi-IN", "transcribe"), HINGLISH: ("hi-IN", "translit")}


class SarvamUnavailable(Exception):
    def __init__(self, message: str, kind: str = "error", code: Optional[int] = None):
        super().__init__(message)
        self.kind = kind   # "no key", "timeout", "network", "quota", "busy", "key", "refused", "empty"
        self.code = code


def api_key() -> str:
    return storage.setting("SARVAM_API_KEY")


def configured() -> bool:
    return bool(api_key())


@dataclass
class Transcript:
    text: str
    removed: Dict[str, int]
    parts: int
    by: str = NAME


# ---------- splitting a WAV recording at pauses ----------

def _wav(audio: bytes):
    try:
        with wave.open(io.BytesIO(audio)) as w:
            return w.getparams(), w.readframes(w.getnframes())
    except Exception:
        return None, None


def _to_wav(params, frames: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(params.nchannels), w.setsampwidth(params.sampwidth), w.setframerate(params.framerate)
        w.writeframes(frames)
    return out.getvalue()


def _loudness(frames: bytes, params, window: int) -> List[float]:
    """Mean absolute level of each window of `window` frames (16-bit audio; other widths: all equal)."""
    count = len(frames) // (params.sampwidth * params.nchannels)
    if params.sampwidth != 2:
        return [1.0] * (count // window + 1)
    samples = array.array("h")
    samples.frombytes(frames[: count * 2 * params.nchannels])
    step = window * params.nchannels
    return [sum(abs(s) for s in samples[i:i + step]) / max(1, len(samples[i:i + step]))
            for i in range(0, len(samples), step)]


def split(audio: bytes) -> List[bytes]:
    """The recording as WAV parts under 30 seconds each, cut at pauses. Not a WAV (or short): one part."""
    params, frames = _wav(audio)
    if params is None:
        return [audio]
    rate, frame_bytes = params.framerate, params.sampwidth * params.nchannels
    total = len(frames) // frame_bytes
    if total <= PART_SECONDS * rate:
        return [audio]
    window = max(1, rate // 20)  # 50 ms
    level = _loudness(frames, params, window)
    parts, start = [], 0
    while total - start > PART_SECONDS * rate:
        hi = start + int(PART_SECONDS * rate)
        lo = start + int((PART_SECONDS - SEARCH_SECONDS) * rate)
        candidates = range(lo // window, hi // window)
        cut = min(candidates, key=lambda i: (level[i] if i < len(level) else 0, -i)) * window if candidates else hi
        cut = min(max(cut, start + window), hi)  # never longer than the limit
        parts.append(_to_wav(params, frames[start * frame_bytes: cut * frame_bytes]))
        start = cut
    parts.append(_to_wav(params, frames[start * frame_bytes:]))
    return parts


# ---------- the service ----------

def _form(fields: Dict[str, str], audio: bytes, filename: str, mime: str):
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for name, value in fields.items():
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
               f"Content-Type: {mime}\r\n\r\n".encode())
    body.write(audio)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def _post(audio: bytes, mime: str, language_code: str, mode: str, key: str) -> dict:
    """One request to Sarvam (at most 30 seconds of audio). Tests replace this; they never call Sarvam."""
    import llm  # the same HTTPS certificates as the AI calls
    data, content_type = _form({"model": MODEL, "language_code": language_code, "mode": mode},
                               audio, "speech.wav" if "wav" in mime else "speech", mime)
    request = urllib.request.Request(URL, data=data, method="POST",
                                     headers={"api-subscription-key": key, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=llm._ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        kind = {400: "refused", 403: "key", 422: "refused", 429: "quota", 503: "busy"}.get(err.code, "error")
        raise SarvamUnavailable(f"Sarvam answered with error {err.code}.", kind, err.code) from None
    except (TimeoutError, OSError) as err:
        kind = "timeout" if "timed out" in str(err).lower() else "network"
        raise SarvamUnavailable("Sarvam could not be reached.", kind) from None
    except ValueError:
        raise SarvamUnavailable("Sarvam's answer could not be read.", "error") from None


def transcribe(audio: bytes, mime_type: str, language: str,
               progress: Optional[Callable[[int, int], None]] = None) -> Transcript:
    """Speech to text, part by part (progress(n, total) before each part). Raises SarvamUnavailable."""
    key = api_key()
    if not key:
        raise SarvamUnavailable("Sarvam is not set up (no SARVAM_API_KEY).", "no key")
    if not audio:
        raise SarvamUnavailable("The recording is empty.", "empty")
    language_code, mode = MODES.get(language, ("unknown", "transcribe"))
    parts = split(audio)
    texts = []
    for n, part in enumerate(parts, 1):
        if progress:
            progress(n, len(parts))
        answer = _post(part, "audio/wav" if len(parts) > 1 else (mime_type or "audio/wav"), language_code, mode, key)
        text = answer.get("transcript") if isinstance(answer, dict) else None
        if not isinstance(text, str):
            raise SarvamUnavailable("Sarvam's answer had no text.", "error")
        texts.append(text.strip())
    clean, removed = privacy.redact(" ".join(t for t in texts if t))
    return Transcript(clean, removed, len(parts))
