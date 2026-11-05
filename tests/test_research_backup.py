"""The research backup (Tavily search on official sites, then a brief written only from those results),
the Nyaya Setu button, and the story kept across the clinic sign-in. Fake search results only: the
real Gemini, Groq and Tavily limits are never used."""

import json
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import audit
import llm
import research
import tracker

REAL_TAVILY = llm.tavily_search  # tests/conftest.py replaces it in every test; one test needs the real one

FAKE_RESULTS = [
    {"url": "https://www.sbpdcl.co.in/consumer/complaints", "title": "SBPDCL complaints", "content": "Write to the AE."},
    {"url": "https://berc.co.in/cgrf", "title": "BERC CGRF", "content": "Consumer Grievance Redressal Forum."},
    {"url": "https://www.lawrato.com/electricity", "title": "A law blog", "content": "Blog text."},  # not official
]
SENTENCES = {"sentences": [
    {"text": "First write to the Assistant Engineer of the supply sub-division.", "sources": [1]},
    {"text": "If there is no reply, complain to the Consumer Grievance Redressal Forum.", "sources": [2]},
    {"text": "Keep the latest bill and payment receipts.", "sources": [3]},       # only a blog: dropped
    {"text": "Call the minister directly.", "sources": []},                        # no source: dropped
    {"text": "Draft letter: To the Assistant Engineer, [Name of sub-division]: the electricity supply to my house was cut without notice. Please restore it. [Name] [Signature]", "sources": [1]},
]}
POINTS = [
    {"kind": "route", "text": "Write first to the Assistant Engineer.",
     "quote": "First write to the Assistant Engineer of the supply sub-division."},
    {"kind": "route", "text": "If no reply, complain to the CGRF.",
     "quote": "If there is no reply, complain to the Consumer Grievance Redressal Forum."},
    {"kind": "documents", "text": "Keep the latest bill and receipts.", "quote": "Keep the latest bill and payment receipts."},
    {"kind": "route", "text": "Call the minister.", "quote": "Call the minister directly."},
    {"kind": "letter", "text": "To the Assistant Engineer, [Name of sub-division]: the electricity supply to my house was cut without notice. Please restore it. [Name] [Signature]",
     "quote": "Draft letter"},
]


@pytest.fixture
def backup(monkeypatch):
    """Gemini's Google Search fails (tests/conftest.py); Tavily and the brief writer are pretend."""
    seen = {"queries": [], "domains": [], "prompts": [], "groq": []}
    monkeypatch.setattr(llm, "tavily_key", lambda: "fake-tavily-key")

    def fake_search(query, domains, max_results=8):
        seen["queries"].append(query)
        seen["domains"].append(list(domains))
        return [dict(r) for r in FAKE_RESULTS]

    def fake_json(prompt, schema, extra_parts=None, groq=False):
        seen["prompts"].append(prompt)
        seen["groq"].append(groq)
        if schema is llm.BRIEF_SCHEMA:
            return json.loads(json.dumps(SENTENCES)), "gemini-test"
        return {"points": [dict(p) for p in POINTS]}, "gemini-test"

    monkeypatch.setattr(llm, "tavily_search", fake_search)
    monkeypatch.setattr(llm, "_generate_json", fake_json)
    return seen


def new_case(tmp_path):
    return tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]


def test_tavily_is_used_when_google_search_fails_with_every_check(tmp_path, backup):
    case_id = new_case(tmp_path)
    record = research.run(case_id, "Bihar", "electricity cut; call 9876543210", "Volunteer A", base=tmp_path)
    assert record["search"] == "Tavily search (official sites only)" and "Tavily" in record["model"]
    # Only the state and the issue, numbers removed; Tavily limited to the official-site list
    assert backup["queries"] == ["electricity cut; call [phone number removed] Bihar complaint procedure official"] or \
        "9876543210" not in backup["queries"][0]
    assert "gov.in" in backup["domains"][0] and "berc.co.in" in backup["domains"][0]
    # The writer saw only official results (the blog was filtered out before it), and Groq may help
    assert "lawrato" not in backup["prompts"][0] and backup["groq"] == [True, True]
    kept = [p["text"] for p in record["points"]]
    assert kept == ["Write first to the Assistant Engineer.", "If no reply, complain to the CGRF.",
                    POINTS[4]["text"]]
    assert {s["url"] for p in record["points"] for s in p["sources"]} <= {r["url"] for r in FAKE_RESULTS[:2]}
    reasons = {d["text"]: d["reason"] for d in record["dropped"]}
    assert reasons["Keep the latest bill and receipts."] == "no search result backs it"  # its only result was a blog
    assert reasons["Call the minister."] == "no search result backs it"
    # Which search was used: in the audit record and the problems log
    events = audit.read_record(case_id, base=tmp_path)["events"]
    assert any(e["event"] == "research search" and "Tavily" in e["details"] for e in events)
    assert "search: Tavily search (official sites only)" in events[-1]["details"]
    [problem] = [p for p in audit.list_problems(base=tmp_path) if p.get("research_search")]
    assert problem["case_id"] == case_id and "Gemini with Google Search did not work" in problem["text"]
    assert "fake-tavily-key" not in json.dumps(events) + json.dumps(problem)
    assert record["label"] == research.LABEL and record["status"] == research.WAITING  # supervisor approves


def test_google_search_is_tried_first(tmp_path, backup, monkeypatch):
    from test_research import BIHAR_POINTS, BIHAR_RAW, resolve
    monkeypatch.setattr(llm, "research_issue", lambda s, i: BIHAR_RAW)
    monkeypatch.setattr(llm, "split_brief", lambda brief: ([dict(p) for p in BIHAR_POINTS], "gemini-test"))
    record = research.run(new_case(tmp_path), "Bihar", "electricity cut", "Volunteer A", base=tmp_path, resolve=resolve)
    assert record["search"] == "Gemini with Google Search" and backup["queries"] == []


def test_without_a_tavily_key_research_fails_and_suggests_15100(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "tavily_key", lambda: None)
    with pytest.raises(research.ResearchFailed, match="15100"):
        research.run(new_case(tmp_path), "Bihar", "electricity cut", "Volunteer A", base=tmp_path)


def test_tavily_results_from_other_sites_are_never_used(monkeypatch):
    monkeypatch.setattr(llm, "tavily_key", lambda: "fake")
    monkeypatch.setattr(llm, "tavily_search", lambda q, d, max_results=8: [FAKE_RESULTS[2]])
    with pytest.raises(llm.AIUnavailable, match="no official search results"):
        llm.research_issue_tavily("Bihar", "electricity cut")


def test_tavily_request_sends_the_key_only_in_the_header(monkeypatch):
    sent = {}

    def fake_post(url, auth, body, model):
        sent.update(url=url, auth=auth, body=body)
        return {"results": [{"url": "https://www.sbpdcl.co.in/", "title": "t", "content": "c"}]}
    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm, "tavily_key", lambda: "SECRET-KEY")
    out = REAL_TAVILY("q", ["gov.in"])
    assert sent["url"] == "https://api.tavily.com/search" and sent["auth"] == {"Authorization": "Bearer SECRET-KEY"}
    assert "SECRET-KEY" not in json.dumps(sent["body"]) and sent["body"]["include_domains"] == ["gov.in"]
    assert out == [{"url": "https://www.sbpdcl.co.in/", "title": "t", "content": "c"}]


# ---------- the Nyaya Setu button ----------

def test_nyaya_setu_button_opens_whatsapp_only(monkeypatch):
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert 'NYAYA_SETU_URL = "https://wa.me/917217711814"' in source  # no ?text=: the story is never pre-filled
    from test_research import STORY, fake_ai as _  # noqa: F401
    from test_general import MODEL, answer, yn
    raw = answer(what_happened=["The electricity line was cut."],
                 issues=[{"category": "electricity_or_water", "name": "electricity connection cut"}],
                 state={"value": "Bihar", "quote": "lives in Bihar"}, woman=yn("yes", "The person seeking help"),
                 outcome_wanted={"value": "the connection restored", "quote": "She wants the connection restored."})
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", known=None: llm.NotesReading(raw, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    at.text_area(key="g_notes").set_value(STORY)
    next(b for b in at.button if b.label == "Read the story").click().run()
    assert not at.exception, at.exception[0].stack_trace
    buttons = [e for e in at.get("link_button")]
    assert [b.proto.url for b in buttons] == ["https://wa.me/917217711814"]   # research failed: shown
    assert buttons[0].proto.label == "Ask Nyaya Setu on WhatsApp (7217711814)"


# ---------- the story kept across the clinic sign-in ----------

def test_story_typed_on_home_survives_the_clinic_sign_in(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    monkeypatch.setenv("RAAHI_START_SCREEN", "Home")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="ui_lang").set_value("hi").run()
    at.text_area(key="home_story").set_value("Bhai ko 15 March 2024 ko pakda gaya.")
    at.button(key="home-go").click().run()
    assert at.title[0].value == "क्लिनिक साइन-इन"          # the sign-in comes in between
    at.text_input(key="gate-pass").set_value("practice-pass-123")
    at.text_input(key="gate-name").set_value("VA")
    at.button(key="gate-go").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert at.text_area(key="g_notes").value == "Bhai ko 15 March 2024 ko pakda gaya."
    assert at.selectbox(key="g_notes_lang").value == "hi-Latn"  # detected: Hinglish (Hindi in English letters)
    assert "held_story" not in at.session_state          # held only until it is back in the box
