"""Safe abstention: five deliberately difficult fictional cases. The agent must not conclude."""

from datetime import date

from streamlit.testing.v1 import AppTest

import consistency
import general
import llm
from test_intake import NOTES, field, practice_answer

FORM = {"custody_began": date(2024, 3, 15), "offence_date": date(2024, 2, 15), "today": date(2026, 11, 2),
        "law": "IPC", "section": "380", "never_convicted": True, "other_cases_pending": False,
        "delay_days_by_accused": 0, "answer": "", "lawyer": "Legal aid lawyer"}

# Fictional notes (not real people).
NOTES_ANOTHER_CASE = ("Practice case (fictional). Her brother was arrested on 15 March 2024. He is charged under "
                      "IPC 380. No other cases are pending against him. Later his mother said another case is "
                      "pending against him in the Gaya court.")
NOTES_CONVICTED = ("Practice case (fictional). He was arrested on 15 March 2024 under IPC 380. His sister says he "
                   "has never been convicted. The jail record shows he was convicted in 2019 for theft and "
                   "served six months.")


def reasons(problems):
    return [p.reason for p in problems]


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def results_shown(at) -> bool:
    return any("One-third" in m.value for m in at.markdown)


def open_form():
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="case_type").set_value("Undertrial").run()
    return at


def errors(at):
    return " ".join(e.value for e in at.error)


# ---------- case 1: custody began before the offence ----------

def test_case1_custody_before_offence():
    problems = consistency.undertrial_problems(dict(FORM, offence_date=date(2024, 5, 1)))
    assert reasons(problems) == ["offence_after_custody"]
    at = open_form()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 5, 1))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15))
    at.date_input(key="f_today").set_value(date(2026, 11, 2)).run()
    ok(at)
    assert "Cannot conclude yet: the offence date (2024-05-01) is after the date custody began (2024-03-15)." in errors(at)
    assert not results_shown(at) and not any(b.label == "Make draft" for b in at.button)
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15)).run()  # corrected
    assert results_shown(at)


# ---------- case 2: "no other cases", then "another case" ----------

def test_case2_another_case_mentioned_later(monkeypatch):
    assert reasons(consistency.undertrial_problems(FORM, notes=NOTES_ANOTHER_CASE)) == ["other_cases"]
    assert consistency.undertrial_problems(dict(FORM, other_cases_pending=True), notes=NOTES_ANOTHER_CASE) == []
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    answer = practice_answer(
        custody_began=field("2024-03-15", "Her brother was arrested on 15 March 2024."),
        other_cases_pending=field("no", "No other cases are pending against him."),
        sections=[{"law": "IPC", "section": "380", "quote": "He is charged under IPC 380."}],
        previously_convicted=field(None, None), delay_by_accused=field("no", "No other cases are pending"),
        lawyer=field(None, None), today_date=field(None, None))
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: llm.NotesReading(answer, notes, {}, "m"))
    at = open_form()
    at.text_area(key="f_notes").set_value(NOTES_ANOTHER_CASE)
    next(b for b in at.button if b.label == "Read notes").click().run()
    next(b for b in at.button if b.label == "Skip the rest and check the form").click().run()
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.checkbox(key="f_checked").check().run()
    ok(at)
    assert "the notes mention another case" in errors(at) and not results_shown(at)


# ---------- case 3: the AI's reading and the volunteer's answer disagree ----------

def test_case3_ai_and_volunteer_disagree(monkeypatch):
    problems = consistency.undertrial_problems(dict(FORM, custody_began=date(2023, 3, 15),
                                                    offence_date=date(2023, 2, 15)),
                                               ai_read={"custody_began": date(2024, 3, 15)})
    assert reasons(problems) == ["ai_vs_volunteer"] and problems[0].confirm_fact == "custody_began"
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: llm.NotesReading(practice_answer(), notes, {}, "m"))
    at = open_form()
    at.text_area(key="f_notes").set_value(NOTES)
    next(b for b in at.button if b.label == "Read notes").click().run()  # "February 2024": the month decides, no day asked
    at.date_input(key="f_custody").set_value(date(2023, 3, 15))  # the volunteer changes the AI's reading
    at.checkbox(key="f_checked").check().run()
    ok(at)
    assert "the notes say Date custody began is \"2024-03-15\", but the form says \"2023-03-15\"" in errors(at)
    assert not results_shown(at)
    at.checkbox(key="confirm-custody_began").check().run()  # the volunteer checked: the form is right
    assert results_shown(at)


# ---------- case 4: "never convicted", but the notes mention a conviction ----------

def test_case4_conviction_mentioned():
    problems = consistency.undertrial_problems(FORM, notes=NOTES_CONVICTED)
    assert reasons(problems) == ["convictions"]
    assert "convicted in 2019" in problems[0].params["quote"]
    assert consistency.undertrial_problems(dict(FORM, never_convicted=False), notes=NOTES_CONVICTED) == []


# ---------- case 5: key facts missing ----------

def test_case5_key_facts_missing():
    assert reasons(consistency.undertrial_problems(dict(FORM, custody_began=None))) == ["missing_custody"]
    at = open_form()
    at.text_input(key="f_section").set_value("380").run()
    ok(at)
    assert "Cannot conclude yet: the date custody began is not known." in errors(at)
    empty = general.GeneralFacts(person="", what_happened=[], timeline=[], coming_dates=[], issues=[], sections=[],
                                 documents_held=[], answers=[], still_to_ask=[], facts={}, today="2026-11-04")
    assert reasons(consistency.general_problems(empty)) == ["general_unclear"]


# ---------- no false alarms on the practice cases ----------

def test_practice_cases_have_no_problems():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    hindi = (root / "case_notes_hi.txt").read_text(encoding="utf-8")
    assert consistency.undertrial_problems(FORM, ai_read={"custody_began": date(2024, 3, 15)}, notes=NOTES) == []
    assert consistency.undertrial_problems(FORM, notes=hindi) == []  # "कोई दूसरा केस लंबित नहीं है"


def test_future_dates():
    assert "custody_future" in reasons(consistency.undertrial_problems(dict(FORM, custody_began=date(2027, 1, 1))))
