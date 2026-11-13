"""When the AI fails: retries after 2, 4 and 8 seconds, then the backup model; a daily limit goes
straight to the backup; a friendly message and the form if it still fails; every failure in the
problems log (time, error type, model; never case text). No internet and no real key needed."""

import io
import json
import socket
import urllib.error
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import llm
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

MAIN, BACKUP = llm.DEFAULT_MODEL, llm.FALLBACK_MODEL
GOOD = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
SECRET_STORY = "Practice story: Meena from Rampur was not paid"


@pytest.fixture
def ai(monkeypatch, tmp_path):
    """A pretend AI service: `script` is the list of results, one per call, in order."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    state = {"script": [], "calls": [], "waits": [], "logged": []}

    def call(model, key, body):
        state["calls"].append(model)
        result = state["script"].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(llm, "_call_model", call)
    monkeypatch.setattr(llm, "_sleep", lambda s: state["waits"].append(s))
    monkeypatch.setattr(audit, "log_ai_failure",
                        lambda attempts, outcome, base=None: state["logged"].append((attempts, outcome)))
    return state


def busy(kind=llm.BUSY, code=503):
    return llm._Busy("busy", kind, code)


def ask():
    return llm._generate_json("Read this: " + SECRET_STORY, {"type": "OBJECT"})


def test_retries_after_2_4_8_seconds_then_the_backup(ai):
    ai["script"] = [busy(), busy(), busy(), busy(llm.TIMEOUT, None), GOOD]
    answer, model = ask()
    assert answer == {"ok": True} and model == BACKUP
    assert ai["calls"] == [MAIN, MAIN, MAIN, MAIN, BACKUP]
    assert ai["waits"] == [2, 4, 8]
    attempts, outcome = ai["logged"][0]
    assert [a["error"] for a in attempts] == [llm.BUSY] * 3 + [llm.TIMEOUT]
    assert outcome == f"answered by {BACKUP} after 4 failed tries"


def test_a_retry_that_works_stops_early(ai):
    ai["script"] = [busy(llm.LIMIT, 429), GOOD]
    assert ask()[1] == MAIN
    assert ai["calls"] == [MAIN, MAIN] and ai["waits"] == [2]


def test_no_failure_nothing_logged(ai):
    ai["script"] = [GOOD]
    ask()
    assert ai["logged"] == [] and ai["waits"] == []


def test_a_daily_limit_goes_straight_to_the_backup(ai):
    ai["script"] = [busy(llm.DAILY_LIMIT, 429), GOOD]
    assert ask()[1] == BACKUP
    assert ai["calls"] == [MAIN, BACKUP] and ai["waits"] == []


def test_still_failing_gives_the_friendly_message(ai):
    ai["script"] = [busy()] * 4 + [busy(llm.DAILY_LIMIT, 429)]
    with pytest.raises(llm.AIUnavailable) as err:
        ask()
    assert str(err.value) == "The AI is busy; continue with the form." and err.value.busy
    assert len(ai["calls"]) == 5
    attempts, outcome = ai["logged"][0]
    assert [a["model"] for a in attempts] == [MAIN] * 4 + [BACKUP] and "gave up" in outcome


def test_a_bad_key_is_not_retried_but_is_logged(ai):
    ai["script"] = [llm._Failed("the API key was not accepted", llm.KEY, 403)]
    with pytest.raises(llm.AIUnavailable) as err:
        ask()
    assert not err.value.busy and ai["calls"] == [MAIN] and ai["waits"] == []
    assert ai["logged"][0][0] == [{"model": MAIN, "error": llm.KEY, "code": 403}]


# ---------- what the real service sends, sorted into error types ----------

def http_error(code, body):
    return urllib.error.HTTPError("https://x", code, "x", {}, io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize("error, kind", [
    (http_error(503, {"error": {"status": "UNAVAILABLE"}}), llm.BUSY),
    (http_error(429, {"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProject"}]}]}}),
     llm.LIMIT),
    (http_error(429, {"error": {"details": [{"violations": [
        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}), llm.DAILY_LIMIT),
    (socket.timeout(), llm.TIMEOUT),
])
def test_errors_are_sorted(monkeypatch, error, kind):
    def fail(*a, **k):
        raise error
    monkeypatch.setattr(llm.urllib.request, "urlopen", fail)
    with pytest.raises(llm._Busy) as caught:
        llm._call_model(MAIN, "test-key-not-real", {})
    assert caught.value.kind == kind


def test_the_log_entry_has_no_case_text(tmp_path):
    entry = audit.log_ai_failure([{"model": MAIN, "error": llm.BUSY, "code": 503},
                                  {"model": BACKUP, "error": llm.DAILY_LIMIT, "code": 429}],
                                 "gave up after every try: the form opened instead", base=tmp_path)
    saved = audit.list_problems(base=tmp_path)[0]
    assert saved == entry and saved["where"] == "AI service" and saved["time"]
    assert f"{MAIN}: {llm.BUSY} (error 503)" in saved["text"] and BACKUP in saved["text"]
    assert "Meena" not in json.dumps(saved) and "test-key" not in json.dumps(saved)


# ---------- on screen: the form opens, the story is kept ----------

def test_any_case_form_opens_when_the_ai_is_busy(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)

    def busy_ai(*a, **k):
        raise llm.AIUnavailable(llm.BUSY_MESSAGE, busy=True)
    monkeypatch.setattr(llm, "read_general_notes", busy_ai)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_area(key="g_notes").set_value("Practice case. The worker was not paid for three months.")
    choose_language(at, "g_notes", language_of("Practice case. The worker was not paid for three months."))
    next(b for b in at.button if b.label == "Read the story").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert any("The AI is busy; continue with the form." in w.value for w in at.warning)
    assert at.session_state["gen"] is not None                      # the form (questions) is open
    assert at.text_area(key="g_notes").value.startswith("Practice case.")  # nothing lost
    assert not [e for e in at.error if "busy" in e.value]


def test_hindi_busy_message():
    import lang
    assert lang.t("ui.ai_busy", "hi") and lang.t("ui.ai_busy", "hi") != lang.t("ui.ai_busy")


def test_the_log_says_what_happened_after_giving_up(ai):
    """Research that hits the limit on every try moves to the backup search (never "the form opened");
    a story that can't be read opens the form. (Real research calls are switched off in tests, so the research
    call is checked in the code itself.)"""
    ai["script"] = [busy(llm.DAILY_LIMIT, 429)] * 8
    with pytest.raises(llm.AIUnavailable):
        llm._generate({"contents": []}, then=llm.BACKUP_SEARCH)
    assert ai["logged"][-1][1] == "gave up after every try: research used the backup search"
    ai["script"] = [busy(llm.DAILY_LIMIT, 429)] * 8
    with pytest.raises(llm.AIUnavailable):
        ask()
    assert ai["logged"][-1][1] == "gave up after every try: the form opened instead"
    source = (Path(__file__).resolve().parents[1] / "llm.py").read_text(encoding="utf-8")
    research = source[source.index("def research_issue(state"):source.index("def split_brief")]
    assert "_generate(body, then=BACKUP_SEARCH if tavily_key() else" in research
