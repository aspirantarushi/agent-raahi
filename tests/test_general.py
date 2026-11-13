"""General intake ("Any case"): three fake stories, no law references from memory, urgency rules,
eligibility, the supervisor flow and the screen."""

import json
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import general
import knowledge
import llm
import section479
import store
from drafts import DRAFT_HEADER
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
UNDERTRIAL = (ROOT / "case_notes.txt").read_text(encoding="utf-8")
UPI = (ROOT / "practice_stories" / "upi_fraud.txt").read_text(encoding="utf-8")
WAGES = (ROOT / "practice_stories" / "unpaid_wages.txt").read_text(encoding="utf-8")
TODAY = date(2026, 11, 4)
MODEL = "gemini-3.5-flash-lite"


def yn(value, quote=None):
    return {"value": value, "quote": quote}


def answer(**fields):
    base = {
        "person_needing_help": "the person in the practice story", "what_happened": [], "timeline": [],
        "danger_now": yn("unknown"), "in_custody": yn("unknown"), "money_lost_online": yn("unknown"),
        "money_lost_in_last_few_days": yn("unknown"), "called_1930": yn("unknown"), "coming_dates": [],
        "sections_charged": [], "issues": [], "documents_held": [], "questions_to_ask": [],
        "woman": yn("unknown"), "under_18": yn("unknown"), "sc_st": yn("unknown"), "disability": yn("unknown"),
        "state": {"value": None, "quote": None}, "income": {"amount": None, "per": "unknown", "quote": None},
    }
    base.update(fields)
    return base


# What a careful AI returns for each fake story.
UNDERTRIAL_ANSWER = answer(
    person_needing_help="the brother, who is in jail",
    what_happened=["The brother was arrested on 15 March 2024 and is charged under IPC 380.",
                   "He has a legal aid lawyer. Bail has never been applied for."],
    timeline=[{"when": "15 March 2024", "what": "arrested"}, {"when": "May 2024", "what": "chargesheet filed"}],
    in_custody=yn("yes", "Her brother was arrested on 15 March 2024."),
    woman=yn("no", "Her brother was arrested"),
    sections_charged=[{"law": "IPC", "section": "380", "quote": "He is charged under IPC 380"}],
    issues=[{"category": "arrest_or_custody", "name": "arrest and bail"}],
    questions_to_ask=["Has the jail legal aid clinic been contacted?"],
    outcome_wanted={"value": "to get him out of jail", "quote": "what can we do to get him out?"},
)
UPI_ANSWER = answer(
    person_needing_help="the mother, aged 68",
    what_happened=["A caller pretending to be from the bank sent a UPI request.",
                   "Rs 40,000 left the account in two payments."],
    timeline=[{"when": "Yesterday", "what": "Rs 40,000 lost in two payments"}],
    danger_now=yn("no", "No one is threatening her now."),
    money_lost_online=yn("yes", "Rs 40,000 left her account in two payments."),
    money_lost_in_last_few_days=yn("yes", "Yesterday she got a call"),
    called_1930=yn("no", "She has not called 1930 yet"),
    woman=yn("yes", "His mother is 68"),
    state={"value": "Bihar", "quote": "lives in Patna, Bihar"},
    issues=[{"category": "online_or_financial_fraud", "name": "online fraud"}],
    documents_held=["bank SMS alerts", "screenshot of the UPI request"],
    questions_to_ask=["What are the transaction IDs?", "Has the card or UPI been blocked?"],
)
WAGES_ANSWER = answer(
    person_needing_help="the construction worker",
    what_happened=["The worker was not paid wages for June to August 2026 by the contractor."],
    timeline=[{"when": "June to August 2026", "what": "worked without pay"}],
    danger_now=yn("no", "He is not in any danger"),
    in_custody=yn("no", "He is not in any danger and no case has been filed."),
    woman=yn("no", "a man aged 35"), under_18=yn("no", "a man aged 35"),
    sc_st=yn("unknown"), disability=yn("unknown"),
    state={"value": "Maharashtra", "quote": "lives in Pune, Maharashtra"},
    income={"amount": 10000, "per": "month", "quote": "He earns about Rs 10,000 a month"},
    issues=[{"category": "other", "name": "unpaid wages"}],
    documents_held=["photos of the site attendance register"],
    questions_to_ask=["Does the worker have any messages from the contractor about wages?",
                      "Were other workers also not paid?"],
)


def summarise(raw, notes, answers=(), model=MODEL):
    reading = general.check_general_answer(raw, notes)
    facts = general.build_facts(reading, list(answers), reading.questions, reading.facts, TODAY)
    return reading, facts, general.make_summary_draft(facts, model)


def refs_not_from_knowledge(text: str, reading: general.GeneralReading):
    """Law or section references in a draft that do not come from knowledge/ (files or sentence table)."""
    allowed = knowledge.all_text()
    table_lines = "\n".join(f"IPC {o.ipc_section} = BNS {o.bns_section}: {o.offence}" for o in reading.sections)
    return [r for r in general.legal_refs(text) if r not in allowed and r not in table_lines]


# ---------- story 1: the practice undertrial case ----------

def test_undertrial_story():
    reading, facts, text = summarise(UNDERTRIAL_ANSWER, UNDERTRIAL)
    assert text.startswith(DRAFT_HEADER)
    assert general.urgent_actions(reading.facts) == []
    assert "Urgency: Urgent: someone is in custody now." in text and "URGENT\n" not in text  # said once
    assert "Arrest and bail — to discuss with a lawyer." in text
    for heading in ["Rights on arrest", "Who to approach for an undertrial"]:
        e = knowledge.get("undertrial_bail.md", heading)
        assert f"“{heading}”" in text and e.source_line in text
    assert "IPC 380 = BNS 305: Theft in a dwelling house or vehicle or place of worship" in text
    assert "charged under [law reference removed: ask a lawyer]" in text  # the AI's own copy is removed
    assert "Qualifies for free legal aid whatever the income, as a person in custody." in text
    assert refs_not_from_knowledge(text, reading) == []


# ---------- story 2: UPI fraud ----------

def test_upi_fraud_story():
    reading, facts, text = summarise(UPI_ANSWER, UPI)
    assert general.urgent_actions(reading.facts) == [general.CALL_1930]
    assert "Urgency: Call 1930 now." in text and "URGENT\n" not in text  # said once, at a glance
    assert "Online fraud — to discuss with a lawyer." in text
    assert knowledge.get("cyber_fraud.md", "Call 1930 at once: report immediately").source_line in text
    assert "Qualifies for free legal aid whatever the income, as a woman." in text
    assert "Bihar: Bihar residents only" in text      # the state note from income_limits.csv ...
    assert "Confirmed on BSLSA" not in text            # ... without our own working notes
    assert "- Has: bank SMS alerts; screenshot of the UPI request" in text
    assert "the bank SMS and email alerts" not in documents_line(text)
    assert refs_not_from_knowledge(text, reading) == []


# ---------- story 3: unpaid wages (not covered by our files) ----------

def test_unpaid_wages_story():
    reading, facts, text = summarise(WAGES_ANSWER, WAGES)
    assert general.urgent_actions(reading.facts) == []
    assert "Unpaid wages — to discuss with a lawyer." in text
    assert "Not covered by our verified files yet; ask NALSA's free helpline 15100." in text
    assert "15100" in text.split("Next steps")[1]
    assert reading.facts["annual_income"] == 120000
    assert ("Qualifies on income: about ₹120,000 a year is below Maharashtra's limit of ₹300,000."
            in text)
    assert ("- Still needed: Appointment letter or work ID card; Pay slips; "
            "Bank statements showing earlier payments; Messages with the employer or contractor; ID proof; "
            "Income proof, or a self-declaration (for free legal aid)") == documents_line(text)
    assert refs_not_from_knowledge(text, reading) == []


# ---------- no law or section from memory ----------

def test_ai_law_references_are_removed_everywhere():
    stuffed = dict(WAGES_ANSWER)
    stuffed.update(
        person_needing_help="the worker under Section 2(f) of the Act",
        what_happened=["Wages are due under the Payment of Wages Act, 1936, Section 5.",
                       "This may be an offence u/s 406 IPC and 316(2) BNS."],
        timeline=[{"when": "June 2026", "what": "Complaint possible under Article 23 of the Constitution"}],
        issues=[{"category": "other", "name": "unpaid wages (Minimum Wages Act s. 20)"}],
        documents_held=["Form 16 under Rule 3"],
        questions_to_ask=["Was a claim filed under the Code on Wages, 2019?"],
    )
    reading, facts, text = summarise(stuffed, WAGES)
    assert refs_not_from_knowledge(text, reading) == []
    for bad in ["Payment of Wages Act", "406", "316(2)", "Article 23", "Minimum Wages Act", "Rule 3",
                "Code on Wages", "2(f)"]:
        assert bad not in text, bad


def test_sections_only_from_the_sentence_table():
    raw = dict(UNDERTRIAL_ANSWER)
    raw["sections_charged"] = [{"law": "IPC", "section": "380", "quote": "He is charged under IPC 380"},
                               {"law": "IPC", "section": "999", "quote": "He is charged under IPC 380"}]
    reading, facts, text = summarise(raw, UNDERTRIAL)
    assert reading.sections_as_written == ["IPC 380"]  # 999 is not in the notes or the table
    assert "999" not in text


def test_section_must_be_written_in_the_notes():
    raw = dict(UPI_ANSWER)
    raw["sections_charged"] = [{"law": "BNS", "section": "318(4)", "quote": "Rs 40,000 left her account"}]
    reading, facts, text = summarise(raw, UPI)
    assert reading.sections == [] and "318(4)" not in text.split("Possible legal issues")[0]


@pytest.mark.parametrize("text", ["IPC 380", "Section 498A", "s. 5", "u/s 420", "302 IPC", "BNSS 35(3)",
                                  "the Payment of Wages Act, 1936", "Article 21", "Rule 3", "CrPC"])
def test_legal_reference_pattern(text):
    assert general.legal_refs(f"It is under {text} here.")


@pytest.mark.parametrize("text", ["15 March 2024", "Rs 40,000", "June to August 2026", "two payments",
                                  "Call 1930 now.", "15100", "aged 68"])
def test_ordinary_text_is_not_a_legal_reference(text):
    assert general.legal_refs(text) == []


# ---------- urgency rules (CLAUDE.md) ----------

def test_danger_shows_call_112_first():
    assert general.urgent_actions({"danger_now": True, "money_lost_online": True})[0] == general.CALL_112


@pytest.mark.parametrize("facts, shown", [
    ({"money_lost_online": True, "money_lost_in_last_few_days": True, "called_1930": False}, True),
    ({"money_lost_online": True}, True),                                     # when, and 1930, not known
    ({"money_lost_online": True, "called_1930": True}, False),               # already called
    ({"money_lost_online": True, "money_lost_in_last_few_days": False}, False),  # long ago
    ({"money_lost_online": False}, False),
])
def test_call_1930_rule(facts, shown):
    assert (general.CALL_1930 in general.urgent_actions(facts)) is shown


def test_yes_no_without_words_from_the_notes_is_dropped():
    raw = dict(UPI_ANSWER)
    raw["danger_now"] = yn("yes", "Someone is threatening her")  # not in the notes
    reading = general.check_general_answer(raw, UPI)
    assert "danger_now" not in reading.facts and "danger_now" in reading.dropped
    assert general.CALL_112 not in general.urgent_actions(reading.facts)


def test_income_must_match_its_words():
    raw = dict(WAGES_ANSWER)
    raw["income"] = {"amount": 120000, "per": "year", "quote": "He earns about Rs 10,000 a month"}
    assert "annual_income" not in general.check_general_answer(raw, WAGES).facts  # no converting by the AI


def test_state_must_be_in_its_words():
    raw = dict(WAGES_ANSWER)
    raw["state"] = {"value": "Gujarat", "quote": "lives in Pune, Maharashtra"}
    assert "state" not in general.check_general_answer(raw, WAGES).facts


# ---------- free legal aid eligibility (plain code) ----------

@pytest.mark.parametrize("facts, status", [
    ({"in_custody": True}, "eligible"),
    ({"woman": True}, "eligible"),
    ({"under_18": True}, "eligible"),
    ({"sc_st": True}, "eligible"),
    ({"disability": True}, "eligible"),
    ({"in_custody": False, "woman": False, "under_18": False, "sc_st": False, "disability": False,
      "state": "Gujarat", "annual_income": 99999}, "eligible"),
    ({"in_custody": False, "woman": False, "under_18": False, "sc_st": False, "disability": False,
      "state": "Gujarat", "annual_income": 100000}, "not eligible on income alone"),  # must be BELOW the limit
    ({"state": "Gujarat", "annual_income": 500000}, "not decided yet"),  # groups still unknown
    ({}, "not decided yet"),
])
def test_eligibility(facts, status):
    assert general.check_eligibility(facts).status == status


def test_eligibility_asks_only_what_is_needed_in_order():
    assert general.check_eligibility({}).missing == ["in_custody", "woman", "under_18", "sc_st", "disability",
                                                     "state", "annual_income"]
    assert general.check_eligibility({"woman": True}).missing == []
    partly = {"in_custody": False, "woman": False, "under_18": False, "state": "Kerala"}
    assert general.check_eligibility(partly).missing == ["sc_st", "disability", "annual_income"]


def test_eligibility_shows_its_sources_and_state_notes():
    e = general.check_eligibility({"in_custody": False, "woman": False, "under_18": False, "sc_st": False,
                                   "disability": False, "state": "Mizoram", "annual_income": 10000})
    assert knowledge.get("legal_aid_eligibility.md", "Who qualifies for free legal aid").source_line in e.sources
    assert any("Mizoram: Very low; likely outdated" in n for n in e.notes)
    assert any("case worth pursuing" in n for n in e.notes)


# ---------- the draft and the supervisor ----------

def test_summary_draft_has_header_and_disclosure():
    _, _, text = summarise(WAGES_ANSWER, WAGES)
    assert text.startswith(DRAFT_HEADER)
    tail = text.rstrip().split("\n")[-1]
    assert tail.startswith("How this draft was prepared: facts were read from case notes with AI assistance "
                           f"(Google Gemini) and checked by a volunteer; {general.RULES_USED};")  # the plain name
    assert "dates were calculated" not in text
    assert "does not predict the outcome" in text


def test_general_case_flow_through_the_supervisor(tmp_path):
    reading, facts, text = summarise(UPI_ANSWER, UPI)
    ai = {"model": MODEL, "read_at": "2026-11-04T10:00:00", "extracted": dict(reading.facts), "not_accepted": []}
    case_id = store.submit(text, facts, base=tmp_path, ai=ai)
    [c] = store.list_cases(tmp_path)
    assert (c["case_type"], c["status"]) == (general.CASE_TYPE, "waiting")
    assert not (tmp_path / "drafts").exists()  # nothing saved before approval

    store.approve(case_id, base=tmp_path, approved_on=date(2026, 11, 5))
    draft = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "approved by the supervisor on 5 November 2026." in draft
    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "- Case type: Any problem" in case and "- Follow-up date: 12 November 2026" in case
    assert [c["case_type"] for c in store.list_cases(tmp_path)] == [general.CASE_TYPE]

    record = audit.read_record(case_id, base=tmp_path)
    assert record["model"] == MODEL and record["ai_extracted"]["money_lost_online"] is True
    assert [e["event"] for e in record["events"]] == ["sent to supervisor", "approved", "timeline created"]

    saved = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file())
    assert "Speaker: the son of the person who lost the money." not in saved  # the notes are never saved


def test_possible_names_are_flagged():
    notes = "The worker, Ramesh, was not paid. The contractor Suresh Patil refused."
    summary = "Ramesh was not paid by Suresh Patil."
    assert general.possible_names(summary, notes) == ["Ramesh", "Suresh", "Patil"]
    assert general.possible_names("The worker was not paid in Maharashtra in June.",
                                  "He lives in Pune, Maharashtra. He was not paid in June.") == []


# ---------- the screen ----------

def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def button(at, label):
    return next(b for b in at.button if b.label == label)


@pytest.fixture
def pretend_ai(monkeypatch, tmp_path):
    answers = {UNDERTRIAL: UNDERTRIAL_ANSWER, UPI: UPI_ANSWER, WAGES: WAGES_ANSWER}
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes", lambda notes, output_lang="en": llm.NotesReading(answers[notes], notes, {}, MODEL))
    original_submit = store.submit
    monkeypatch.setattr(store, "submit", lambda *a, **k: original_submit(*a, base=tmp_path, **k))
    return tmp_path


def read_story(notes):
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    ok(at)
    assert at.radio(key="case_type").value == "Any case (start here)"  # the first choice
    at.text_area(key="g_notes").set_value(notes)
    choose_language(at, "g_notes", language_of(notes))
    button(at, "Read the story").click().run()
    ok(at)
    return at


def test_screen_wages_questions_one_at_a_time_then_send(pretend_ai):
    at = read_story(WAGES)
    assert any("Does the worker have any messages" in m.value for m in at.markdown)
    at.text_input(key="gq-0").set_value("Yes, on his phone")
    button(at, "Next").click().run()
    assert any("Were other workers also not paid?" in m.value for m in at.markdown)
    button(at, "Don't know").click().run()
    ok(at)
    # The story doesn't say what he wants: asked last (by plain code), counted in "Question n of 3"
    assert "Question 3 of 3" in " ".join(m.value for m in at.markdown)
    assert any("What does the person want to happen?" in m.value for m in at.markdown)
    at.text_input(key="gq-2").set_value("His three months' wages")
    button(at, "See the summary").click().run()   # the last question says so
    # Eligible on income, so no eligibility questions: straight to the summary.
    draft = make_drafts(at).session_state["shown_drafts"][0]
    assert "— His three months' wages" in draft
    assert "- Asked: Does the worker have any messages from the contractor about wages? " \
           "— Yes, on his phone" in draft
    assert "- Still to ask the person: Were other workers also not paid?" in draft
    assert "Not covered by our verified files yet; ask NALSA's free helpline 15100." in draft
    assert next(b for b in at.button if b.label.startswith("Send to supervisor")).disabled  # until the volunteer confirms
    at.checkbox(key="g_checked").check().run()
    next(b for b in at.button if b.label.startswith("Send to supervisor")).click().run()
    ok(at)
    assert any("Sent to the supervisor as case" in s.value for s in at.success)
    [c] = store.list_cases(pretend_ai)
    assert c["case_type"] == general.CASE_TYPE


def test_screen_upi_shows_1930_at_the_top_and_cyber_note(pretend_ai):
    at = read_story(UPI)
    assert at.error[0].value.endswith("Call 1930 now.")
    while any(b.label == "Don't know" for b in at.button):
        button(at, "Don't know").click().run()
    assert any("cyber fraud module" in i.value for i in at.info)


def test_screen_eligibility_questions_when_needed(pretend_ai, monkeypatch):
    raw = answer(issues=[{"category": "other", "name": "land dispute"}])
    monkeypatch.setattr(llm, "read_general_notes", lambda notes, output_lang="en": llm.NotesReading(raw, notes, {}, MODEL))
    at = read_story(WAGES)
    button(at, "Don't know").click().run()  # what the person wants: not known yet
    # The free legal aid questions: ONE screen, one question in the count
    assert any("Free legal aid: which of these apply to the person?" in m.value for m in at.markdown)
    counter = next(m.value for m in at.markdown if 'class="q-count"' in m.value)
    assert "Question 2 of 3" in counter  # 1 AI question + the legal aid screen + the state
    labels = [r.label for r in at.radio if str(r.key).startswith("la-")]
    assert "Is the person needing help in jail or police custody now?" in labels and "Is the person needing help a woman?" in labels
    assert any(n.key == "la-income" for n in at.number_input)   # no group is Yes yet: the income box shows
    at.radio(key="la-in_custody").set_value("No")
    at.radio(key="la-woman").set_value("Yes").run()
    assert not any(n.key == "la-income" for n in at.number_input)  # a group applies: income doesn't matter
    button(at, "Next").click().run()
    ok(at)  # a woman qualifies whatever the income, but research needs the state: it is asked next
    assert any("Which state or union territory does the person live in?" in m.value for m in at.markdown)
    at.selectbox(key="ge-state").set_value("Punjab")
    button(at, "See the summary").click().run()
    ok(at)
    assert "Qualifies for free legal aid whatever the income, as a woman." in make_drafts(at).session_state["shown_drafts"][0]


def test_screen_custody_offers_section_479_check(pretend_ai, monkeypatch):
    from test_intake import field, practice_answer
    monkeypatch.setattr(llm, "read_undertrial_notes",  # no offence date in the notes: it is asked first
                        lambda notes: llm.NotesReading(practice_answer(offence_date=field(None, None)), notes, {}, MODEL))
    at = read_story(UNDERTRIAL)
    while any(b.label == "Don't know" for b in at.button):  # the AI's question, then the state
        button(at, "Don't know").click().run()
    button(at, "Open Section 479 check").click().run()
    ok(at)
    assert at.radio(key="case_type").value == "Undertrial"
    assert any("On what date was the offence said to have happened?" in m.value for m in at.markdown)


def test_screen_without_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "available", lambda: False)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_area(key="g_manual").set_value("The landlord locked the tenant out last week.")
    button(at, "Start without AI").click().run()
    ok(at)
    assert any("Free legal aid: which of these apply to the person?" in m.value for m in at.markdown)  # one screen
    button(at, "Skip the rest and see the summary").click().run()
    draft = make_drafts(at).session_state["shown_drafts"][0]
    assert "facts were entered by a volunteer" in draft and "The landlord locked the tenant out" in draft


# ---------- the real AI (only with a key) ----------

@pytest.mark.skipif(not llm.available(), reason="No GEMINI_API_KEY: live AI test skipped")
@pytest.mark.parametrize("notes, urgent, words", [
    (UNDERTRIAL, [], "someone is in custody now."),
    (UPI, [general.CALL_1930], "Call 1930 now."),
    (WAGES, [], "Not covered by our verified files yet; ask NALSA's free helpline 15100."),
])
def test_live_ai_three_stories(notes, urgent, words):
    reading_ai = llm.read_general_notes(notes)
    reading = general.check_general_answer(reading_ai.answer, reading_ai.notes_sent)
    facts = general.build_facts(reading, [], reading.questions, reading.facts, TODAY)
    text = general.make_summary_draft(facts, reading_ai.model)
    assert general.urgent_actions(reading.facts) == urgent
    assert words in text
    assert refs_not_from_knowledge(text, reading) == []
    assert general.possible_names(text, notes) == []


# ---------- documents for problems our files don't cover ----------

def documents_line(text):
    """The documents still needed (one per line under "Still needed:" in the Documents section), joined."""
    part = text.split("\nDocuments\n")[1].split("\n\n")[0].splitlines()
    start = next(i for i, l in enumerate(part) if l.startswith("- Still needed:"))
    items = [l[4:] for l in part[start + 1:] if l.startswith("  - ")]
    return "- Still needed: " + "; ".join(items)


def test_unpaid_wages_gets_no_fir_or_court_papers():
    _, _, text = summarise(WAGES_ANSWER, WAGES)
    line = documents_line(text)
    for word in ["FIR", "Court", "court"]:
        assert word not in line
    assert "FIR" not in text.split("Documents")[1].split("Free legal aid")[0]
    assert legal_refs_free(line)


def legal_refs_free(line):
    return general.legal_refs(line) == []


@pytest.mark.parametrize("issue, story, expected, not_expected", [
    ("domestic violence", "The husband beats the wife at home.",
     ["Marriage proof", "Children's birth certificates", "Any medical records", "Messages", "Notices received"],
     ["FIR copy", "Pay slips"]),
    ("land dispute", "The neighbour took part of the family's land.",
     ["Ownership or rent papers", "Tax receipts", "Notices received"], ["FIR copy"]),
    ("land dispute", "The neighbour took the land. The police refused to file an FIR.",
     ["Ownership or rent papers", "FIR copy", "Court orders"], []),
    ("unpaid wages", "There is a court hearing next month about the wages.",
     ["Pay slips", "FIR copy", "Court orders"], ["Latest electricity bill"]),
    ("electricity cut", "The electricity line was cut five weeks ago although the bills were paid.",
     ["Latest electricity bill", "Receipts of bills paid", "Disconnection notice"], ["Pay slips", "FIR copy"]),
    ("noise from a factory", "The factory runs machines all night.",
     ["Any papers, receipts or messages about the problem"], ["FIR copy"]),
])
def test_documents_by_type_of_problem(issue, story, expected, not_expected):
    raw = answer(what_happened=[story], issues=[{"category": "other", "name": issue}])
    _, _, text = summarise(raw, story)
    line = documents_line(text)
    for d in expected + ["ID proof", "Income proof"]:
        assert d in line, d
    for d in not_expected:
        assert d not in line, d
    assert general.legal_refs(line) == []


def test_first_does_not_mean_fir():
    raw = answer(what_happened=["The first payment was missed by the employer."],
                 issues=[{"category": "other", "name": "unpaid wages"}])
    _, _, text = summarise(raw, "The first payment was missed by the employer.")
    assert "FIR copy" not in documents_line(text)


def test_covered_issue_keeps_its_knowledge_list_and_source():
    _, _, text = summarise(UPI_ANSWER, UPI)
    assert "- Still needed:" in text
    assert knowledge.get("cyber_fraud.md", "Evidence to keep").source_line in text
    assert "a plain list for this kind of problem" not in text


def test_documents_held_are_not_listed_again():
    raw = dict(WAGES_ANSWER)
    raw["documents_held"] = ["pay slips for June", "bank statements"]
    _, _, text = summarise(raw, WAGES)
    line = documents_line(text)
    assert "Pay slips" not in line and "Bank statements" not in line and "Attendance records" in line


# ---------- safety first: an unconfirmed "yes" still shows the warning ----------

def test_unconfirmed_money_loss_still_shows_call_1930():
    raw = dict(UPI_ANSWER)
    raw["money_lost_online"] = yn("yes", "उनके खाते से 40,000 रुपये निकल गए")  # words not in the notes
    reading = general.check_general_answer(raw, UPI)
    assert "money_lost_online" not in reading.facts  # not accepted as a fact
    assert general.urgent_actions(reading.facts) == []
    assert general.urgent_actions(reading.facts, reading.unconfirmed_yes) == [general.CALL_1930]
    _, facts, text = summarise(raw, UPI)
    assert "Urgency: Call 1930 now." in text and "URGENT\n" not in text  # said once, at a glance  # also in the summary


def test_unconfirmed_danger_still_shows_call_112():
    raw = dict(UPI_ANSWER)
    raw["danger_now"] = yn("yes", "someone is threatening her")
    reading = general.check_general_answer(raw, UPI)
    assert general.urgent_actions(reading.facts, reading.unconfirmed_yes)[0] == general.CALL_112


def test_unconfirmed_no_does_not_hide_a_warning():
    raw = dict(UPI_ANSWER)
    raw["called_1930"] = yn("yes", "she already called 1930")  # not in the notes: can't stop the warning
    reading = general.check_general_answer(raw, UPI)
    assert general.CALL_1930 in general.urgent_actions(reading.facts, reading.unconfirmed_yes)


def test_unconfirmed_money_loss_adds_the_1930_next_step():
    raw = dict(UPI_ANSWER)
    raw["money_lost_online"] = yn("yes", "words that are not in the notes")
    _, facts, text = summarise(raw, UPI)
    assert "Call 1930 now." in text.split("Next steps")[1]



def test_questions_already_answered_are_dropped_and_missing_ones_added():
    raw = answer(state={"value": "Maharashtra", "quote": "lives in Pune, Maharashtra"},
                 timeline=[{"when": "15 June", "what": "last paid"}, {"when": "yesterday", "what": "called"}],
                 questions_to_ask=["Which state does he live in?", "Were other workers also not paid?"])
    r = general.check_general_answer(raw, WAGES)
    assert r.questions == ["Were other workers also not paid?",
                           "What does the person want to happen? (the outcome they hope for)",
                           "What is the full date (with the year) for “15 June” (last paid)?"]
    hi = general.check_general_answer(raw, WAGES, "hi")
    assert hi.questions[1].startswith("व्यक्ति क्या चाहता")
    told = answer(outcome_wanted={"value": "to get her money back", "quote": "Rs 40,000 left her account"})
    r = general.check_general_answer(told, UPI)
    assert r.outcome == "to get her money back" and not any("want" in q for q in r.questions)
    facts = general.build_facts(r, [], r.questions, r.facts, TODAY)
    assert "What the person wants\n- to get her money back" in general.summary_body(facts)


def test_prompt_asks_for_outcome_years_and_age():
    p = llm.GENERAL_PROMPT
    assert "Never ask about anything the notes already answer" in p and "what the person wants" in p
    assert "date without a year" in p and "age" in p and "outcome_wanted" in llm.GENERAL_SCHEMA["properties"]


def test_word_check_uses_whole_words():
    raw = answer(woman=yn("no", "a man aged 35"), under_18=yn("no", "a man aged 35"),
                 questions_to_ask=["Does the worker have any messages about wages?", "How old is he?"])
    r = general.check_general_answer(raw, WAGES)
    assert r.questions[0] == "Does the worker have any messages about wages?"  # "age" is not in "wages"
    assert "How old is he?" not in r.questions                                # age is already known


def test_outcome_question_not_added_twice_in_hindi_or_hinglish():
    for asked in ["आपको किस परिणाम की उम्मीद है?", "आप इस मामले में क्या नतीजा चाहती हैं?", "Aap kya chahte hain?"]:
        r = general.check_general_answer(answer(questions_to_ask=[asked]), WAGES, "hi")
        assert r.questions[0] == general.person_not_you(asked)  # "the person", never "you"
        assert not any(q.startswith("व्यक्ति क्या चाहता") for q in r.questions), asked
