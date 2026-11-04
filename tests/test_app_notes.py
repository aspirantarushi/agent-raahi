"""The New case screen with pasted notes, using a pretend AI (no internet, no key)."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import llm
from test_intake import NOTES, practice_answer

APP = "../app.py"


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def button(at, label):
    return next(b for b in at.button if b.label == label)


@pytest.fixture
def pretend_ai(monkeypatch):
    calls = []

    def fake_read(notes):
        calls.append(notes)
        return practice_answer(), notes, {}

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", fake_read)
    return calls


def test_notes_fill_the_practice_case(pretend_ai):
    at = AppTest.from_file(APP, default_timeout=20).run()
    ok(at)
    at.text_area(key="f_notes").set_value(NOTES)
    button(at, "Read notes").click().run()
    ok(at)

    # One missing fact is asked: the offence date (the notes only say February 2024).
    assert any("On what date was the offence said to have happened?" in m.value for m in at.markdown)
    assert any("February 2024" in c.value for c in at.caption)
    at.date_input(key="q-offence_date").set_value(date(2024, 2, 15))
    button(at, "Next").click().run()
    ok(at)

    # The form is filled in for the volunteer to check.
    assert at.text_input(key="f_section").value == "380"
    assert at.date_input(key="f_custody").value == date(2024, 3, 15)
    assert at.date_input(key="f_offence_date").value == date(2024, 2, 15)
    assert at.date_input(key="f_today").value == date(2026, 11, 2)
    assert at.checkbox(key="f_never").value is True
    assert at.checkbox(key="f_other").value is False

    # No dates until the volunteer has checked every field.
    assert not any("One-third" in m.value for m in at.markdown)
    at.checkbox(key="f_checked").check().run()
    ok(at)
    results = " ".join(m.value for m in at.markdown)
    assert "15 July 2026" in results and "reached" in results
    assert "15 September 2027" in results
    assert at.radio(key="f_lawyer").value == "Legal aid lawyer"


def test_dont_know_skips_a_question(pretend_ai):
    at = AppTest.from_file(APP, default_timeout=20).run()
    at.text_area(key="f_notes").set_value(NOTES)
    button(at, "Read notes").click().run()
    button(at, "Don't know").click().run()
    ok(at)
    assert at.date_input(key="f_offence_date").value is None
    assert any("Still not known: Date of the offence" in w.value for w in at.warning)


def test_no_key_the_form_still_works(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    at = AppTest.from_file(APP, default_timeout=20).run()
    ok(at)
    assert any("not set up" in i.value for i in at.info)
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_custody").set_value(date(2024, 3, 15))
    at.date_input(key="f_today").set_value(date(2026, 11, 2))
    at.checkbox(key="f_never").check().run()
    ok(at)
    assert "15 July 2026" in " ".join(m.value for m in at.markdown)


def test_ai_failure_shows_message_and_form_works(monkeypatch):
    def fail(notes):
        raise llm.AIUnavailable("AI reading failed: the free-tier limit was reached; try again later (error 429).")

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", fail)
    at = AppTest.from_file(APP, default_timeout=20).run()
    at.text_area(key="f_notes").set_value(NOTES)
    button(at, "Read notes").click().run()
    ok(at)
    assert any("free-tier limit" in e.value and "by hand" in e.value for e in at.error)
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_custody").set_value(date(2024, 3, 15))
    at.date_input(key="f_today").set_value(date(2026, 11, 2))
    at.run()
    ok(at)
    assert "15 September 2027" in " ".join(m.value for m in at.markdown)


def test_empty_reading_asks_every_fact_in_intake_order(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: ({}, notes, {}))
    at = AppTest.from_file(APP, default_timeout=20).run()
    at.text_area(key="f_notes").set_value("Nothing useful here.")
    button(at, "Read notes").click().run()

    def asked():
        ok(at)
        return next(m.value for m in at.markdown if m.value.startswith("**") and m.value.endswith("?**"))

    assert asked() == "**On what date did custody begin (the date of arrest)?**"
    at.date_input(key="q-custody_began").set_value(date(2024, 3, 15))
    button(at, "Next").click().run()
    assert asked() == "**On what date was the offence said to have happened?**"
    at.date_input(key="q-offence_date").set_value(date(2024, 2, 15))
    button(at, "Next").click().run()
    assert asked() == "**Which sections are written on the FIR or chargesheet?**"
    at.text_input(key="q-section").set_value("406")
    button(at, "Next").click().run()
    assert asked() == "**Has the person ever been convicted of any offence before?**"
    at.radio(key="q-never").set_value("Not sure")
    button(at, "Next").click().run()  # "Not sure" counts as "Don't know"
    assert asked() == "**Are any other cases pending against them?**"
    at.radio(key="q-other_cases_pending").set_value("No")
    button(at, "Next").click().run()
    assert asked().startswith("**Was the person a clerk or employee")  # IPC 406's deciding question
    button(at, "Don't know").click().run()
    assert asked() == ("**Has the case been delayed because of the accused "
                       "(for example, their own adjournment requests)?**")
    at.radio(key="q-delay_days_by_accused").set_value("No")
    button(at, "Next").click().run()
    assert asked() == "**Does the person have a lawyer?**"
    at.radio(key="q-lawyer").set_value("None")
    button(at, "Next").click().run()
    ok(at)

    assert at.text_input(key="f_section").value == "406"
    assert at.checkbox(key="f_never").value is False  # not known: left unticked, and flagged
    warnings = " ".join(w.value for w in at.warning)
    assert "Never convicted" in warnings and "Answer to the deciding question" in warnings


def test_next_without_an_answer_stays_on_the_question(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: ({}, notes, {}))
    at = AppTest.from_file(APP, default_timeout=20).run()
    at.text_area(key="f_notes").set_value("Nothing useful here.")
    button(at, "Read notes").click().run()
    button(at, "Next").click().run()
    ok(at)
    assert any("7 to go" in h.value for h in at.subheader)
