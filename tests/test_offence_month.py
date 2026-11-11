"""Evaluation case 2: the notes give the month and year of the offence but not the day. The month decides
IPC or BNS: every day of June 2024 is before 1 July 2024 (IPC), every day of July 2024 is on or after it
(BNS). The day is never asked when the month and year are known.
Fake data only."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import drafts
import intake
import llm
import section479
from test_intake import field, practice_answer
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

CASE2 = (Path(__file__).resolve().parent.parent / "practice_stories" / "test_set" / "case02_old_ipc_maximum.txt"
         ).read_text(encoding="utf-8")


def extortion():
    [o] = section479.find_offences("IPC", "384")
    return o


def calc(**kw):
    base = dict(custody_began=date(2024, 8, 5), today=date(2026, 11, 4), never_convicted=True,
                other_cases_pending=False, more_than_one_section=False, delay_days_by_accused=0)
    return section479.calculate(extortion(), **{**base, **kw})


@pytest.mark.parametrize("quote, month", [("an offence in May 2024", "2024-05"), ("offence in December 2023", "2023-12"),
                                          ("अपराध मई 2024 में हुआ", "2024-05"), ("offence 2024 mai hua", None),
                                          ("in May", None), ("on 5 May 2024 or 2023", None)])
def test_month_and_year_from_the_notes(quote, month):
    assert intake.month_year(quote) == month


@pytest.mark.parametrize("month, decides", [("2024-05", True), ("2023-12", True), ("2024-06", True),
                                            ("2024-07", True), ("2024-08", True), (None, False), ("May", False)])
def test_the_month_and_year_always_decide(month, decides):
    assert (section479.month_law_date(month) is not None) == decides


def test_may_2024_uses_the_ipc_maximum_without_the_day():
    r = calc(offence_month="2024-05")
    assert (r.maximum.months, r.maximum.section) == (36, "IPC 384") and not r.lawyer_check
    assert (r.one_third.when, r.one_half.when) == (date(2025, 8, 5), date(2026, 2, 5))
    assert calc().maximum.months == 84 and calc().lawyer_check  # no month, no day: BNS, to be checked (as before)
    june, july = calc(offence_month="2024-06"), calc(offence_month="2024-07")
    assert (june.maximum.months, june.maximum.section) == (36, "IPC 384")  # every day of June 2024: before 1 July
    assert (july.maximum.months, july.maximum.section) == (84, "BNS 308(2)")  # every day of July 2024: on or after
    assert not june.lawyer_check


def test_the_day_is_never_asked_when_the_month_is_known():
    for month in ("2024-05", "2024-06", "2024-07", "2023-12"):
        assert "offence_date" not in intake.missing_facts({"offence_month": month})
    assert "offence_date" in intake.missing_facts({})  # no month either: asked


def test_draft_says_the_month_never_a_made_up_day():
    facts = drafts.UndertrialFacts(law_typed="IPC", section_typed="384", custody_began=date(2024, 8, 5),
                                   today=date(2026, 11, 4), never_convicted=True, other_cases_pending=False,
                                   more_than_one_section=False, question_answered=False, delay_days_by_accused=0,
                                   lawyer="Legal aid lawyer", offence_month="2024-05")
    result = drafts.recalculate(facts)
    assert result.maximum.months == 36
    text = drafts.make_undertrial_draft(facts, result)
    assert "IPC 384 (now BNS 308(2))" in text and "offence date not given" not in text
    assert "May 2024 (the day is not known)" in drafts.make_case_file("U-20261104-a123", facts, result, date(2026, 11, 4))
    assert drafts.UndertrialFacts.from_dict(facts.to_dict()).offence_month == "2024-05"


def test_case2_on_screen_no_day_asked_ipc_dates(monkeypatch):
    answer = practice_answer(
        custody_began=field("2024-08-05", "arrested on 5 August 2024"),
        offence_date=field(None, "an offence in May 2024"), today_date=field("2026-11-04", "4 November 2026"),
        sections=[{"law": "IPC", "section": "384", "quote": "IPC 384"}],
        lawyer=field("Legal aid lawyer", "legal aid lawyer"))
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: llm.NotesReading(answer, notes, {}, "m"))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_area(key="f_notes").set_value(CASE2)
    choose_language(at, "f_notes", language_of(CASE2))
    next(b for b in at.button if b.label == "Read notes").click().run()
    assert not any(b.key == "skip-offence_date" for b in at.button)  # the day is never asked: the month decides
    if any(b.key == "skip-all" for b in at.button):  # other facts this fake reading left out: skip them
        at.button(key="skip-all").click().run()
    at.session_state["f_today"] = date(2026, 11, 4)
    at.checkbox(key="f_checked").check().run()
    calculate(at)
    assert not at.exception, at.exception[0].stack_trace
    md = " ".join(m.value for m in at.markdown)
    assert "36 months, as per IPC 384" in md and "5 February 2026" in md  # the IPC maximum: one-half reached
    assert "84 months" not in md
    assert any("The notes give the month: May 2024" in c.value for c in at.caption)
