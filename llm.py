"""Every AI call in the app lives in this file, so the model can be swapped.

Provider: Google Gemini API (free tier). Model gemini-3.8-flash; if Google says it is
busy or it is too slow, the same request goes once to gemini-3.5-flash-lite.
The key is read from the environment variable GEMINI_API_KEY, or from a .env file
in the project folder (kept out of git). It is never written in the code.

The AI only reads case notes and returns what they clearly say, with the exact words
it relied on. Plain code (intake.py) then checks every answer against the notes.
Dates, rules and drafts are never left to the AI.

Note: on Google's free tier, what is sent may be used to improve Google's products.
Personal numbers are removed before sending (privacy.redact), and volunteers are told
not to type names.
"""

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

import privacy

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"  # used when the main model is busy or too slow
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


def _generate_json(prompt: str, schema: dict) -> dict:
    key = api_key()
    if not key:
        raise AIUnavailable("AI reading is not set up yet (no GEMINI_API_KEY).")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
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
            break
        except _Busy as busy:
            last_busy = busy
    else:
        raise AIUnavailable(last_busy.message)

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(text)
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


def read_undertrial_notes(notes: str) -> Tuple[dict, str, Dict[str, int]]:
    """Send case notes to the AI and return (its answer, the notes as sent, what was removed).

    Phone numbers, Aadhaar numbers and email addresses are removed before sending.
    The answer must still be checked by intake.check_ai_answer before use.
    """
    clean, removed = privacy.redact(notes)
    if not clean.strip():
        raise AIUnavailable("There are no case notes to read.")
    answer = _generate_json(UNDERTRIAL_PROMPT.format(notes=clean), UNDERTRIAL_SCHEMA)
    if not isinstance(answer, dict):
        raise AIUnavailable("AI reading failed: the answer could not be read.")
    return answer, clean, removed
