"""Every AI call in the app lives in this file, so the model can be swapped.

Provider: Google Gemini API (free tier). Model gemini-3.5-flash-lite (fast). If Google says it is
busy (503, 500, 504), a per-minute limit is reached (429) or it is too slow, the request is tried
again after 2, 4 and 8 seconds, then once with the backup model gemini-3.8-flash. A DAILY limit
(429 with a per-day quota) is not retried: waiting seconds can't help, so the backup is tried at once.
For READING STORIES only (undertrial notes and any-case stories), Groq is a third, free backup after
both Gemini models (GROQ_API_KEY; model openai/gpt-oss-120b, changeable with GROQ_MODEL). Voice and
"Research this issue" stay on Gemini (research needs Google Search). The same filter runs first.
If it still fails, the app says "The AI is busy; continue with the form" and the form opens.
Every failure is written to the problems log: time, error type and model (never case text).
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
import re
import socket
import ssl
import time
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
BUSY_CODES = {429, 500, 503, 504}  # worth trying again
RETRY_WAITS = (2, 4, 8)            # seconds to wait before each new try of the main model
BUSY_MESSAGE = "The AI is busy; continue with the form."
_sleep = time.sleep                # tests replace this, so they never wait

# Error types written to the problems log
BUSY, LIMIT, DAILY_LIMIT, TIMEOUT, NETWORK, KEY, NOT_FOUND, REFUSED, UNREADABLE = (
    "busy (503/500/504)", "limit reached (429)", "daily limit reached (429)", "timeout", "no internet",
    "key not accepted", "model not found", "request not accepted", "answer unreadable")


class AIUnavailable(Exception):
    """The AI could not be used (no key, no internet, an error or an unreadable answer).
    The app then carries on with the normal form. busy: True when the AI was busy, limited or slow
    (the friendly "continue with the form" case)."""

    def __init__(self, message: str, busy: bool = False):
        super().__init__(message)
        self.busy = busy


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
    """Reading stories works with either key (Gemini, or Groq as the backup)."""
    return api_key() is not None or groq_key() is not None


def gemini_available() -> bool:
    """Voice and research need Gemini itself."""
    return api_key() is not None


# ---------- Groq: the free backup for reading stories ----------

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"  # production model, strict JSON schema, free tier (Groq docs, Nov 2026)
GROQ_PREFIX = "groq:"                       # how the model is named in drafts and audit records
STRICT_SCHEMA_MODELS = ("openai/gpt-oss", "qwen/")


def groq_key() -> Optional[str]:
    _load_dotenv()
    key = os.environ.get("GROQ_API_KEY", "").strip()
    return key or None


def groq_model() -> str:
    return os.environ.get("GROQ_MODEL", "").strip() or GROQ_DEFAULT_MODEL


def json_schema(schema: dict) -> dict:
    """A Gemini response schema as a strict JSON Schema (for Groq): lower-case types, nullable as
    [type, "null"], every property required, no extra properties."""
    kind = str(schema.get("type", "string")).lower()
    if kind == "object":
        props = {k: json_schema(v) for k, v in schema.get("properties", {}).items()}
        out = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    elif kind == "array":
        out = {"type": "array", "items": json_schema(schema.get("items", {"type": "STRING"}))}
    else:
        out = {"type": kind}
        if "enum" in schema:
            out["enum"] = list(schema["enum"])
    if schema.get("nullable"):
        out["type"] = [out["type"], "null"]
        if "enum" in out:
            out["enum"] = out["enum"] + [None]
    return out


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # comes with Streamlit; makes HTTPS work the same everywhere
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ---------- the one place that talks to the AI ----------

class _Busy(Exception):
    """The model was busy, limited or too slow: worth trying again."""

    def __init__(self, message: str, kind: str = BUSY, code: Optional[int] = None):
        super().__init__(message)
        self.message, self.kind, self.code = message, kind, code


class _Failed(AIUnavailable):
    """Not worth trying again (bad key, unknown model, no internet), with its error type for the log."""

    def __init__(self, message: str, kind: str, code: Optional[int] = None):
        super().__init__(message)
        self.kind, self.code = kind, code


def _is_daily(error: dict) -> bool:
    """A 429 whose quota is per day (free tier): waiting seconds won't help."""
    for detail in error.get("details", []) or []:
        for v in detail.get("violations", []) or []:
            if "PerDay" in str(v.get("quotaId", "")):
                return True
    return False


def _call_model(model: str, key: str, body: dict) -> dict:
    return _post(API_URL.format(model=model), {"x-goog-api-key": key}, body, model)


def _call_groq(model: str, key: str, prompt: str, schema: dict) -> dict:
    """One Groq request. Returns the parsed JSON answer."""
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": "Answer only with JSON that matches the given schema."},
                         {"role": "user", "content": prompt}]}
    if model.startswith(STRICT_SCHEMA_MODELS):
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "answer", "strict": True, "schema": json_schema(schema)}}
    else:  # other models: JSON mode, with the schema written into the request
        body["response_format"] = {"type": "json_object"}
        body["messages"][1]["content"] += "\n\nReply with JSON matching this schema:\n" + json.dumps(json_schema(schema))
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # faster; the checks in plain code do the rest
    data = _post(GROQ_URL, {"Authorization": f"Bearer {key}"}, body, model)
    try:
        return json.loads(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise _Failed("AI reading failed: the answer could not be read.", UNREADABLE) from None


def _post(url: str, auth: dict, body: dict, model: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "AgentRaahi/1.0", **auth},
        method="POST",
    )
    slow = "AI reading failed: the AI service took too long to answer; try again in a few minutes."
    offline = "AI reading failed: could not reach the AI service (check the internet)."
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_ssl_context()) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        error = {}
        try:
            error = json.load(err).get("error", {}) or {}
        except Exception:
            pass
        message = error.get("message", "")
        if err.code in BUSY_CODES:
            if err.code == 429:
                kind = DAILY_LIMIT if _is_daily(error) else LIMIT
                hint = "the free-tier limit was reached; try again later"
            else:
                kind, hint = BUSY, "the AI service is busy; try again in a few minutes"
            raise _Busy(f"AI reading failed: {hint} (error {err.code}).", kind, err.code) from None
        kind, hint = {
            400: (REFUSED, "the request was not accepted"),
            401: (KEY, "the API key was not accepted"),
            403: (KEY, "the API key was not accepted"),
            404: (NOT_FOUND, f"the model '{model}' was not found"),
        }.get(err.code, (f"error {err.code}", "the AI service had a problem"))
        raise _Failed(f"AI reading failed: {hint} (error {err.code}). {message}".strip(), kind, err.code) from None
    except (TimeoutError, socket.timeout):
        raise _Busy(slow, TIMEOUT) from None
    except urllib.error.URLError as err:
        if isinstance(err.reason, (TimeoutError, socket.timeout)):
            raise _Busy(slow, TIMEOUT) from None
        raise _Failed(offline, NETWORK) from None
    except OSError:
        raise _Failed(offline, NETWORK) from None


def record_failures(attempts: list, outcome: str) -> None:
    """Write the failed tries of one AI request to the problems log: time, error type, model, outcome.
    Never the case text. A storage problem never stops the app."""
    if not attempts:
        return
    try:
        import audit
        audit.log_ai_failure(attempts, outcome)
    except Exception:
        pass


def _plan():
    """(model, seconds to wait first) for each try: the main model now and after 2, 4 and 8 seconds,
    then the backup once."""
    models = models_to_try()
    tries = [(models[0], 0)] + [(models[0], w) for w in RETRY_WAITS]
    return tries + [(m, 0) for m in models[1:]]


def _generate_json(prompt: str, schema: dict, extra_parts: Optional[list] = None,
                   groq: bool = False) -> Tuple[dict, str]:
    """Returns (the JSON answer, the model that gave it). extra_parts: e.g. an audio recording.
    groq: also try Groq after both Gemini models (only for reading stories; never with a recording)."""
    body = {
        "contents": [{"role": "user", "parts": (extra_parts or []) + [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    fallback = None
    if groq and not extra_parts and groq_key():
        model = groq_model()
        fallback = (GROQ_PREFIX + model, lambda: _call_groq(model, groq_key(), prompt, schema))
    data, used = _generate(body, fallback)
    if used.startswith(GROQ_PREFIX):
        if not isinstance(data, dict):
            raise AIUnavailable("AI reading failed: the answer could not be read.")
        return data, used
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(text), used
    except (KeyError, IndexError, TypeError, ValueError):
        record_failures([{"model": used, "error": UNREADABLE, "code": None}], "gave up: the form opened instead")
        raise AIUnavailable("AI reading failed: the answer could not be read.") from None


def _generate(body: dict, fallback=None) -> Tuple[dict, str]:
    """Send a request with the retries (2, 4, 8 s, then the backup model), then the fallback if given
    (("groq:<model>", call) for reading stories). Returns (answer, model)."""
    key = api_key()
    if not key and not fallback:
        raise AIUnavailable("AI reading is not set up yet (no GEMINI_API_KEY).")
    attempts, used, data, failed_hard = [], None, None, None
    skip_model = None  # a model whose daily limit is used up: no more tries of it
    for model, wait in (_plan() if key else []):
        if model == skip_model:
            continue
        if wait:
            _sleep(wait)
        try:
            data = _call_model(model, key, body)
            used = model
            break
        except _Busy as busy:
            attempts.append({"model": model, "error": busy.kind, "code": busy.code})
            if busy.kind == DAILY_LIMIT:
                skip_model = model
        except _Failed as failed:
            attempts.append({"model": model, "error": failed.kind, "code": failed.code})
            failed_hard = failed
            break  # a bad key or no internet: more Gemini tries won't help
    if used is None and fallback:
        name, call = fallback
        try:
            data, used = call(), name
            failed_hard = None
        except _Busy as busy:
            attempts.append({"model": name, "error": busy.kind, "code": busy.code})
        except _Failed as failed:
            attempts.append({"model": name, "error": failed.kind, "code": failed.code})
            failed_hard = failed_hard or failed
    if used is None:
        if failed_hard is not None and not fallback:
            record_failures(attempts, "gave up: the form opened instead")
            raise failed_hard
        record_failures(attempts, "gave up after every try: the form opened instead")
        raise AIUnavailable(BUSY_MESSAGE, busy=True)
    record_failures(attempts, f"answered by {used} after {len(attempts)} failed tries")
    return data, used


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
    answer, model = _generate_json(UNDERTRIAL_PROMPT.format(notes=clean), UNDERTRIAL_SCHEMA, groq=True)
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
                                       "enum": ["arrest_or_custody", "online_or_financial_fraud",
                                                "electricity_or_water", "wages_or_work", "ration_or_welfare",
                                                "other"]},
                          "name": {"type": "STRING"}},
                      "required": ["category", "name"]},
        },
        "documents_held": {"type": "ARRAY", "items": {"type": "STRING"}},
        "questions_to_ask": {"type": "ARRAY", "items": {"type": "STRING"}},
        "why_asked": {"type": "ARRAY", "items": {"type": "STRING"}},
        "payment_demand_meaning": {"type": "STRING", "nullable": True},
        "outcome_wanted": {"type": "OBJECT",
                           "properties": {"value": {"type": "STRING", "nullable": True},
                                          "quote": {"type": "STRING", "nullable": True}},
                           "required": ["value", "quote"]},
        "woman": _YES_NO,
        "under_18": _YES_NO,
        "sc_st": _YES_NO,
        "disability": _YES_NO,
        "essential_service_cut": _YES_NO,
        "unofficial_payment_demand": _YES_NO,
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
                 "sections_charged", "issues", "documents_held", "questions_to_ask", "why_asked", "outcome_wanted",
                 "essential_service_cut", "unofficial_payment_demand", "woman", "under_18",
                 "sc_st", "disability", "state", "income"],
}

GENERAL_PROMPT = """You help legal aid volunteers in India write a short, factual summary of a person's
problem from the volunteer's notes. Read the notes and fill in the form.

Rules:
- Only extract facts stated in the notes. Never judge or predict bail chances, flight risk, the risk
  of re-offending, guilt, innocence or anyone's credibility, never predict the outcome of a case, and
  never give an opinion or a score.
- Describe people only by their role ("the employer", "the husband", "the sister", "the person"). Never write anyone's name, phone number, address or ID number.
- Never cite any law, Act, section, article, rule or court case. Name problems only in plain words,
  for example "unpaid wages", "domestic violence", "land dispute", "online fraud", "arrest and bail".
  The only exception is "sections_charged": copy any IPC or BNS section written in the notes, with the
  exact words.
- The notes may be in English, Hindi (Devanagari script), Hinglish (Hindi written in Roman letters)
  or a mix. Read them all the same way. Copy every "quote" exactly as written, in the same script and
  spelling. "आईपीसी" or "IPC" means law "IPC"; "बीएनएस" or "BNS" means law "BNS".
- Write person_needing_help, what_happened, timeline, issue names, documents_held, questions_to_ask and
  why_asked in {output_language}. Every "quote" must still be copied word for word from the notes, in the notes'
  own script and spelling: never translate or transliterate a quote.
- Never guess. If something is not clearly stated, use "unknown" (or null, or an empty list).
- For every yes/no answer and for state and income, "quote" must be the exact words copied from the
  notes that show it (null if unknown).
- what_happened: 2 to 6 short plain sentences. timeline: dates or times exactly as written in the notes.
- In what_happened, timeline and documents_held keep every amount of money, count, age, place (district,
  village) and date exactly as the notes give them ("Rs 14,000", "twice", "62-year-old", "Gaya district,
  Bihar", "1 October 2026"); never replace them with general words ("an amount", "money", "a place").
- Refer to the person who needs help as "the person" or by their role ("the widow", "the worker"), never
  as "the person needing help".
- in_custody: "yes" only if the notes say someone is in jail or police custody now.
- money_lost_in_last_few_days: "yes" only if the notes say the money was lost within about the last
  7 days ("today", "yesterday", "two days ago"...).
- coming_dates: hearings, deadlines or other dates still to come, as written.
- issues: one entry per problem. category "arrest_or_custody" for arrest, jail or bail; category
  "online_or_financial_fraud" for money taken by online or payment fraud; "electricity_or_water" for an
  electricity or water connection or bill; "wages_or_work" for unpaid wages or work problems;
  "ration_or_welfare" for a ration card, pension or other government scheme; otherwise "other".
- person_needing_help: the role of the person who needs the help, as the notes describe them (for
  example "the speaker's husband, a labourer"); "unknown" if the notes don't say who it is.
- essential_service_cut: "yes" only if the notes say the person's electricity or water is cut off now.
- unofficial_payment_demand: "yes" only if the notes say someone asked for an unofficial payment, a
  bribe, "kharcha-pani" or similar to do their work. Copy the exact words as quote. Never judge anyone.
- Never write any ID number, consumer number or account number: leave such numbers out.
- documents_held: papers or evidence the notes say the person already has.
- questions_to_ask: up to 5 short questions the volunteer should still ask, most important first.
  Never ask about anything the notes already answer. Ask what the person wants to happen (the outcome
  they hope for) if the notes don't say it; for any date without a year, ask for the full date; ask the
  person's age if it is not stated and they might be under 18 (children get free legal aid whatever the
  income). Never ask for names, phone numbers, Aadhaar numbers, addresses or ID numbers.
  Never ask anything the notes already answer, even with "no" (if the notes say "no written contract",
  don't ask about a contract). The volunteer fills the answers in: always say "the person" (or their
  role), never "you". Never ask whether an unofficial payment demand should be paid, reduced, waived or
  negotiated: such a demand is only recorded for the lawyer.
- why_asked: for each question in questions_to_ask, in the same order, one short plain sentence saying
  what the letter or the application needs the answer for (for example "The letter must say when the
  wages stopped."). Never include anyone's name. Never mention the strength of evidence, chances,
  winning, the other side, or anyone's credibility.
- outcome_wanted: what the person wants to happen, only if the notes say it; otherwise null. value: YOUR
  OWN plain words in {output_language} (translate it: never copy the notes' Hindi or Hinglish words into
  value). quote: the exact words from the notes.
- payment_demand_meaning: only if unofficial_payment_demand is "yes": what the demand was, in plain
  English (for example "Rs 2,000 to reconnect the electricity"); otherwise null. No names.
- woman, under_18, sc_st, disability, state, income: about the person needing legal help (not the
  person telling the story). income: the amount and whether it is per month or per year, as written;
  do not convert it. income is what the person earns now; wages or money owed to them (unpaid salary)
  are not income: leave income null then.

Volunteer's notes:
<<<
{notes}
>>>"""


OUTPUT_LANGUAGES = {"en": "English", "hi": "simple everyday Hindi (Devanagari script)"}


KNOWN_FACTS_NOTE = """
Facts already known from earlier visits (do not ask about these again in questions_to_ask; only extract
them if these notes state them):
{known}
"""


def read_general_notes(notes: str, output_lang: str = "en", known: Optional[Dict[str, object]] = None) -> NotesReading:
    """Send a story to the AI for a structured summary. Phone numbers, Aadhaar numbers and email
    addresses are removed before sending. Check the answer with general.check_general_answer.
    known: facts already in the case file (from the tracker), so the AI doesn't ask for them again."""
    clean, removed = privacy.redact(notes)
    if not clean.strip():
        raise AIUnavailable("There are no case notes to read.")
    prompt = GENERAL_PROMPT.format(notes=clean, output_language=OUTPUT_LANGUAGES.get(output_lang, "English"))
    if known:
        listed = "\n".join(f"- {fact}: {value}" for fact, value in known.items())
        prompt += KNOWN_FACTS_NOTE.format(known=privacy.redact(listed)[0])
    answer, model = _generate_json(prompt, GENERAL_SCHEMA, groq=True)
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


SCRIPT_HINTS = {
    "hi": "Write Hindi speech in Devanagari script (for example: \"मेरे भाई को गिरफ़्तार किया गया\"), "
          "keep English words in English, and write numbers and dates in digits.",
    "en": "Write Hindi or Hinglish speech in Roman letters as it is spoken, English in English, and numbers "
          "and dates in digits.",
    "other": "Write each language in its own usual script (for example Tamil in Tamil script, Bengali in "
             "Bengali script), English in English, and numbers and dates in digits.",
}


def transcribe(audio: bytes, mime_type: str = "audio/wav", script: str = "en") -> Transcript:
    """Send a recording to Gemini only to turn it into text. The recording is not saved anywhere;
    the text goes through the same privacy filter as typed notes."""
    if not audio:
        raise AIUnavailable("The recording is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise AIUnavailable("The recording is too long. Please record a shorter part of the story.")
    part = {"inline_data": {"mime_type": mime_type or "audio/wav",
                            "data": base64.b64encode(audio).decode("ascii")}}
    prompt = TRANSCRIBE_PROMPT + "\n" + SCRIPT_HINTS.get(script, SCRIPT_HINTS["other"])
    answer, model = _generate_json(prompt, TRANSCRIBE_SCHEMA, extra_parts=[part])
    text = answer.get("text", "") if isinstance(answer, dict) else ""
    if not isinstance(text, str):
        raise AIUnavailable("AI reading failed: the answer could not be read.")
    clean, removed = privacy.redact(text.strip())
    return Transcript(text=clean, removed=removed, model=model)


# ---------- "Research this issue": web search with Google Search grounding ----------
# Only the state and the issue in plain words are sent (never names or personal numbers). The AI
# writes a brief; research.py (plain code) keeps only points backed by an official link that Google
# Search actually returned. Nothing reaches a case until the supervisor approves it.

RESEARCH_PROMPT = """You help a free legal aid clinic in India. A volunteer has a problem that the clinic's
own files do not cover. Use Google Search to find OFFICIAL information for this state.

State: {state}
Problem, in plain words: {issue}
If the problem names its current law, search for official pages about that law first (for example the state's
rules or Labour Department pages under the Code on Wages, 2019), not pages about the law it replaced.
Today's date: {today}. Use only the law in force today. The Indian Penal Code, the Code of Criminal Procedure
and the Indian Evidence Act were replaced on 1 July 2024 (by the BNS, the BNSS and the BSA), and 29 central labour
Acts (for example the Payment of Wages Act and the Minimum Wages Act) were replaced on 21 November 2025 by the four
labour codes: name the current law, never a replaced one.

Write a short research brief in plain English, with these headings:
1. Routes: who the person can complain to or apply to, in order (first the office or officer concerned,
   then any grievance cell, ombudsman, regulator, commission or court), with the name of the office.
2. Documents usually needed.
3. Time limits, if any (only if an official source states them).
4. Where and how to file (office, online portal or address of the office, fee if any).
5. Draft letter: a short application or complaint letter to the first office in the routes. Use blanks
   in square brackets for every personal detail the letter needs, such as [Name], [Address], [Date],
   [Signature], and a reference number blank only if this kind of problem has one (for example a
   consumer number for electricity). Never invent a name, number or address.

Rules:
- Use only official sources: Indian central or state government websites (gov.in, nic.in), India Code,
  state regulators and commissions, courts, NALSA and state or district legal services authorities.
- Write every point as a short factual sentence that the source states. If official information is
  not found for a heading, write "Not found in official sources."
- Never predict the outcome, the chances of success, how long it will take or what the authority will
  decide. Never promise anything. Never give an opinion about anyone.
"""

SPLIT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "points": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "kind": {"type": "STRING", "enum": ["route", "documents", "time_limit", "how_to_file", "letter"]},
                    "text": {"type": "STRING"},
                    "quote": {"type": "STRING"},
                },
                "required": ["kind", "text", "quote"],
            },
        },
    },
    "required": ["points"],
}

SPLIT_PROMPT = """Split this research brief into separate points. For each point give:
- kind: "route" (who to complain or apply to; keep the order of the brief), "documents", "time_limit",
  "how_to_file" or "letter" (the whole draft letter as ONE point);
- text: the point in one or two short plain sentences (for the letter: the letter itself, unchanged);
- quote: the exact sentence or sentences copied word for word from the brief that the point comes from.
Leave out headings, anything that says "Not found in official sources", and anything that predicts an
outcome or gives an opinion. Do not add anything that is not in the brief.

Brief:
<<<
{brief}
>>>"""


@dataclass
class ResearchRaw:
    brief: str           # the grounded brief, as written by the AI
    sources: list        # [{"uri", "title"}] from Google Search (groundingChunks), in order
    supports: list       # [{"text", "sources": [index, ...]}] which search results back which words
    queries: list        # the searches Google ran
    model: str
    sent: str            # exactly what was sent (state and issue), for the audit record


def _today() -> str:
    from datetime import date
    return f"{date.today():%d %B %Y}"


def research_issue(state: str, issue: str) -> ResearchRaw:
    """Research with Google Search grounding. Phone, Aadhaar and email numbers are removed first."""
    state, _ = privacy.redact((state or "").strip()[:60])
    issue, _ = privacy.redact((issue or "").strip()[:300])
    if not issue.strip() or not state.strip():
        raise AIUnavailable("Research needs the state and the problem in plain words.")
    prompt = RESEARCH_PROMPT.format(state=state, issue=issue, today=_today())
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}], "generationConfig": {"temperature": 0}}
    data, model = _generate(body)
    try:
        candidate = data["candidates"][0]
        brief = "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
        meta = candidate.get("groundingMetadata") or {}
    except (KeyError, IndexError, TypeError):
        raise AIUnavailable("Research failed: the answer could not be read.") from None
    sources = [{"uri": (c.get("web") or {}).get("uri", ""), "title": (c.get("web") or {}).get("title", "")}
               for c in meta.get("groundingChunks", []) or []]
    supports = [{"text": (s.get("segment") or {}).get("text", ""), "sources": list(s.get("groundingChunkIndices", []))}
                for s in meta.get("groundingSupports", []) or []]
    if not brief.strip() or not sources:
        raise AIUnavailable("Research failed: no search results came back.")
    return ResearchRaw(brief, sources, supports, list(meta.get("webSearchQueries", []) or []), model,
                       f"State: {state}. Problem: {issue}")


def split_brief(brief: str) -> Tuple[list, str]:
    """The brief as separate points [{"kind", "text", "quote"}] (no new facts, no links).
    Groq may do this when Gemini is busy: it only splits text that is already there."""
    answer, model = _generate_json(SPLIT_PROMPT.format(brief=brief), SPLIT_SCHEMA, groq=True)
    points = answer.get("points") if isinstance(answer, dict) else None
    if not isinstance(points, list):
        raise AIUnavailable("Research failed: the answer could not be read.")
    return points, model


# ---------- research backup: Tavily search on official sites, then a brief from those results only ----------
# Used when Gemini with Google Search fails or its daily limit is reached. Tavily searches only the
# official-site list (official.py); Gemini (or Groq if Gemini is busy) then writes the brief ONLY from
# those numbered results, naming the result numbers for every sentence. research.py then applies the
# same checks as before: links only from these results, official sites only, every point cited.

TAVILY_URL = "https://api.tavily.com/search"
TAVILY_LABEL = "Tavily search (official sites only)"
GOOGLE_LABEL = "Gemini with Google Search"


def tavily_key() -> Optional[str]:
    _load_dotenv()
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    return key or None


def tavily_search(query: str, domains: list, max_results: int = 8) -> list:
    """[{"url", "title", "content"}] from Tavily, limited to these domains. The key goes only in the header."""
    key = tavily_key()
    if not key:
        raise AIUnavailable("Tavily is not set up (no TAVILY_API_KEY).")
    body = {"query": query, "max_results": max_results, "search_depth": "advanced", "include_domains": list(domains),
            "include_answer": False}
    data = _post(TAVILY_URL, {"Authorization": f"Bearer {key}"}, body, "tavily")
    return [{"url": str(r.get("url", "")), "title": str(r.get("title", ""))[:200], "content": str(r.get("content", ""))[:3000]}
            for r in (data.get("results") or []) if isinstance(r, dict)]


BRIEF_SCHEMA = {
    "type": "OBJECT",
    "properties": {"sentences": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "text": {"type": "STRING"}, "sources": {"type": "ARRAY", "items": {"type": "INTEGER"}}},
        "required": ["text", "sources"]}}},
    "required": ["sentences"],
}

BRIEF_FROM_RESULTS_PROMPT = """You help a free legal aid clinic in India. Write a short research brief for this state and
problem using ONLY the numbered official search results below. Do not use anything else you know.

State: {state}
Problem, in plain words: {issue}
Today's date: {today}. Use only the law in force today (the IPC, CrPC and Evidence Act were replaced on 1 July
2024; 29 central labour Acts were replaced by the four labour codes on 21 November 2025): never a replaced law.

Cover, if the results say it: 1. Routes: who the person can complain or apply to, in order. 2. Documents usually
needed. 3. Time limits. 4. Where and how to file. 5. A short draft letter to the first office, with blanks in square
brackets for the personal details the letter needs ([Name], [Address], [Date], [Signature]; a reference number
blank only if this kind of problem has one).
Return the brief as sentences. For every sentence give "sources": the numbers of the results it comes from. A
sentence that no result supports must not be written. Never predict outcomes or chances, never promise anything,
and never give an opinion about anyone. Write "Not found in official sources." (with no sources) for a heading
the results don't cover.

Search results:
{results}"""


def research_issue_tavily(state: str, issue: str) -> "ResearchRaw":
    """The research backup. Only the state and the issue in plain words are sent (numbers removed)."""
    import official
    state, _ = privacy.redact((state or "").strip()[:60])
    issue, _ = privacy.redact((issue or "").strip()[:300])
    if not issue.strip() or not state.strip():
        raise AIUnavailable("Research needs the state and the problem in plain words.")
    domains = list(official.ALLOWED_SUFFIXES) + list(official.ALLOWED_HOSTS)
    results = [r for r in tavily_search(f"{issue} {state} complaint procedure official", domains)
               if official.allowed_link(r["url"])]
    if not results:
        raise AIUnavailable("Research failed: no official search results came back.")
    listed = "\n\n".join(f"[{n}] {r['title']} ({r['url']})\n{r['content']}" for n, r in enumerate(results, 1))
    answer, model = _generate_json(BRIEF_FROM_RESULTS_PROMPT.format(state=state, issue=issue, results=listed,
                                                                    today=_today()),
                                   BRIEF_SCHEMA, groq=True)
    sentences = [s for s in (answer.get("sentences") if isinstance(answer, dict) else []) or []
                 if isinstance(s, dict) and str(s.get("text", "")).strip()]
    if not sentences:
        raise AIUnavailable("Research failed: the answer could not be read.")
    brief = "\n".join(str(s["text"]).strip() for s in sentences)
    supports = [{"text": str(s["text"]).strip(),
                 "sources": [n - 1 for n in s.get("sources", []) if isinstance(n, int) and 1 <= n <= len(results)]}
                for s in sentences]
    return ResearchRaw(brief, [{"uri": r["url"], "title": r["title"]} for r in results], supports, [], 
                       f"{TAVILY_LABEL}; brief by {model}", f"State: {state}. Problem: {issue}")


def display_model(raw: Optional[str]) -> str:
    """The model's name as people read it: "groq:openai/gpt-oss-120b" -> "Groq (gpt-oss-120b)",
    "gemini-3.5-flash-lite" -> "Google Gemini". The raw id stays in the audit record and the CSV."""
    if not raw:
        return ""
    parts = []
    for one in re.split(r"\s*(?:\+|,| and )\s*", str(raw)):
        low = one.casefold()
        if low.startswith("groq:") or "groq" in low:
            name = one.split(":", 1)[-1].split("/")[-1] or "Groq"
            parts.append(f"Groq ({name})")
        elif "gemini" in low:
            parts.append("Google Gemini")
        elif "tavily" in low:
            parts.append("Tavily search (official sites only)")
        elif one:
            parts.append(one)
    return " + ".join(dict.fromkeys(parts))

