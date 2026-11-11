"""Notes and recordings in any scheduled language. Plain code that decides who does what.

- English, Hindi and Hinglish notes go straight to the AI reader (Gemini), as before.
- Notes in another scheduled language are filtered for personal numbers, translated to English by
  Bhashini, and then read by the AI; the volunteer checks every fact as before.
- Recordings in English, Hindi or Hinglish: Sarvam AI (saaras:v4) first, Gemini as the backup, then
  typing. Other languages: Bhashini where it supports the language, otherwise Gemini.
If Bhashini is not set up or fails, BhashiniUnavailable is raised: the app then says so and asks for
English or Hindi.
"""

import io
import wave
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import audit
import bhashini
import lang
import llm
import privacy
import sarvam

HINGLISH = "hi-Latn"  # Hindi written in English letters
DIRECT = ("en", "hi", HINGLISH)  # the AI reads these itself (drafts stay in English or Hindi)


HINGLISH_WORDS = {"hai", "hain", "nahi", "nahin", "nhi", "ka", "ki", "ke", "ko", "se", "mein", "me", "main", "mera",
                  "meri", "mere", "tha", "thi", "the", "kya", "aur", "bhi", "kar", "karta", "karti", "raha", "rahi",
                  "rahe", "gaya", "gayi", "diya", "di", "mila", "mili", "bhai", "behen", "paisa", "paise", "unka",
                  "unki", "uska", "uski", "humne", "hum", "ab", "abhi", "kuch", "koi", "wala", "wali", "lekin",
                  "par", "pe", "ne", "hua", "hui", "chahiye", "chahte", "chahti", "saal", "mahine", "din", "ghar",
                  "kaam", "maalik", "malik", "bola", "boli", "jab", "tab", "kyunki", "sirf", "bahut"}
ENGLISH_ONLY = {"the", "is", "was", "and", "of", "to", "he", "she", "has", "have", "not", "his", "her", "they"}


def detect_language(text: str) -> Optional[str]:
    """English, Hindi (Devanagari) or Hinglish (Hindi in English letters), by plain counting. None if
    there is too little text to tell. The volunteer can always change it."""
    letters = [c for c in text or "" if c.isalpha()]
    if len(letters) < 12:
        return None
    devanagari = sum(1 for c in letters if "\u0900" <= c <= "\u097f")
    if devanagari / len(letters) > 0.3:
        return "hi"
    words = [w.casefold() for w in __import__("re").findall(r"[A-Za-z]+", text)]
    hindi = sum(1 for w in words if w in HINGLISH_WORDS and w not in ENGLISH_ONLY)
    return HINGLISH if words and (hindi >= 3 and hindi / len(words) >= 0.12) else "en"


def note_languages() -> Dict[str, str]:
    """English, Hindi, Hinglish, then the other scheduled languages, each in its own script."""
    hinglish = {HINGLISH: "Hinglish (Hindi in English letters)"}
    if lang.PILOT_FREEZE:
        return {"en": "English", "hi": lang.NATIVE_NAMES["hi"], **hinglish}
    return {"en": "English", "hi": lang.NATIVE_NAMES["hi"], **hinglish,
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
    by: str              # "Sarvam AI (saaras:v4)", "Bhashini" or the Gemini model
    backup: bool = False  # True when Sarvam failed (or was not set up) and Gemini answered instead


def _wav_rate(audio: bytes) -> Optional[int]:
    try:
        with wave.open(io.BytesIO(audio)) as w:
            return w.getframerate()
    except Exception:
        return None


def speech_to_text(audio: bytes, mime_type: str, language: str,
                   progress: Optional[Callable[[int, int], None]] = None) -> SpokenText:
    """English, Hindi and Hinglish: Sarvam first (in parts under 30 seconds; progress(n, total) before
    each), then Gemini as the backup (progress(0, 0)); if both fail, llm.AIUnavailable (the volunteer
    types instead). A Sarvam failure, or a missing key, is written in the problems log.
    Other languages: Bhashini where it supports the language (a WAV recording), otherwise Gemini.
    The recording is never saved; the text is filtered for personal numbers."""
    if language in DIRECT:
        try:
            result = sarvam.transcribe(audio, mime_type, language, progress)
            return SpokenText(result.text, result.removed, result.by)
        except sarvam.SarvamUnavailable as err:
            failed = {"model": sarvam.NAME, "error": err.kind, "code": err.code}
        if progress:
            progress(0, 0)  # the backup
        script = "en" if language == HINGLISH else language
        try:
            backup = llm.transcribe(audio, mime_type, script=script)
        except llm.AIUnavailable:
            _log_voice([failed, {"model": "Gemini (backup)", "error": "unavailable"}],
                       "speech to text failed; the volunteer was asked to type the story")
            raise
        _log_voice([failed], f"speech to text by the backup ({backup.model})")
        return SpokenText(backup.text, backup.removed, backup.model, backup=True)
    if bhashini.configured():
        rate = _wav_rate(audio)
        if rate and bhashini.supports("asr", language):
            result = bhashini.speech_to_text(audio, language, "wav", rate)
            return SpokenText(result.text, result.removed, "Bhashini")
    # Hinglish: written down in Roman letters as spoken; other languages: "write it in its own script"
    script = "en" if language == HINGLISH else language if language in DIRECT else "other"
    result = llm.transcribe(audio, mime_type, script=script)
    return SpokenText(result.text, result.removed, result.model)


# ---------- legal text: a reading copy only ----------

import re as _re
from typing import List as _List

READING_COPY_LABEL = "Machine translated, not checked. Rely on the English or Hindi version."
KEEP_IN_ENGLISH = _re.compile(r"^\s*(?:Source|Link|Also|Checked):|^DRAFT — to be checked by a lawyer$|https?://")


def numbers_in(text: str) -> _List[str]:
    """Section numbers, dates and amounts as they appear: '479(2)', '2024', '40,000' (any script's digits)."""
    return sorted(_re.findall(r"\d+(?:\(\w+\))*(?:,\d+)*", privacy.normalise_digits(text)))


@dataclass
class ReadingCopy:
    text: str
    kept_in_english: int  # paragraphs kept in English because a number, date or amount changed


def reading_copy(text: str, language: str, translate=None) -> ReadingCopy:
    """A machine-translated reading copy of legal text (a draft, a summary or a knowledge entry).

    Translated a paragraph at a time; lines with Source / Link / web addresses and the DRAFT line stay
    in English; any paragraph whose section numbers, dates or amounts change is kept in English.
    Never saved, never sent to the DLSA or a court."""
    translate = translate or bhashini.translate
    out, kept = [READING_COPY_LABEL], 0
    for paragraph in _re.split(r"\n\s*\n", text.strip()):
        lines = paragraph.split("\n")
        if all(KEEP_IN_ENGLISH.search(l) or not _re.search(r"[A-Za-z]", l) for l in lines):
            out.append(paragraph)
            continue
        translatable = [l for l in lines if not KEEP_IN_ENGLISH.search(l)]
        result = translate("\n".join(translatable), "en", language).text
        if numbers_in(result) != numbers_in("\n".join(translatable)):
            kept += 1
            out.append("[kept in English: a number, date or amount changed in translation]\n" + paragraph)
            continue
        translated = iter(result.split("\n")) if result.count("\n") == len(translatable) - 1 else None
        if translated is None:
            out.append(result + "\n" + "\n".join(l for l in lines if KEEP_IN_ENGLISH.search(l)))
        else:
            out.append("\n".join(l if KEEP_IN_ENGLISH.search(l) else next(translated) for l in lines))
    return ReadingCopy("\n\n".join(out), kept)


def _log_voice(attempts, outcome: str) -> None:
    """In the problems log: which voice service failed and why (no audio, no text)."""
    try:
        audit.log_ai_failure(attempts, outcome)
    except Exception:  # the log must never stop the volunteer
        pass
