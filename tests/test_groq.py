"""Groq as the third, free backup AI: Gemini main -> Gemini backup -> Groq, for reading stories only.
No internet and no real key, except the live test at the end (it runs only when GROQ_API_KEY is in .env)."""

import io
import json
import os
import urllib.error
from pathlib import Path

import pytest

import audit
import llm

ROOT = Path(__file__).resolve().parent.parent
MAIN, BACKUP = llm.DEFAULT_MODEL, llm.FALLBACK_MODEL
GROQ = llm.GROQ_PREFIX + llm.GROQ_DEFAULT_MODEL
STORY = ("Practice case. A worker from Bihar was not paid wages for three months. "
         "Call 9876543210 or Aadhaar 2345 6789 0123.")


def gemini_answer(answer):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}


def groq_reply(answer):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return json.dumps({"choices": [{"message": {"content": json.dumps(answer)}}]}).encode()
    return Response()


@pytest.fixture
def services(monkeypatch):
    """Pretend Gemini (via _call_model) and pretend Groq (via urlopen to api.groq.com)."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-SECRET")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    state = {"gemini": [], "groq": [], "groq_bodies": [], "logged": [], "gemini_result": "busy",
             "groq_result": "ok"}

    def gemini(model, key, body):
        state["gemini"].append(model)
        if state["gemini_result"] == "busy":
            raise llm._Busy("busy", llm.BUSY, 503)
        if state["gemini_result"] == "key":
            raise llm._Failed("key", llm.KEY, 403)
        return gemini_answer({"from": "gemini"})

    def urlopen(request, **k):
        assert request.full_url == llm.GROQ_URL
        state["groq"].append(request.get_header("Authorization"))
        body = json.loads(request.data)
        state["groq_bodies"].append(body)
        if state["groq_result"] == "busy":
            raise urllib.error.HTTPError(request.full_url, 429, "limit", {}, io.BytesIO(b"{}"))
        return groq_reply({"from": "groq"})

    monkeypatch.setattr(llm, "_call_model", gemini)
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(audit, "log_ai_failure",
                        lambda attempts, outcome, base=None: state["logged"].append((attempts, outcome)))
    return state


def ask(**k):
    return llm._generate_json("Read: " + STORY, {"type": "OBJECT", "properties": {"from": {"type": "STRING"}}}, **k)


def test_order_gemini_main_then_backup_then_groq(services):
    answer, model = ask(groq=True)
    assert answer == {"from": "groq"} and model == GROQ
    assert services["gemini"] == [MAIN] * 4 + [BACKUP] and len(services["groq"]) == 1
    attempts, outcome = services["logged"][0]
    assert [a["model"] for a in attempts] == [MAIN] * 4 + [BACKUP]
    assert outcome == f"answered by {GROQ} after 5 failed tries"


def test_groq_not_used_when_gemini_answers(services):
    services["gemini_result"] = "ok"
    assert ask(groq=True) == ({"from": "gemini"}, MAIN)
    assert services["groq"] == []


def test_groq_after_a_bad_gemini_key(services):
    services["gemini_result"] = "key"
    assert ask(groq=True)[1] == GROQ
    assert services["gemini"] == [MAIN]  # a bad key is not retried


def test_groq_only_when_asked_research_and_voice_stay_on_gemini(services):
    with pytest.raises(llm.AIUnavailable):
        ask()  # groq not allowed: research's split, voice
    assert services["groq"] == []
    with pytest.raises(llm.AIUnavailable):
        ask(groq=True, extra_parts=[{"inline_data": {}}])  # a recording never goes to Groq
    assert services["groq"] == []


def test_stories_go_to_groq_but_research_does_not(services, monkeypatch):
    seen = []
    original = llm._generate_json
    monkeypatch.setattr(llm, "_generate_json", lambda p, s, extra_parts=None, groq=False: (
        seen.append(groq) or original(p, s, extra_parts, groq)))
    llm.read_general_notes(STORY)  # only the route matters here
    llm.read_undertrial_notes(STORY)
    with pytest.raises(llm.AIUnavailable):
        llm.split_brief("brief")
    assert seen == [True, True, False]


def test_numbers_are_removed_before_groq_sees_anything(services):
    assert llm.read_general_notes(STORY).model == GROQ
    sent = json.dumps(services["groq_bodies"][0])
    assert "9876543210" not in sent and "2345 6789 0123" not in sent and "not paid wages" in sent


def test_strict_json_schema_for_groq(services):
    ask(groq=True)
    fmt = services["groq_bodies"][0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert services["groq_bodies"][0]["model"] == llm.GROQ_DEFAULT_MODEL
    schema = llm.json_schema(llm.GENERAL_SCHEMA)
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["state"]["properties"]["value"]["type"] == ["string", "null"]
    issue = schema["properties"]["issues"]["items"]["properties"]["category"]
    assert issue == {"type": "string", "enum": ["arrest_or_custody", "online_or_financial_fraud", "electricity_or_water",
                                             "wages_or_work", "ration_or_welfare", "other"]}


def test_other_groq_models_use_json_mode(services, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    assert ask(groq=True)[1] == "groq:llama-3.3-70b-versatile"
    body = services["groq_bodies"][0]
    assert body["response_format"] == {"type": "json_object"} and "schema" in body["messages"][1]["content"]


def test_everything_busy_gives_the_friendly_message_and_logs_groq(services):
    services["groq_result"] = "busy"
    with pytest.raises(llm.AIUnavailable) as err:
        ask(groq=True)
    assert err.value.busy and str(err.value) == llm.BUSY_MESSAGE
    attempts, outcome = services["logged"][0]
    assert attempts[-1] == {"model": GROQ, "error": llm.LIMIT, "code": 429} and "gave up" in outcome
    assert "SECRET" not in json.dumps(services["logged"])  # the key is never logged


def test_groq_key_alone_is_enough_for_reading(services, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(llm, "_load_dotenv", lambda *a, **k: None)
    assert llm.available() and not llm.gemini_available()
    assert ask(groq=True)[1] == GROQ and services["gemini"] == []


def test_the_key_is_sent_only_as_a_header(services):
    ask(groq=True)
    assert services["groq"] == ["Bearer test-groq-key-SECRET"]
    assert "SECRET" not in json.dumps(services["groq_bodies"])


# ---------- live: only when the real key is in .env ----------

def real_groq_key() -> str:
    env = ROOT / ".env"
    for line in (env.read_text(encoding="utf-8").splitlines() if env.exists() else []):
        if line.strip().startswith("GROQ_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


@pytest.mark.skipif(not real_groq_key(), reason="no GROQ_API_KEY in .env")
def test_live_groq_reads_the_hindi_practice_story(monkeypatch):
    import general
    monkeypatch.setenv("GROQ_API_KEY", real_groq_key())
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(llm, "_load_dotenv", lambda *a, **k: None)  # Groq alone
    notes = (ROOT / "case_notes_hi.txt").read_text(encoding="utf-8")
    reading = llm.read_general_notes(notes, output_lang="hi")
    assert reading.model == GROQ
    checked = general.check_general_answer(reading.answer, reading.notes_sent)
    assert checked.what_happened and checked.facts.get("in_custody") is True
