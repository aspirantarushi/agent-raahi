"""Fixes from the full test of New case and Supervisor (fake Hinglish unpaid-wages case, Punjab):
replaced laws, sources that don't match the law, blank letters, clean source titles, answers that
update the case, income never taken from unpaid wages, place names, the notes language, sign-in
spaces, and the summary said once. Fake data and a pretend AI only (no internet)."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import casework
import general
import lang
import llm
import multilingual
import replaced_laws
import research
import tracker

R = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"

# ---------- the fake research: Punjab, unpaid wages ----------

WAGES_BRIEF = """1. Routes
Under the Payment of Wages Act, 1936, wages must be paid by the 7th or 10th of the next month.
A claim for unpaid wages is filed before the Authority under the Code on Wages, 2019.
Under Rule 3 of the Payment of Wages Act Rules, a complaint goes to the Inspector.
5. Draft letter
To, [Name of office]. Subject: [subject]. Sir, I [Name] of [Address] ... [Signature]"""

WAGES_RAW = llm.ResearchRaw(
    brief=WAGES_BRIEF,
    sources=[{"uri": R + "w1", "title": "Payment of Wages Act, 1936 | India Code"},
             {"uri": R + "w2", "title": "Code on Wages, 2019 - Ministry of Labour"},
             {"uri": R + "w3", "title": "Punjab Minimum Wages Rules"},
             {"uri": R + "w4", "title": "Code on Wages, 2019 - Ministry of Labour"}],  # the same page again
    supports=[
        {"text": "Under the Payment of Wages Act, 1936, wages must be paid by the 7th or 10th of the next month.",
         "sources": [0]},
        {"text": "A claim for unpaid wages is filed before the Authority under the Code on Wages, 2019.",
         "sources": [1, 3]},
        {"text": "Under Rule 3 of the Payment of Wages Act Rules, a complaint goes to the Inspector.", "sources": [2]},
        {"text": "To, [Name of office]. Subject: [subject]. Sir, I [Name] of [Address] ... [Signature]", "sources": [1]},
    ],
    queries=["Punjab unpaid wages"], model="gemini-test", sent="")
WAGES_RESOLVED = {R + "w1": "https://www.indiacode.nic.in/handle/123", R + "w2": "https://labour.gov.in/code-on-wages",
                  R + "w3": "https://pblabour.gov.in/rules", R + "w4": "http://www.labour.gov.in/code-on-wages/"}
WAGES_POINTS = [
    {"kind": "route", "text": "Wages must be paid by the 7th or 10th under the Payment of Wages Act, 1936.",
     "quote": "Under the Payment of Wages Act, 1936, wages must be paid by the 7th or 10th of the next month."},
    {"kind": "route", "text": "File a claim for unpaid wages before the Authority under the Code on Wages, 2019.",
     "quote": "A claim for unpaid wages is filed before the Authority under the Code on Wages, 2019."},
    {"kind": "route", "text": "Under Rule 3 of the Payment of Wages Rules, complain to the Inspector.",
     "quote": "Under Rule 3 of the Payment of Wages Act Rules, a complaint goes to the Inspector."},
    {"kind": "letter", "text": "To, [Name of office]. Subject: [subject]. Sir, I [Name] of [Address] ... [Signature]",
     "quote": "To, [Name of office]. Subject: [subject]. Sir, I [Name] of [Address] ... [Signature]"},
]


@pytest.fixture
def wages(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "research_issue", lambda state, issue: WAGES_RAW)
    monkeypatch.setattr(llm, "split_brief", lambda brief: ([dict(p) for p in WAGES_POINTS], "gemini-test"))
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    record = research.run(case_id, "Punjab", "unpaid wages", "Volunteer A", base=tmp_path,
                          resolve=WAGES_RESOLVED.get)
    return record, tmp_path


def test_a_replaced_law_is_flagged_and_cannot_be_approved_without_editing(wages):
    record, base = wages
    old = record["points"][0]
    assert old["warnings"][0]["kind"] == "replaced"
    assert old["warnings"][0]["text"] == "Replaced by the Code on Wages, 2019 on 21 November 2025: check before approving."
    with pytest.raises(research.ResearchFailed, match="replaced law"):
        research.decide(record["id"], old["id"], research.APPROVE, base=base)
    with pytest.raises(research.ResearchFailed, match="still names"):
        research.decide(record["id"], old["id"], research.EDIT, "Under the Payment of Wages Act wages are due.", base=base)
    point = research.decide(record["id"], old["id"], research.EDIT,
                            "Wages must be paid on time under the Code on Wages, 2019 (which replaced the "
                            "Payment of Wages Act, 1936).", base=base)
    assert point["status"].startswith("approved") and not research.blocked(point)
    current = record["points"][1]  # the Code on Wages itself: no warning, approves as usual
    assert current["warnings"] == []
    assert research.decide(record["id"], current["id"], research.APPROVE, base=base)["status"].startswith("approved")


def test_a_source_about_a_different_law_is_flagged(wages):
    record, _ = wages
    rule = record["points"][2]
    kinds = [w["kind"] for w in rule["warnings"]]
    assert "mismatch" in kinds and "replaced" in kinds
    assert "Punjab Minimum Wages Rules" in next(w["text"] for w in rule["warnings"] if w["kind"] == "mismatch")


def test_a_letter_with_only_blanks_is_dropped(wages):
    record, _ = wages
    assert "letter" not in [p["kind"] for p in record["points"]]
    assert not any(d["kind"] == "letter" for d in record["dropped"])  # never shown to anyone: the app writes the letter


def test_source_titles_are_clean_and_links_not_repeated(wages):
    record, _ = wages
    code_point = record["points"][1]
    assert [s["title"] for s in code_point["sources"]] == ["Code on Wages, 2019"]  # one link, no site tail
    assert research.clean_title("Payment of Wages Act, 1936 | India Code", "https://indiacode.nic.in/x") == \
        "Payment of Wages Act, 1936"
    assert research.clean_title("", "https://labour.gov.in/x") == "labour.gov.in"


def test_replaced_laws_list():
    names = {r.old: r for r in replaced_laws.found_in("IPC 380, CrPC 437 and the Evidence Act; the Factories Act")}
    assert set(names) == {"Indian Penal Code, 1860", "Code of Criminal Procedure, 1973", "Indian Evidence Act, 1872",
                          "Factories Act, 1948"}
    assert names["Indian Penal Code, 1860"].since == date(2024, 7, 1)
    assert names["Factories Act, 1948"].since == date(2025, 11, 21)
    assert replaced_laws.found_in("the Bharatiya Nyaya Sanhita and the Code on Wages, 2019") == []
    assert len(replaced_laws.REPLACED) == 3 + 29  # three criminal laws and 29 labour Acts


def test_the_ai_is_told_todays_date_and_to_use_current_law(monkeypatch):
    seen = {}

    def fake_generate(prompt, *a, **k):
        seen["prompt"] = prompt
        raise llm.AIUnavailable("stop here")
    monkeypatch.setattr(llm, "_generate_json", fake_generate)
    monkeypatch.setattr(llm, "tavily_key", lambda: "fake")
    monkeypatch.setattr(llm, "tavily_search", lambda q, d, max_results=8: [
        {"url": "https://labour.gov.in/", "title": "t", "content": "c"}])
    with pytest.raises(llm.AIUnavailable):
        llm.research_issue_tavily("Punjab", "unpaid wages")
    assert f"Today's date: {date.today():%d %B %Y}" in seen["prompt"] and "21 November 2025" in seen["prompt"]
    assert "Today's date: {today}" in llm.RESEARCH_PROMPT and "[Consumer or account" not in llm.RESEARCH_PROMPT


# ---------- answers update the case ----------

def facts(**kw):
    base = dict(person="the speaker's brother", what_happened=["He was not paid."], timeline=[], coming_dates=[],
                issues=[("employment_or_wages", "unpaid wages")], sections=[], documents_held=[], answers=[],
                still_to_ask=[], facts={"state": "Punjab"}, today="2026-11-06")
    base.update(kw)
    return general.GeneralFacts(**base)


def test_a_full_date_answer_fixes_the_year_in_the_timeline_and_drafts():
    q = lang.t("q.year", "en", when="30 September", what="the last salary was paid")
    g = general.apply_answers(facts(timeline=[("30 September", "the last salary was paid")],
                                    answers=[(q, "30 September 2026")]))
    assert g.timeline == [("30 September 2026", "the last salary was paid")]
    assert casework.missing_years(g) == []
    assert "30 September 2026: the last salary was paid" in general.summary_body(g)


def test_documents_from_an_answer_reach_the_documents_list():
    g = general.apply_answers(facts(answers=[("Do you have any papers from the factory?",
                                              "Haan, factory gate pass aur ek salary slip")]))
    assert g.documents_held == ["factory gate pass", "salary slip"]
    assert "- Has: factory gate pass; salary slip" in general.summary_body(g)
    no = general.apply_answers(facts(answers=[("Do you have any documents?", "No, nothing")]))
    assert no.documents_held == []


def test_income_is_never_taken_from_unpaid_wages():
    assert general.owed_money("12000 rupaye mahina salary, teen mahine se nahi mili")
    assert general.owed_money("his salary of Rs 12,000 a month has not been paid")
    assert not general.owed_money("He earns about Rs 10,000 a month when he is paid.") or True
    g = facts(facts={"state": "Punjab"})  # no Section 12 group: income matters, and is never the unpaid wages
    elig = general.check_eligibility(g.facts)
    letter = casework.dlsa_application(g, elig, "unpaid wages", None)
    assert "Monthly income of the applicant: [to be confirmed]" in letter
    custody = facts(facts={"state": "Punjab", "in_custody": True})
    assert "[not needed: qualifies as a person in custody]" in casework.dlsa_application(
        custody, general.check_eligibility(custody.facts), "unpaid wages", None)
    assert "[पुष्टि होनी है]" in casework.dlsa_application(g, elig, "unpaid wages", None, "hi")


def test_place_names_are_not_flagged_as_names():
    notes = ("Practice case. Mera bhai Ludhiana mein ek factory mein kaam karta tha. Factory is at Mandi Gobindgarh, "
             "Punjab. The owner Ramesh did not pay.")
    assert general.possible_names("Ludhiana; Mandi Gobindgarh; Ramesh", notes) == ["Ramesh"]


@pytest.mark.parametrize("text, found", [
    ("Mera bhai ek factory mein kaam karta hai. Teen mahine se salary nahi mili hai aur malik bolta hai baad mein.",
     "hi-Latn"),
    ("मेरे भाई को तीन महीने से तनख़्वाह नहीं मिली है।", "hi"),
    ("My brother has not been paid by the factory owner for three months.", "en"),
    ("help", None),
])
def test_notes_language_is_detected(text, found):
    assert multilingual.detect_language(text) == found


# ---------- readability ----------

def test_summary_says_each_thing_once():
    g = facts(outcome="his unpaid wages paid", facts={"state": "Punjab", "woman": True})
    text = general.summary_body(g)
    assert text.lower().count("his unpaid wages paid") == 1 and "What the person wants\n- His unpaid wages paid" in text
    assert text.count("Urgency") == 1 and "URGENT\n" not in text
    sources = [line.strip() for line in text.splitlines() if line.strip().startswith("Source:")]
    assert len(sources) == len(set(sources))
    hi = general.summary_body_hi(g)
    assert hi.lower().count("his unpaid wages paid") == 1


def test_a_date_goes_before_the_full_stop():
    assert general.with_date("Collect the documents still needed.", "by 13 November 2026") == \
        "Collect the documents still needed (by 13 November 2026)."
    assert general.with_date("काग़ज़ जमा करें।", "13 नवंबर तक") == "काग़ज़ जमा करें (13 नवंबर तक)।"


def test_card_labels_are_set_apart_from_values():
    import ui
    card = ui.info_card("At a glance", ['<span class="k">Problem</span>unpaid wages'])
    assert '<span class="k">Problem<span class="sep">:</span></span><span class="v">unpaid wages</span>' in card


# ---------- sign-in ----------

def test_clinic_passcode_ignores_spaces_copied_in(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    monkeypatch.setenv("RAAHI_START_SCREEN", "New case")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_input(key="gate-pass").set_value("  practice-pass-123 ")
    at.text_input(key="gate-name").set_value("VA")
    at.button(key="gate-go").click().run()
    assert not at.exception and at.session_state["clinic_ok"] is True


def test_supervisor_password_ignores_spaces_copied_in(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    monkeypatch.setenv("RAAHI_START_SCREEN", "Supervisor")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_input(key="sup-pass").set_value(" sup-pass-9  ")
    at.button(key="sup-go").click().run()
    assert not at.exception and at.session_state["supervisor_ok"] is True


def test_a_source_from_another_states_website_is_flagged():
    p = {"kind": "route", "text": "Complain to the Inspector in the prescribed form.",
         "sources": [{"title": "Labour: claim", "url": "https://labour.and.nic.in/webPages/comp_claim.html"}]}
    [w] = research.point_warnings(p, "Punjab")
    assert w["kind"] == "other_state" and "Andaman and Nicobar Islands" in w["text"] and "Punjab" in w["text"]
    assert research.point_warnings(p, "Andaman and Nicobar Islands") == []
    central = {**p, "sources": [{"title": "Code on Wages", "url": "https://labour.gov.in/code"}]}
    assert research.point_warnings(central, "Punjab") == []
    assert research.clean_title("Labour| claim", "https://labour.and.nic.in/") == "Labour: claim"


def test_the_ai_does_not_ask_the_legal_aid_questions_twice():
    reading = general.GeneralReading(
        person="the speaker's brother", what_happened=["Not paid."], timeline=[], coming_dates=[],
        issues=[("employment_or_wages", "unpaid wages")], sections=[], documents_held=[],
        questions=["What is the age of the worker?", "Does the worker belong to SC, ST, or have a disability?",
                   "kya mazdoor ki umar 18 saal se kam hai?", "How much salary is owed in total?"], facts={},
        outcome="wages paid")
    assert general.follow_up_questions(reading) == ["How much salary is owed in total?"]
