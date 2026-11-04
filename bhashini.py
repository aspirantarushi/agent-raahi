"""Every call to Bhashini (MeitY's language platform) lives in this file: translation and speech-to-text.

How the API works (from the official docs, https://dibd-bhashini.gitbook.io/bhashini-apis):
1. A "config" call to getModelsPipeline, with the headers userID and ulcaApiKey, says which service
   handles a task for a language, and returns the compute address (callbackUrl) and a key for it
   (inferenceApiKey name and value).
2. A "compute" call to that address does the work: translation (inputData.input[].source ->
   output[0].target) or speech-to-text (inputData.audio[].audioContent, base64 -> output[0].source).

Settings come from the environment or the .env file (kept out of git): BHASHINI_USER_ID and
BHASHINI_API_KEY. Register at https://dashboard.bhashini.co.in/user/register; after DIBD approves the
account, both are shown under "My Profile".

Rules kept here:
- Text goes through the privacy filter BEFORE it is sent (phone, Aadhaar, email in any script).
- Recordings are sent only to become text and are never saved.
- If Bhashini is not set up or fails, BhashiniUnavailable is raised and the app falls back to
  English and Hindi.
Note: Bhashini's docs say the free APIs are for proof-of-concept use; production use needs their
paid plan (contact the Bhashini team).
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import llm  # shared .env reader and HTTPS settings
import privacy

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
PIPELINE_ID = "64392f96daac500b55c543cd"  # "Initial Pipeline Models": ASR, translation, transliteration, TTS
TIMEOUT_SECONDS = 40
CONFIG_CACHE_SECONDS = 30 * 60
MAX_AUDIO_BYTES = 15 * 1024 * 1024

# The 22 languages of the Eighth Schedule: code -> (English name, name in its own script).
LANGUAGES: Dict[str, Tuple[str, str]] = {
    "as": ("Assamese", "অসমীয়া"), "bn": ("Bengali", "বাংলা"), "brx": ("Bodo", "बड़ो"),
    "doi": ("Dogri", "डोगरी"), "gu": ("Gujarati", "ગુજરાતી"), "hi": ("Hindi", "हिंदी"),
    "kn": ("Kannada", "ಕನ್ನಡ"), "ks": ("Kashmiri", "كٲشُر"), "gom": ("Konkani", "कोंकणी"),
    "mai": ("Maithili", "मैथिली"), "ml": ("Malayalam", "മലയാളം"), "mni": ("Manipuri", "ꯃꯤꯇꯩꯂꯣꯟ"),
    "mr": ("Marathi", "मराठी"), "ne": ("Nepali", "नेपाली"), "or": ("Odia", "ଓଡ଼ିଆ"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ"), "sa": ("Sanskrit", "संस्कृतम्"), "sat": ("Santali", "ᱥᱟᱱᱛᱟᱲᱤ"),
    "sd": ("Sindhi", "سنڌي"), "ta": ("Tamil", "தமிழ்"), "te": ("Telugu", "తెలుగు"), "ur": ("Urdu", "اردو"),
}


class Secret(str):
    """A key that never shows itself in error reports or logs (it is still sent as normal text)."""

    def __repr__(self) -> str:
        return "'***'"

    __str__ = __repr__


class BhashiniUnavailable(Exception):
    """Bhashini could not be used (not set up, no internet, language not supported, an error).
    The app then falls back to English and Hindi."""


@dataclass
class Endpoint:
    url: str
    auth_name: str
    auth_value: str = field(repr=False)
    service_id: str = ""


_config_cache: Dict[tuple, Tuple[float, Endpoint, List[dict]]] = {}


# ---------- settings ----------

def settings() -> Dict[str, str]:
    llm._load_dotenv()
    return {"user_id": os.environ.get("BHASHINI_USER_ID", "").strip(),
            "api_key": Secret(os.environ.get("BHASHINI_API_KEY", "").strip())}


def configured() -> bool:
    s = settings()
    return bool(s["user_id"] and s["api_key"])


# ---------- the one place that sends requests ----------

def _post(url: str, body: dict, headers: Dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    del body  # the request body may hold case text: keep no readable copy in error reports
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=llm._ssl_context()) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        try:
            detail = json.load(err)
            message = detail.get("message") or detail.get("detail") or ""
        except Exception:
            message = ""
        if err.code in (401, 403):
            raise BhashiniUnavailable("Bhashini did not accept the user ID or API key.") from None
        if err.code == 400 and "not supported" in str(message).lower():
            raise BhashiniUnavailable("Bhashini does not support this language for this task.") from None
        raise BhashiniUnavailable(f"Bhashini had a problem (error {err.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise BhashiniUnavailable("Could not reach Bhashini (check the internet).") from None
    except ValueError:
        raise BhashiniUnavailable("Bhashini's answer could not be read.") from None


def _task(task: str, source: str, target: Optional[str] = None) -> dict:
    language = {"sourceLanguage": source}
    if target:
        language["targetLanguage"] = target
    return {"taskType": task, "config": {"language": language}}


def endpoint(task: str, source: str, target: Optional[str] = None) -> Endpoint:
    """The config call: which service does this task for these languages, and where to send it."""
    s = settings()
    if not (s["user_id"] and s["api_key"]):
        raise BhashiniUnavailable("Bhashini is not set up (no BHASHINI_USER_ID / BHASHINI_API_KEY).")
    key = (task, source, target)
    cached = _config_cache.get(key)
    if cached and time.time() - cached[0] < CONFIG_CACHE_SECONDS:
        return cached[1]
    data = _post(CONFIG_URL, {"pipelineTasks": [_task(task, source, target)],
                              "pipelineRequestConfig": {"pipelineId": PIPELINE_ID}},
                 {"userID": s["user_id"], "ulcaApiKey": s["api_key"]})
    try:
        point = data["pipelineInferenceAPIEndPoint"]
        service_id = data["pipelineResponseConfig"][0]["config"][0]["serviceId"]
        found = Endpoint(point["callbackUrl"], point["inferenceApiKey"]["name"],
                         Secret(point["inferenceApiKey"]["value"]), service_id)
    except (KeyError, IndexError, TypeError):
        raise BhashiniUnavailable("Bhashini does not support this language for this task.") from None
    _config_cache[key] = (time.time(), found, data.get("languages") or [])
    return found


def _compute(point: Endpoint, task: dict, input_data: dict) -> dict:
    task["config"]["serviceId"] = point.service_id
    data = _post(point.url, {"pipelineTasks": [task], "inputData": input_data}, {point.auth_name: point.auth_value})
    try:
        return data["pipelineResponse"][0]["output"][0]
    except (KeyError, IndexError, TypeError):
        try:
            return data["output"][0]
        except (KeyError, IndexError, TypeError):
            raise BhashiniUnavailable("Bhashini's answer could not be read.") from None


# ---------- translation ----------

@dataclass
class Translation:
    text: str
    removed: Dict[str, int]  # personal numbers removed before sending


def translate(text: str, source: str, target: str) -> Translation:
    """Translate text. Phone, Aadhaar and email numbers (in any script) are removed BEFORE sending."""
    clean, removed = privacy.redact(text)
    if source == target or not clean.strip():
        return Translation(clean, removed)
    point = endpoint("translation", source, target)
    out = _compute(point, _task("translation", source, target), {"input": [{"source": clean}]})
    translated = out.get("target")
    if not isinstance(translated, str):
        raise BhashiniUnavailable("Bhashini's answer could not be read.")
    return Translation(privacy.redact(translated)[0], removed)


# ---------- speech to text ----------

@dataclass
class Transcript:
    text: str                 # already through the privacy filter
    removed: Dict[str, int]


def speech_to_text(audio: bytes, language: str, audio_format: str = "wav", sampling_rate: int = 16000) -> Transcript:
    """Turn a recording into text. The recording is sent only for this and is never saved."""
    if not audio:
        raise BhashiniUnavailable("The recording is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise BhashiniUnavailable("The recording is too long. Please record a shorter part of the story.")
    point = endpoint("asr", language)
    task = _task("asr", language)
    task["config"].update({"audioFormat": audio_format, "samplingRate": sampling_rate})
    out = _compute(point, task, {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]})
    text = out.get("source")
    if not isinstance(text, str):
        raise BhashiniUnavailable("Bhashini's answer could not be read.")
    clean, removed = privacy.redact(text.strip())
    return Transcript(clean, removed)


def supports(task: str, language: str) -> bool:
    """Whether Bhashini can do this task for this language (asks the config call; False if unavailable)."""
    try:
        endpoint(task, language, "en" if task == "translation" and language != "en" else None)
        return True
    except BhashiniUnavailable:
        return False
