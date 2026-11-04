"""Notes and recordings in any scheduled language. Plain code that decides who does what.

- English, Hindi and Hinglish notes go straight to the AI reader (Gemini), as before.
- Notes in another scheduled language are filtered for personal numbers, translated to English by
  Bhashini, and then read by the AI; the volunteer checks every fact as before.
- Recordings: Bhashini speech-to-text where it supports the language, otherwise Gemini.
If Bhashini is not set up or fails, BhashiniUnavailable is raised: the app then says so and asks for
English or Hindi.
"""

import io
import wave
from dataclasses import dataclass
from typing import Dict, Optional

import bhashini
import lang
import llm
import privacy

DIRECT = ("en", "hi")  # the AI reads these (and Hinglish) itself


def note_languages() -> Dict[str, str]:
    """English, Hindi, then the other scheduled languages, each in its own script."""
    return {"en": "English", "hi": lang.NATIVE_NAMES["hi"],
            **{c: native for c, (_, native) in bhashini.LANGUAGES.items() if c != "hi"}}


@dataclass
class PreparedNotes:
    text: str                       # what the AI reads (filtered; in English if it was translated)
    removed: Dict[str, int]         # personal numbers removed before anything was sent
    translated_from: Optional[str]  # the language code, if Bhashini translated the notes


def prepare(notes: str, language: str) -> PreparedNotes:
    """Filter first, then translate to English with Bhashini if the AI can't read the language itself."""
    clean, removed = privacy.redact(notes)
    if language in DIRECT or not clean.strip():
        return PreparedNotes(clean, removed, None)
    translation = bhashini.translate(clean, language, "en")  # raises BhashiniUnavailable
    for kind, n in translation.removed.items():
        removed[kind] = removed.get(kind, 0) + n
    return PreparedNotes(translation.text, removed, language)


# ---------- voice ----------

@dataclass
class SpokenText:
    text: str
    removed: Dict[str, int]
    by: str  # "Bhashini" or the Gemini model


def _wav_rate(audio: bytes) -> Optional[int]:
    try:
        with wave.open(io.BytesIO(audio)) as w:
            return w.getframerate()
    except Exception:
        return None


def speech_to_text(audio: bytes, mime_type: str, language: str) -> SpokenText:
    """Bhashini where it supports the language (a WAV recording), otherwise Gemini.
    The recording is never saved; the text is filtered for personal numbers."""
    if language not in DIRECT and bhashini.configured():
        rate = _wav_rate(audio)
        if rate and bhashini.supports("asr", language):
            result = bhashini.speech_to_text(audio, language, "wav", rate)
            return SpokenText(result.text, result.removed, "Bhashini")
    script = language if language in DIRECT else "other"  # other languages: "write it in its own script"
    result = llm.transcribe(audio, mime_type, script=script)
    return SpokenText(result.text, result.removed, result.model)
