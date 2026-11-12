"""Readiness checklist: required fields per draft type, "cannot obtain", the send label, the gaps."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import drafts
import general
import readiness
import store
from test_drafts import practice_facts
from test_general import UPI, UPI_ANSWER, WAGES, WAGES_ANSWER, summarise
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

DETAILS = {"court": "Saket Court", "cnr": "DLST010012342024", "fir": "123/2024", "police_station": "Saket",
           "jail": "Tihar", "district": "South Delhi"}


def note_items(details=None, cannot=None, skipped=(), **changes):
    facts = practice_facts(**changes)
    return readiness.section479_items(facts, drafts.recalculate(facts), details or {}, skipped, cannot)


def by_key(items):
    return {i.key: i for i in items}


def test_section479_ready_with_every_field():
    items = note_items(DETAILS)
    assert readiness.is_ready(items)
    assert readiness.button_label(items) == "Ready for review"


def test_section479_missing_case_details():
    items = note_items({})
    assert {i.key for i in readiness.gaps(items)} == {"court", "cnr", "fir", "jail", "district"}
    assert readiness.button_label(items) == "Not ready: 5 items missing"


def test_unknown_answers_and_two_sections_are_uncertain():
    items = by_key(note_items(DETAILS, skipped={"never_convicted"}, more_than_one_section=True))
    assert items["previous_convictions"].status == "uncertain"
    assert items["one_section"].status == "uncertain"


def test_deciding_question_must_be_answered_and_confirmed():
    items = by_key(note_items(DETAILS, section_typed="406"))
    assert items["deciding_question"].status == "uncertain"
    items = by_key(note_items(DETAILS, section_typed="406", answer="No", question_answered=True))
    assert items["deciding_question"].status == "present"


def test_cannot_obtain_with_a_reason_counts_as_ready():
    details = dict(DETAILS, cnr="")
    assert not readiness.is_ready(note_items(details))
    items = note_items(details, cannot={"cnr": "Case not yet on eCourts"})
    assert readiness.is_ready(items)
    assert by_key(items)["cnr"].status == "cannot obtain"
    assert "Case not yet on eCourts" in readiness.gaps_block(items)


def test_cannot_obtain_needs_a_reason():
    items = note_items(dict(DETAILS, cnr=""), cannot={"cnr": "  "})
    assert not readiness.is_ready(items)


def test_dlsa_application_items():
    items = by_key(readiness.dlsa_items({"district": "South Delhi"}))
    assert items["dlsa_district"].status == "present" and items["dlsa_case_number"].status == "missing"


def test_general_summary_items():
    _, facts, _ = summarise(WAGES_ANSWER, WAGES)
    items = by_key(readiness.general_items(facts, general.check_eligibility(facts.facts)))
    assert items["what_happened"].status == "present" and items["legal_aid_decided"].status == "present"
    assert items["questions_answered"].status == "uncertain"  # 2 questions still open


def test_gaps_listed_at_top_of_draft_after_the_draft_line():
    facts = practice_facts()
    text = drafts.make_undertrial_draft(facts, drafts.recalculate(facts))
    out = readiness.add_gaps_to_draft(text, note_items({}))
    lines = out.splitlines()
    assert lines[0] == drafts.DRAFT_HEADER  # the hard rule still holds
    assert lines[2] == "NOT READY FOR REVIEW: 5 items missing or uncertain"
    assert readiness.add_gaps_to_draft(text, note_items(DETAILS)) == text  # nothing to list when ready


def test_hindi_gaps_block_keeps_hindi_header_lines():
    facts = practice_facts()
    text = drafts.make_undertrial_draft(facts, drafts.recalculate(facts), code="hi")
    lines = readiness.add_gaps_to_draft(text, note_items({}), "hi").splitlines()
    assert lines[0] == drafts.DRAFT_HEADER and lines[2].startswith("हिंदी अनुवाद की जाँच")
    assert lines[4].startswith("जाँच के लिए तैयार नहीं: 5")


def test_case_details_fill_the_blanks():
    facts = practice_facts()
    text = readiness.fill_details(drafts.make_undertrial_draft(facts, drafts.recalculate(facts)), DETAILS)
    assert "- Court and case number (CNR): Saket Court, CNR DLST010012342024" in text
    assert "- FIR number and police station: 123/2024, Saket" in text
    assert "lodged in Tihar" in text and "District Legal Services Authority, South Delhi" in text
    assert not store.drafts.personal_details_found(text)


def test_screen_checklist_and_send_label(monkeypatch, tmp_path):
    original_submit = store.submit
    monkeypatch.setattr(store, "submit", lambda *a, **k: original_submit(*a, base=tmp_path, **k))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15))
    at.checkbox(key="f_never").check().run()
    calculate(at.run())  # "Calculate the dates"
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    next(b for b in at.button if b.label == "Make draft").click().run()
    assert at.button(key="send-f").label == "Send to supervisor — Not ready: 5 items missing"
    for field, value in DETAILS.items():
        at.text_input(key=f"f-detail-{field}").set_value(value)
    at.run()
    assert at.button(key="send-f").label == "Send to supervisor — Ready for review"
    assert "Saket Court, CNR DLST010012342024" in at.session_state["shown_drafts"][0]
    at.button(key="send-f").click().run()
    [record] = store.list_pending(tmp_path)
    assert {r["status"] for r in record["readiness"]} == {"present"}


def test_screen_cannot_obtain(monkeypatch):
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15)).run()
    calculate(at.run())  # "Calculate the dates"
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    next(b for b in at.button if b.label == "Make draft").click().run()
    for field, value in DETAILS.items():
        if field != "cnr":
            at.text_input(key=f"f-detail-{field}").set_value(value)
    at.run()
    at.checkbox(key="cant-f-cnr").check().run()
    at.text_input(key="cantr-f-cnr").set_value("Not yet on eCourts").run()
    assert at.button(key="send-f").label == "Send to supervisor — Ready for review"
    assert "Could not be obtained (reason given by the volunteer):\n- CNR number: Not yet on eCourts" in at.session_state["shown_drafts"][0]
