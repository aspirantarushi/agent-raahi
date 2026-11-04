import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest

import intake
import llm
import privacy

HERE = Path(__file__).resolve().parent
NOTES = (HERE.parent / "case_notes.txt").read_text(encoding="utf-8")


def field(value, quote):
    return {"value": value, "quote": quote}


def practice_answer(**changes):
    """What a careful AI should return for case_notes.txt."""
    answer = {
        "custody_began": field("2024-03-15", "Her brother was arrested on 15 March 2024."),
        "offence_date": field(None, "The offence was in February 2024."),
        "today_date": field("2026-11-02", "Today's date: 2 November 2026."),
        "sections": [{"law": "IPC", "section": "380",
                      "quote": "He is charged under IPC 380 (theft in a dwelling house)."}],
        "previously_convicted": field("no", "He has never been convicted before."),
        "other_cases_pending": field("no", "No other cases are pending against him."),
        "delay_by_accused": field("no", "He has not caused any delay in the case."),
        "lawyer": field("Legal aid lawyer", "He has a legal aid lawyer he has met twice."),
    }
    answer.update(changes)
    return answer


# ---------- the practice case ----------

def test_practice_case_is_filled():
    r = intake.check_ai_answer(practice_answer(), NOTES)
    assert r.values == {
        "custody_began": date(2024, 3, 15),
        "today": date(2026, 11, 2),
        "law": "IPC", "section": "380", "more_than_one_section": False,
        "never_convicted": True, "other_cases_pending": False,
        "delay_days_by_accused": 0, "lawyer": "Legal aid lawyer",
    }
    assert r.dropped == []
    # Only the month of the offence is known, so the exact date is asked for.
    assert r.notes_say["offence_date"] == "The offence was in February 2024."
    assert intake.missing_facts(r.values) == ["offence_date"]


# ---------- the AI never gets to guess ----------

def test_guessed_day_is_dropped():
    r = intake.check_ai_answer(practice_answer(
        offence_date=field("2024-02-01", "The offence was in February 2024.")), NOTES)
    assert "offence_date" not in r.values
    assert r.dropped == ["offence_date: 2024-02-01"]
    assert r.notes_say["offence_date"] == "The offence was in February 2024."


def test_wrong_date_is_dropped():
    r = intake.check_ai_answer(practice_answer(
        custody_began=field("2024-03-16", "Her brother was arrested on 15 March 2024.")), NOTES)
    assert "custody_began" not in r.values


def test_quote_not_in_notes_is_dropped():
    r = intake.check_ai_answer(practice_answer(
        other_cases_pending=field("no", "There are no other cases.")), NOTES)
    assert "other_cases_pending" not in r.values
    assert "other_cases_pending" in intake.missing_facts(r.values)


def test_section_must_be_in_its_quote():
    r = intake.check_ai_answer(practice_answer(sections=[
        {"law": "BNS", "section": "305", "quote": "He is charged under IPC 380 (theft in a dwelling house)."}]),
        NOTES)
    assert "section" not in r.values


def test_two_sections_tick_more_than_one():
    notes = "He is charged under IPC 380 and IPC 411."
    r = intake.check_ai_answer({"sections": [
        {"law": "IPC", "section": "380", "quote": "He is charged under IPC 380 and IPC 411."},
        {"law": "IPC", "section": "411", "quote": "He is charged under IPC 380 and IPC 411."},
    ]}, notes)
    assert r.values["section"] == "380" and r.values["more_than_one_section"] is True
    assert r.values["all_sections"] == ["IPC 380", "IPC 411"]


def test_unknown_lawyer_value_is_dropped():
    r = intake.check_ai_answer(practice_answer(
        lawyer=field("Probably legal aid", "He has a legal aid lawyer he has met twice.")), NOTES)
    assert "lawyer" not in r.values


def test_delay_yes_asks_for_the_days():
    notes = "His lawyer asked for adjournments twice."
    r = intake.check_ai_answer({"delay_by_accused": field("yes", "His lawyer asked for adjournments twice.")},
                               notes)
    assert "delay_days_by_accused" not in r.values
    assert "delay_days_by_accused" in intake.missing_facts(r.values)


def test_empty_or_broken_answers_are_safe():
    assert intake.check_ai_answer({}, NOTES).values == {}
    assert intake.check_ai_answer({"sections": "IPC 380", "lawyer": "x"}, NOTES).values == {}


def test_quote_check_ignores_case_and_spacing():
    r = intake.check_ai_answer({"custody_began": field("2024-03-15", "arrested on  15 march 2024")}, NOTES)
    assert r.values["custody_began"] == date(2024, 3, 15)


@pytest.mark.parametrize("quote, ok", [
    ("arrested on 15/03/2024", True),
    ("arrested on 15th March 2024", True),
    ("arrested on 15 Mar 2024", True),
    ("arrested in March 2024", False),
    ("arrested on 15 March", False),
])
def test_date_needs_day_month_and_year(quote, ok):
    r = intake.check_ai_answer({"custody_began": field("2024-03-15", quote)}, quote)
    assert ("custody_began" in r.values) is ok


# ---------- asking one at a time, in the intake file's order ----------

def test_questions_follow_intake_file_order():
    assert intake.question_order() == ["custody_began", "offence_date", "section", "never_convicted",
                                       "other_cases_pending", "answer", "delay_days_by_accused", "lawyer"]


def test_question_text_comes_from_intake_file():
    q = intake.intake_questions()
    assert q[2] == "On what date did custody begin (the date of arrest)?"
    assert q[12] == "Does the person have a lawyer?"


def test_nothing_known_asks_everything_in_order():
    assert intake.missing_facts({}) == ["custody_began", "offence_date", "section", "never_convicted",
                                        "other_cases_pending", "delay_days_by_accused", "lawyer"]


def test_deciding_question_asked_when_offence_has_one():
    missing = intake.missing_facts({"law": "IPC", "section": "406"})
    assert missing.index("answer") == missing.index("other_cases_pending") + 1
    assert intake.offence_question({"law": "IPC", "section": "406"}).startswith("Was the person a clerk")


def test_skipped_facts_are_not_asked_again():
    assert "lawyer" not in intake.missing_facts({}, skipped={"lawyer"})


# ---------- privacy: what is removed before sending ----------

@pytest.mark.parametrize("text, kind", [
    ("call 9876543210", "a phone number"),
    ("call +91 98765 43210", "a phone number"),
    ("call 098765-43210", "a phone number"),
    ("Aadhaar 1234 5678 9012", "an Aadhaar number"),
    ("Aadhaar 1234-5678-9012", "an Aadhaar number"),
    ("mail sister.k@example.com", "an email address"),
])
def test_redact_removes_personal_numbers(text, kind):
    clean, removed = privacy.redact(text)
    assert removed == {kind: 1}
    assert not privacy.personal_details_found(clean)


def test_redact_keeps_case_facts():
    text = ("CNR DLCT010012342024, FIR 123/2024, arrested 15 March 2024, IPC 380, "
            "BNS 117(2), case U-20261103-k7f1, 84 months")
    assert privacy.redact(text) == (text, {})


def test_notes_are_redacted_before_they_reach_the_ai(monkeypatch):
    sent = {}

    def fake_generate(prompt, schema):
        sent["prompt"] = prompt
        return practice_answer()

    monkeypatch.setattr(llm, "_generate_json", fake_generate)
    notes = NOTES + "\nSister's phone: 98765 43210. Email: sis@example.com. Aadhaar 2345 6789 0123."
    answer, clean, removed = llm.read_undertrial_notes(notes)
    for secret in ("98765 43210", "sis@example.com", "2345 6789 0123"):
        assert secret not in sent["prompt"] and secret not in clean
    assert removed == {"a phone number": 1, "an email address": 1, "an Aadhaar number": 1}
    assert "IPC 380" in sent["prompt"]


# ---------- when there is no key or the AI fails ----------

@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr(llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setattr(llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")


def test_no_key_means_not_available(no_key):
    assert not llm.available()
    with pytest.raises(llm.AIUnavailable, match="not set up"):
        llm.read_undertrial_notes(NOTES)


@pytest.mark.parametrize("code, words", [(429, "limit"), (503, "busy"), (403, "key was not accepted"),
                                         (404, "not found")])
def test_http_errors_become_friendly_messages(fake_key, monkeypatch, code, words):
    def fail(*a, **k):
        raise urllib.error.HTTPError("url", code, "error", {}, None)
    monkeypatch.setattr(llm.urllib.request, "urlopen", fail)
    with pytest.raises(llm.AIUnavailable, match=words):
        llm.read_undertrial_notes(NOTES)


def gemini_reply(answer: dict):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}).encode()

    return Response()


def test_busy_main_model_falls_back_to_flash_lite(fake_key, monkeypatch):
    tried = []

    def urlopen(request, **k):
        tried.append(request.full_url.split("/models/")[1].split(":")[0])
        if "gemini-3.8-flash" in request.full_url:
            raise urllib.error.HTTPError("url", 503, "busy", {}, None)
        return gemini_reply(practice_answer())

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    answer, clean, removed = llm.read_undertrial_notes(NOTES)
    assert tried == ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    assert answer["lawyer"]["value"] == "Legal aid lawyer"


def test_slow_main_model_falls_back(fake_key, monkeypatch):
    def urlopen(request, **k):
        if "gemini-3.8-flash" in request.full_url:
            raise urllib.error.URLError(llm.socket.timeout("timed out"))
        return gemini_reply(practice_answer())

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    assert llm.read_undertrial_notes(NOTES)[0]["sections"][0]["section"] == "380"


def test_both_models_busy_gives_friendly_message(fake_key, monkeypatch):
    def urlopen(request, **k):
        raise TimeoutError()

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.AIUnavailable, match="took too long"):
        llm.read_undertrial_notes(NOTES)


def test_bad_key_does_not_try_the_fallback(fake_key, monkeypatch):
    tried = []

    def urlopen(request, **k):
        tried.append(request.full_url)
        raise urllib.error.HTTPError("url", 403, "forbidden", {}, None)

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.AIUnavailable, match="key was not accepted"):
        llm.read_undertrial_notes(NOTES)
    assert len(tried) == 1


def test_no_internet_is_handled(fake_key, monkeypatch):
    def fail(*a, **k):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(llm.urllib.request, "urlopen", fail)
    with pytest.raises(llm.AIUnavailable, match="internet"):
        llm.read_undertrial_notes(NOTES)


def test_unreadable_answer_is_handled(fake_key, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}).encode()

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(llm.AIUnavailable, match="could not be read"):
        llm.read_undertrial_notes(NOTES)


def test_key_is_never_in_the_url(fake_key, monkeypatch):
    seen = {}

    def capture(request, **k):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        raise urllib.error.URLError("stop")

    monkeypatch.setattr(llm.urllib.request, "urlopen", capture)
    with pytest.raises(llm.AIUnavailable):
        llm.read_undertrial_notes(NOTES)
    assert "test-key-not-real" not in seen["url"]
    assert "gemini-3.8-flash" in seen["url"]


def test_dotenv_file_is_read(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('# my key\nGEMINI_API_KEY="abc123"\n')
    llm._load_dotenv(env)
    assert llm.os.environ["GEMINI_API_KEY"] == "abc123"


# ---------- the real AI (runs only when a key is set up) ----------

@pytest.mark.skipif(not llm.available(), reason="No GEMINI_API_KEY: live AI test skipped")
def test_live_ai_reads_practice_case():
    raw, clean, removed = llm.read_undertrial_notes(NOTES)
    r = intake.check_ai_answer(raw, clean)
    assert r.values.get("custody_began") == date(2024, 3, 15)
    assert (r.values.get("law"), r.values.get("section")) == ("IPC", "380")
    assert r.values.get("never_convicted") is True
    assert r.values.get("other_cases_pending") is False
    assert r.values.get("lawyer") == "Legal aid lawyer"
    assert "offence_date" not in r.values  # only "February 2024" is given: no guessing
