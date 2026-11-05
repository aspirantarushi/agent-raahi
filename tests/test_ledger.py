"""Evidence ledger: where every fact came from; legal points without a source are "unresolved"."""

from datetime import date

from streamlit.testing.v1 import AppTest

import drafts
import general
import knowledge
import ledger
import llm
import store
from test_drafts import practice_facts
from test_general import UPI, UPI_ANSWER, WAGES, WAGES_ANSWER, summarise, yn
from test_intake import NOTES, practice_answer

AI_READ = {"custody_began": date(2024, 3, 15), "law": "IPC", "section": "380", "never_convicted": True,
           "other_cases_pending": False, "delay_days_by_accused": 0, "lawyer": "Legal aid lawyer"}


def entries_by_fact(entries):
    return {e.fact: e for e in entries}


def test_undertrial_sources():
    facts = practice_facts()
    e = entries_by_fact(ledger.undertrial(facts, drafts.recalculate(facts), AI_READ, ai_checked=True))
    assert e["fact.custody_began"].source == ledger.AI_CHECKED
    assert e["fact.offence_date"].source == ledger.TOLD  # the AI could not read it; the volunteer entered it
    assert e["s479.third"].source == ledger.CALCULATED and e["s479.third"].value == "2026-07-15"
    assert e["ledger.maximum"].source == ledger.VERIFIED and e["ledger.maximum"].source_line.startswith("Source:")
    assert e["ledger.release_not_automatic"].source_line == \
        knowledge.get("undertrial_bail.md", "Who applies under Section 479").source_line
    assert ledger.unresolved(list(e.values())) == []


def test_volunteer_correction_is_told_not_ai():
    facts = practice_facts(custody_began=date(2024, 3, 16))
    e = entries_by_fact(ledger.undertrial(facts, drafts.recalculate(facts), AI_READ, ai_checked=True))
    assert e["fact.custody_began"].source == ledger.TOLD


def test_unchecked_ai_values_are_not_labelled_checked():
    facts = practice_facts()
    e = entries_by_fact(ledger.undertrial(facts, drafts.recalculate(facts), AI_READ, ai_checked=False))
    assert e["fact.custody_began"].source == ledger.TOLD


def test_legal_points_without_a_source_are_unresolved():
    facts = practice_facts(more_than_one_section=True, section_typed="406")
    open_points = ledger.unresolved(ledger.undertrial(facts, drafts.recalculate(facts)))
    assert {e.fact for e in open_points} == {"ledger.section479_2", "ledger.deciding_question"}
    assert all(e.source_line == "" for e in open_points)


def test_general_uncovered_issue_is_unresolved_covered_is_verified():
    reading, wages, _ = summarise(WAGES_ANSWER, WAGES)
    e = ledger.general(wages, reading.facts, general.check_eligibility(wages.facts))
    issue = [x for x in e if x.fact == "ledger.issue"][0]
    assert (issue.value, issue.source) == ("unpaid wages", ledger.UNRESOLVED)
    reading, upi, _ = summarise(UPI_ANSWER, UPI)
    issue = [x for x in ledger.general(upi, reading.facts, general.check_eligibility(upi.facts))
             if x.fact == "ledger.issue"][0]
    assert issue.source == ledger.VERIFIED and "Source: Moneylife" in issue.source_line


def test_general_facts_answers_and_precautions():
    raw = dict(UPI_ANSWER, money_lost_online=yn("yes", "words not in the notes"))
    reading = general.check_general_answer(raw, UPI)
    g = general.build_facts(reading, [("Was the card blocked?", "Not yet")], [], dict(reading.facts, sc_st=False),
                            date(2026, 11, 4))
    e = ledger.general(g, reading.facts, general.check_eligibility(g.facts))
    by = {x.fact: x for x in e}
    assert by["ledger.f.woman"].source == ledger.AI_CHECKED
    assert by["ledger.f.sc_st"].source == ledger.TOLD  # answered by the volunteer
    assert by["ledger.f.money_lost_online"].source == ledger.PRECAUTION
    assert any(x.fact == "ledger.answer" and x.source == ledger.TOLD for x in e)
    assert any(x.fact == "ledger.urgent" and x.value == "Call 1930 now." for x in e)
    assert by["ledger.legal_aid"].source == ledger.CALCULATED


def test_ledger_saved_with_case_and_shown(monkeypatch, tmp_path):
    original_submit = store.submit
    monkeypatch.setattr(store, "submit", lambda *a, **k: original_submit(*a, base=tmp_path, **k))
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: llm.NotesReading(practice_answer(), notes, {}, "m"))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_area(key="f_notes").set_value(NOTES)
    next(b for b in at.button if b.label == "Read notes").click().run()
    at.date_input(key="q-offence_date").set_value(date(2024, 2, 15))
    next(b for b in at.button if b.label == "Next").click().run()
    at.checkbox(key="f_checked").check().run()
    next(b for b in at.button if b.label == "Make draft").click().run()
    shown = " ".join(m.value for m in at.markdown)
    assert "read from notes by AI, checked by volunteer" in shown and "calculated by rule-based code" in shown
    at.button(key="send-f").click().run()
    [record] = store.list_pending(tmp_path)
    sources = {e["fact"]: e["source"] for e in record["ledger"]}
    assert sources["fact.custody_began"] == "ai_checked" and sources["fact.offence_date"] == "told"
