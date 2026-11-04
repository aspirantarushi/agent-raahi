"""Every AI call in the app lives in this file, so the model can be swapped.

Provider: Google Gemini API (free tier). Model gemini-3.5-flash-lite (fast); if Google says
it is busy or it is too slow, the same request goes once to gemini-3.8-flash.
The key is read from the environment variable GEMINI_API_KEY, or from a .env file
in the project folder (kept out of git). It is never written in the code.

The AI only reads case notes and returns what they clearly say, with the exact words
it relied on. Plain code (intake.py) then checks every answer against the notes.
Dates, rules and drafts are never left to the AI.

Note: on Google's free tier, what is sent may be used to improve Google's products.
Personal numbers are removed before sending (privacy.redact), and volunteers are told
not to type names.
"""

import base64
import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import privacy

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODEL = "gemini-3.8-flash"  # used when the main model is busy or too slow
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 25
BUSY_CODES = {429, 500, 503, 504}  # worth trying the other model


class AIUnavailable(Exception):
    """The AI could not be used (no key, no internet, an error or an unreadable answer).
    The app then carries on with the normal form."""


# ---------- settings ----------

def _load_dotenv(path: Path = HERE / ".env") -> None:
    """Read KEY=value lines from .env into the environment (without overriding)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def api_key() -> Optional[str]:
    _load_dotenv()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key or None


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def models_to_try() -> list:
    """The main model, then the fallback (unless GEMINI_FALLBACK_MODEL is set to empty)."""
    fallback = os.environ.get("GEMINI_FALLBACK_MODEL", FALLBACK_MODEL).strip()
    models = [model_name()]
    if fallback and fallback not in models:
        models.append(fallback)
    return models


def available() -> bool:
    return api_key() is not None


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # comes with Streamlit; makes HTTPS work the same everywhere
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ---------- the one place that talks to the AI ----------

class _Busy(Exception):
    """The model was busy or too slow: try the next one."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _call_model(model: str, key: str, body: dict) -> dict:
    request = urllib.request.Request(
        API_URL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_ssl_context()) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        message = ""
        try:
            message = json.load(err).get("error", {}).get("message", "")
        except Exception:
            pass
        if err.code in BUSY_CODES:
            hint = ("the free-tier limit was reached; try again later" if err.code == 429
                    else "the AI service is busy; try again in a few minutes")
            raise _Busy(f"AI reading failed: {hint} (error {err.code}).") from None
        hint = {
            400: "the request was not accepted",
            401: "the API key was not accepted",
            403: "the API key was not accepted",
            404: f"the model '{model}' was not found",
        }.get(err.code, "the AI service had a problem")
        raise AIUnavailable(f"AI reading failed: {hint} (error {err.code}). {message}".strip()) from None
    except (TimeoutError, socket.timeout):
        raise _Busy("AI reading failed: the AI service took too long to answer; try again in a few minutes.") \
            from None
    except urllib.error.URLError as err:
        if isinstance(err.reason, (TimeoutError, socket.timeout)):
            raise _Busy("AI reading failed: the AI service took too long to answer; try again in a few minutes.") \
                from None
        raise AIUnavailable("AI reading failed: could not reach the AI service (check the internet).") from None
    except OSError:
        raise AIUnavailable("AI reading failed: could not reach the AI service (check the internet).") from None


def _generate_json(prompt: str, schema: dict, extra_parts: Optional[list] = None) -> Tuple[dict, str]:
    """Returns (the JSON answer, the model that gave it). extra_parts: e.g. an audio recording."""
    key = api_key()
    if not key:
        raise AIUnavailable("AI reading is not set up yet (no GEMINI_API_KEY).")
    body = {
        "contents": [{"role": "user", "parts": (extra_parts or []) + [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    last_busy = None
    for model in models_to_try():
        try:
            data = _call_model(model, key, body)
            used = model
            break
        except _Busy as busy:
            last_busy = busy
    else:
        raise AIUnavailable(last_busy.message)

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(text), used
    except (KeyError, IndexError, TypeError, ValueError):
        raise AIUnavailable("AI reading failed: the answer could not be read.") from None


# ---------- reading undertrial case notes ----------

_FIELD = {
    "type": "OBJECT",
    "properties": {
        "value": {"type": "STRING", "nullable": True},
        "quote": {"type": "STRING", "nullable": True},
    },
    "required": ["value", "quote"],
}

UNDERTRIAL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "custody_began": _FIELD,
        "offence_date": _FIELD,
        "today_date": _FIELD,
        "sections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "law": {"type": "STRING", "enum": ["IPC", "BNS"]},
                    "section": {"type": "STRING"},
                    "quote": {"type": "STRING"},
                },
                "required": ["law", "section", "quote"],
            },
        },
        "previously_convicted": _FIELD,
        "other_cases_pending": _FIELD,
        "delay_by_accused": _FIELD,
        "lawyer": _FIELD,
    },
    "required": ["custody_began", "offence_date", "today_date", "sections", "previously_convicted",
                 "other_cases_pending", "delay_by_accused", "lawyer"],
}

UNDERTRIAL_PROMPT = """You help legal aid volunteers in India fill in a form from case notes about an
undertrial prisoner. Read the notes and return only facts the notes state clearly.

Rules:
- Only extract facts stated in the notes. Never judge or predict bail chances, flight risk, the risk
  of re-offending, guilt, innocence or anyone's credibility, and never give an opinion or a score.
- The notes may be in English, Hindi (Devanagari script), Hinglish (Hindi written in Roman letters)
  or a mix. Read them all the same way. Copy every "quote" exactly as written, in the same script and
  spelling. "आईपीसी" or "IPC" means law "IPC"; "बीएनएस" or "BNS" means law "BNS".
- Never guess or work anything out. If a fact is not clearly stated, return null for both value and quote.
- For every value, "quote" must be the exact words copied from the notes that state it.
- Dates: return YYYY-MM-DD only when the notes give the day, month and year. If only a month or a
  year is given (for example "in February 2024"), return null for the value and put those words in quote.
- custody_began: the date of arrest or the date custody began.
- offence_date: the date the offence is said to have happened.
- today_date: only if the notes say what today's date is.
- sections: each IPC or BNS section the person is charged under, as written (for example law "IPC",
  section "380"). Return an empty list if none are named.
- previously_convicted: "no" if the notes say the person has never been convicted, "yes" if they say
  there is an earlier conviction, otherwise null.
- other_cases_pending: "no" if the notes say no other cases are pending, "yes" if they say other cases
  are pending, otherwise null.
- delay_by_accused: "no" if the notes say the accused has not caused any delay, "yes" if they say the
  accused caused delay, otherwise null.
- lawyer: exactly one of "Legal aid lawyer", "Private lawyer", "None", or null if the notes don't say.

Case notes:
<<<
{notes}
>>>"""


# Must appear in every prompt (checked by a test; whitespace ignored).
NO_JUDGEMENT_RULE = ("Never judge or predict bail chances, flight risk, the risk of re-offending, "
                     "guilt, innocence or anyone's credibility")


@dataclass
class NotesReading:
    answer: dict  # the AI's answer: check with intake.check_ai_answer before use
    notes_sent: str  # the notes after personal numbers were removed
    removed: Dict[str, int]  # what was removed, e.g. {"a phone number": 1}
    model: str  # the model that answered (named in the draft's AI disclosure)


def read_undertrial_notes(notes: str) -> NotesReading:
    """Send case notes to the AI. Phone numbers, Aadhaar numbers and email addresses
    are removed before sending."""
    clean, removed = privacy.redact(notes)
    if not clean.strip():
        raise AIUnavailable("There are no case notes to read.")
    answer, model = _generate_json(UNDERTRIAL_PROMPT.format(notes=clean), UNDERTRIAL_SCHEMA)
    if not isinstance(answer, dict):
        raise AIUnavailable("AI reading failed: the answer could not be read.")
    return NotesReading(answer=answer, notes_sent=clean, removed=removed, model=model)


# ---------- reading any case (general intake) ----------

_YES_NO = {
    "type": "OBJECT",
    "properties": {
        "value": {"type": "STRING", "enum": ["yes", "no", "unknown"]},
        "quote": {"type": "STRING", "nullable": True},
    },
    "required": ["value", "quote"],
}

GENERAL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "person_needing_help": {"type": "STRING"},  # a role, e.g. "the brother, who is in jail"
        "what_happened": {"type": "ARRAY", "items": {"type": "STRING"}},
        "timeline": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {"when": {"type": "STRING"}, "what": {"type": "STRING"}},
                      "required": ["when", "what"]},
        },
        "danger_now": _YES_NO,
        "in_custody": _YES_NO,
        "money_lost_online": _YES_NO,
        "money_lost_in_last_few_days": _YES_NO,
        "called_1930": _YES_NO,
        "coming_dates": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {"when": {"type": "STRING"}, "what": {"type": "STRING"},
                                     "quote": {"type": "STRING"}},
                      "required": ["when", "what", "quote"]},
        },
        "sections_charged": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {"law": {"type": "STRING", "enum": ["IPC", "BNS"]},
                                     "section": {"type": "STRING"}, "quote": {"type": "STRING"}},
                      "required": ["law", "section", "quote"]},
        },
        "issues": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {
                          "category": {"type": "STRING",
                                       "enum": ["arrest_or_custody", "online_or_financial_fraud", "other"]},
                          "name": {"type": "STRING"}},
                      "required": ["category", "name"]},
        },
        "documents_held": {"type": "ARRAY", "items": {"type": "STRING"}},
        "questions_to_ask": {"type": "ARRAY", "items": {"type": "STRING"}},
        "woman": _YES_NO,
        "under_18": _YES_NO,
        "sc_st": _YES_NO,
        "disability": _YES_NO,
        "state": {"type": "OBJECT",
                  "properties": {"value": {"type": "STRING", "nullable": True},
                                 "quote": {"type": "STRING", "nullable": True}},
                  "required": ["value", "quote"]},
        "income": {"type": "OBJECT",
                   "properties": {"amount": {"type": "NUMBER", "nullable": True},
                                  "per": {"type": "STRING", "enum": ["month", "year", "unknown"]},
                                  "quote": {"type": "STRING", "nullable": True}},
                   "required": ["amount", "per", "quote"]},
    },
    "required": ["person_needing_help", "what_happened", "timeline", "danger_now", "in_custody",
                 "money_lost_online", "money_lost_in_last_few_days", "called_1930", "coming_dates",
                 "sections_charged", "issues", "documents_held", "questions_to_ask", "woman", "under_18",
                 "sc_st", "disability", "state", "income"],
}

GENERAL_PROMPT = """You help legal aid volunteers in India write a short, factual summary of a person's
problem from the volunteer's notes. Read the notes and fill in the form.

Rules:
- Only extract facts stated in the notes. Never judge or predict bail chances, flight risk, the risk
  of re-offending, guilt, innocence or anyone's credibility, never predict the outcome of a case, and
  never give an opinion or a score.
- Describe people only by their role ("the employer", "the husband", "the sister", "the person
  seeking help"). Never write anyone's name, phone number, address or ID number.
- Never cite any law, Act, section, article, rule or court case. Name problems only in plain words,
  for example "unpaid wages", "domestic violence", "land dispute", "online fraud", "arrest and bail".
  The only exception is "sections_charged": copy any IPC or BNS section written in the notes, with the
  exact words.
- The notes may be in English, Hindi (Devanagari script), Hinglish (Hindi written in Roman letters)
  or a mix. Read them all the same way. Copy every "quote" exactly as written, in the same script and
  spelling. "आईपीसी" or "IPC" means law "IPC"; "बीएनएस" or "BNS" means law "BNS".
- Write person_needing_help, what_happened, timeline, issue names, documents_held and questions_to_ask
  in {output_language}.
- Never guess. If something is not clearly stated, use "unknown" (or null, or an empty list).
- For every yes/no answer and for state and income, "quote" must be the exact words copied from the
  notes that show it (null if unknown).
- what_happened: 2 to 6 short plain sentences. timeline: dates or times exactly as written in the notes.
- in_custody: "yes" only if the notes say someone is in jail or police custody now.
- money_lost_in_last_few_days: "yes" only if the notes say the money was lost within about the last
  7 days ("today", "yesterday", "two days ago"...).
- coming_dates: hearings, deadlines or other dates still to come, as written.
- issues: one entry per problem. category "arrest_or_custody" for arrest, jail or bail; category
  "online_or_financial_fraud" for money taken by online or payment fraud; otherwise "other".
- documents_held: papers or evidence the notes say the person already has.
- questions_to_ask: up to 5 short questions the volunteer should still ask, most important first.
  Never ask for names, phone numbers, Aadhaar numbers, addresses or ID numbers.
- woman, under_18, sc_st, disability, state, income: about the person needing legal help (not the
  person telling the story). income: the amount and whether it is per month or per year, as written;
  do not convert it.

Volunteer's notes:
<<<
{notes}
>>>"""


OUTPUT_LANGUAGES = {"en": "English", "hi": "simple everyday Hindi (Devanagari script)"}


def read_general_notes(notes: str, output_lang: str = "en") -> NotesReading:
    """Send a story to the AI for a structured summary. Phone numbers, Aadhaar numbers and email
    addresses are removed before sending. Check the answer with general.check_general_answer."""
    clean, removed = privacy.redact(notes)
    if not clean.strip():
        raise AIUnavailable("There are no case notes to read.")
    answer, model = _generate_json(GENERAL_PROMPT.format(notes=clean, output_language=OUTPUT_LANGUAGES.get(
        output_lang, "English")), GENERAL_SCHEMA)
    if not isinstance(answer, dict):
        raise AIUnavailable("AI reading failed: the answer could not be read.")
    return NotesReading(answer=answer, notes_sent=clean, removed=removed, model=model)


# ---------- voice: turning a recording into text ----------

MAX_AUDIO_BYTES = 15 * 1024 * 1024
TRANSCRIBE_SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}
TRANSCRIBE_PROMPT = """Write down what is said in this recording, word for word, in the language it is
spoken: Hindi in Devanagari script, Hinglish in Roman letters, English in English. Do not translate,
summarise, explain or add anything. Never write a phone number, Aadhaar number or email address:
write [number removed] instead. Replace any person's name with [name]. If nothing can be heard,
return an empty text."""


@dataclass
class Transcript:
    text: str                 # already through the privacy filter
    removed: Dict[str, int]
    model: str


def transcribe(audio: bytes, mime_type: str = "audio/wav") -> Transcript:
    """Send a recording to Gemini only to turn it into text. The recording is not saved anywhere;
    the text goes through the same privacy filter as typed notes."""
    if not audio:
        raise AIUnavailable("The recording is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise AIUnavailable("The recording is too long. Please record a shorter part of the story.")
    part = {"inline_data": {"mime_type": mime_type or "audio/wav",
                            "data": base64.b64encode(audio).decode("ascii")}}
    answer, model = _generate_json(TRANSCRIBE_PROMPT, TRANSCRIBE_SCHEMA, extra_parts=[part])
    text = answer.get("text", "") if isinstance(answer, dict) else ""
    if not isinstance(text, str):
        raise AIUnavailable("AI reading failed: the answer could not be read.")
    clean, removed = privacy.redact(text.strip())
    return Transcript(text=clean, removed=removed, model=model)
