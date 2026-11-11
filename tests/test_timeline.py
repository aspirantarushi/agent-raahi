"""Next-step timelines for approved cases."""

import functools
import subprocess
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import drafts
import general
import knowledge
import store
import timeline
from test_drafts import practice_facts
from test_general import UPI, UPI_ANSWER, summarise

ROOT = Path(__file__).resolve().parent.parent
APPROVED_ON = date(2026, 11, 3)
TODAY = date(2026, 11, 4)


def approve_undertrial(base, approved_on=APPROVED_ON, **changes):
    facts = practice_facts(**changes)
    text = drafts.make_undertrial_draft(facts, drafts.recalculate(facts))
    case_id = store.submit(text, facts, base=base)
    store.approve(case_id, base=base, approved_on=approved_on)
    return case_id


def steps(case_id, base):
    return {s.id: s for s in timeline.steps_of(timeline.load(case_id, base))}


def source(entry):
    return knowledge.get(*entry).source_line


# ---------- the practice undertrial case ----------

def test_practice_undertrial_timeline(tmp_path):
    case_id = approve_undertrial(tmp_path)  # has a legal aid lawyer: no DLSA steps
    s = steps(case_id, tmp_path)
    assert list(s) == ["s479-note", "s479-third", "s479-half", "s479-ask", "s479-court",
                       "handoff-submitted", "handoff-acknowledged"]

    assert s["s479-note"].title == "Note given to the DLSA / jail legal aid clinic"
    assert (s["s479-note"].due, s["s479-note"].label()) == ("2026-11-10", timeline.SUGGESTED_LABEL)

    third, half = s["s479-third"], s["s479-half"]
    assert (third.due, third.kind, third.label()) == ("2026-07-15", timeline.LEGAL,
                                                      "eligibility date, not a deadline")
    assert (half.due, half.kind) == ("2027-09-15", timeline.LEGAL)
    assert third.source_line == half.source_line == source(timeline.S479_ENTRY)

    ask = s["s479-ask"]  # one-third is already reached, so asking is a suggested follow-up
    assert ask.title == "Ask whether the jail superintendent has applied"
    assert (ask.due, ask.label()) == ("2026-11-10", timeline.SUGGESTED_LABEL)
    assert ask.source_line == source(timeline.WHO_APPLIES_ENTRY)

    court = s["s479-court"]
    assert court.title == "Next court date" and court.due is None and court.kind == timeline.ENTERED

    # The one-third date has passed: reached, never "overdue" (it is not a deadline)
    assert timeline.is_reached(third, TODAY) and not timeline.is_overdue(third, TODAY)
    assert not timeline.is_reached(half, TODAY) and not timeline.is_overdue(half, TODAY)
    assert timeline.next_due(list(s.values()), TODAY).id == "s479-note"  # a task, not the reached date

    # The volunteer enters the next court date
    timeline.set_due(case_id, "s479-court", date(2026, 12, 2), "VA", base=tmp_path)
    assert steps(case_id, tmp_path)["s479-court"].label() == timeline.ENTERED_LABEL


def test_ask_superintendent_on_the_first_legal_date_when_still_ahead(tmp_path):
    case_id = approve_undertrial(tmp_path, custody_began=date(2026, 1, 10), offence_date=date(2026, 1, 5))
    ask = steps(case_id, tmp_path)["s479-ask"]
    assert (ask.due, ask.kind) == ("2028-05-10", timeline.LEGAL)  # one-third of 84 months = 28 months


def test_previously_convicted_has_no_one_third_step(tmp_path):
    case_id = approve_undertrial(tmp_path, never_convicted=False)
    assert steps(case_id, tmp_path)["s479-third"].status == timeline.NOT_NEEDED


def test_legal_dates_cannot_be_changed(tmp_path):
    case_id = approve_undertrial(tmp_path)
    with pytest.raises(ValueError, match="comes from the law"):
        timeline.set_due(case_id, "s479-half", date(2026, 12, 1), "VA", base=tmp_path)


# ---------- a DLSA application refused, then appealed ----------

def test_dlsa_application_refused_then_appealed(tmp_path):
    case_id = approve_undertrial(tmp_path, lawyer="None")  # the draft included the DLSA application
    s = steps(case_id, tmp_path)
    assert ["dlsa-submitted", "dlsa-decision", "dlsa-lawyer", "dlsa-refused", "dlsa-appeal"] == \
        [k for k in s if k.startswith("dlsa")]
    assert s["dlsa-decision"].due is None
    assert s["dlsa-decision"].source_line == source(timeline.DECISION_ENTRY)
    assert s["dlsa-appeal"].status == timeline.NOT_NEEDED

    timeline.mark_done(case_id, "dlsa-submitted", date(2026, 11, 5), "Volunteer A", base=tmp_path)
    s = steps(case_id, tmp_path)
    decision = s["dlsa-decision"]
    assert (decision.due, decision.kind, decision.label()) == ("2026-11-12", timeline.LEGAL, "legal date")

    timeline.mark_done(case_id, "dlsa-refused", date(2026, 11, 12), "Volunteer A", base=tmp_path)
    s = steps(case_id, tmp_path)
    assert s["dlsa-decision"].status == timeline.DONE
    assert s["dlsa-lawyer"].status == timeline.NOT_NEEDED
    appeal = s["dlsa-appeal"]
    assert appeal.title == "Appeal to the Chairman" and appeal.status == timeline.TO_DO
    assert appeal.source_line == source(timeline.REFUSED_ENTRY)
    assert (appeal.due, appeal.label()) == ("2026-11-19", timeline.SUGGESTED_LABEL)  # no time limit in our files

    timeline.set_due(case_id, "dlsa-appeal", date(2026, 11, 20), "Supervisor A2", base=tmp_path)
    timeline.mark_done(case_id, "dlsa-appeal", date(2026, 11, 18), "Volunteer A", base=tmp_path)
    appeal = steps(case_id, tmp_path)["dlsa-appeal"]
    assert (appeal.status, appeal.done_on, appeal.done_by) == (timeline.DONE, "2026-11-18", "Volunteer A")

    events = [(e["event"], e["by"]) for e in audit.read_record(case_id, base=tmp_path)["events"]]
    assert events[-4:] == [
        ("step done: Application submitted to the DLSA", "Volunteer A"),
        ("step done: Refused", "Volunteer A"),
        ("date set: Appeal to the Chairman", "Supervisor A2"),
        ("step done: Appeal to the Chairman", "Volunteer A"),
    ]


def test_dlsa_lawyer_assigned_records_meeting_and_documents(tmp_path):
    case_id = approve_undertrial(tmp_path, lawyer="None")
    timeline.mark_done(case_id, "dlsa-submitted", date(2026, 11, 5), "VA", base=tmp_path)
    timeline.mark_done(case_id, "dlsa-lawyer", date(2026, 11, 10), "VA",
                       {"first meeting": "2026-11-14", "documents handed over": "yes"}, base=tmp_path)
    s = steps(case_id, tmp_path)
    assert s["dlsa-lawyer"].details == {"first meeting": "2026-11-14", "documents handed over": "yes"}
    assert s["dlsa-refused"].status == s["dlsa-appeal"].status == timeline.NOT_NEEDED
    with pytest.raises(ValueError, match="only needed if the application is refused"):
        timeline.mark_done(case_id, "dlsa-appeal", date(2026, 11, 12), "VA", base=tmp_path)
    last = audit.read_record(case_id, base=tmp_path)["events"][-1]
    assert last["details"] == "on 2026-11-10; first meeting: 2026-11-14; documents handed over: yes"


# ---------- general summaries ----------

def test_general_case_steps_are_its_next_steps_with_volunteer_dates(tmp_path):
    reading, facts, text = summarise(UPI_ANSWER, UPI)
    case_id = store.submit(text, facts, base=tmp_path)
    store.approve(case_id, base=tmp_path, approved_on=APPROVED_ON)
    s = timeline.steps_of(timeline.load(case_id, tmp_path))
    s = [x for x in s if not x.id.startswith("handoff-")]
    assert [x.title for x in s] == general.case_next_steps(facts)
    assert all(x.due is None and x.kind == timeline.SUGGESTED for x in s)
    timeline.set_due(case_id, s[0].id, date(2026, 11, 6), "VA", base=tmp_path)
    first = timeline.steps_of(timeline.load(case_id, tmp_path))[0]
    assert first.label() == "suggested follow-up, not a legal deadline"


# ---------- rules for every change ----------

def test_who_did_it_is_required_and_cleaned(tmp_path):
    case_id = approve_undertrial(tmp_path)
    with pytest.raises(ValueError, match="who did this"):
        timeline.mark_done(case_id, "s479-note", TODAY, "  ", base=tmp_path)
    timeline.mark_done(case_id, "s479-note", TODAY, "VA 9876543210", base=tmp_path)
    assert "9876543210" not in steps(case_id, tmp_path)["s479-note"].done_by


def test_every_change_goes_into_the_audit_record(tmp_path):
    case_id = approve_undertrial(tmp_path)
    timeline.mark_done(case_id, "s479-note", TODAY, "VA", base=tmp_path)
    timeline.reopen(case_id, "s479-note", "VA", base=tmp_path)
    timeline.mark_not_needed(case_id, "s479-court", "VA", "case disposed", base=tmp_path)
    events = [e["event"] for e in audit.read_record(case_id, base=tmp_path)["events"]]
    assert events[-4:] == ["timeline created", "step done: Note given to the DLSA / jail legal aid clinic",
                           "step reopened: Note given to the DLSA / jail legal aid clinic",
                           "step not needed: Next court date"]


def test_due_this_week(tmp_path):
    case_id = approve_undertrial(tmp_path)
    items = timeline.due_this_week(TODAY, base=tmp_path)
    assert [(c, s.id, state) for c, s, state in items] == [
        (case_id, "s479-note", "due"),   # 10 November 2026
        (case_id, "s479-ask", "due"),    # 10 November 2026
    ]  # the one-third date (15 July 2026) has passed: it is not a task, so it is not listed
    assert all(s.id != "s479-half" for _, s, _ in items)  # 2027 is not this week


def test_timelines_are_kept_out_of_git():
    assert subprocess.run(["git", "check-ignore", "-q", "timelines/U-20261104-k7f1.json"], cwd=ROOT).returncode == 0


# ---------- on "My cases" ----------

@pytest.fixture
def my_cases(monkeypatch, tmp_path):
    original_load = timeline.load
    monkeypatch.setattr(timeline, "load", lambda case_id, base=tmp_path: original_load(case_id, base))
    for module, name in [(store, "list_cases"), (timeline, "due_this_week"), (timeline, "mark_done"),
                         (timeline, "mark_not_needed"), (timeline, "set_due"), (timeline, "reopen")]:
        monkeypatch.setattr(module, name, functools.partial(getattr(module, name), base=tmp_path))
    return tmp_path


def open_my_cases():
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.button(key="nav-tracker").click().run()
    for b in [b for b in at.button if str(b.key).startswith("tr-open-")]:  # open each case card
        at.button(key=b.key).click().run()
    assert not at.exception, at.exception[0].stack_trace
    return at


def test_my_cases_shows_due_this_week_and_overdue_steps(my_cases):
    # The screen uses the real date, so approve "today": with a fixed date the first follow-up step
    # turned overdue (red) once the calendar passed it, and this test failed for no real reason.
    approve_undertrial(my_cases, approved_on=date.today())
    at = open_my_cases()
    assert at.subheader[0].value == "Due this week"
    errors = [e.value for e in at.error]
    warnings = [w.value for w in at.warning]
    assert not any("One-third" in e for e in errors)  # an eligibility date is never red
    assert any(w.startswith("Reached on 15 July 2026: check whether an application has been made")
               and "One-third (personal bond) date" in w for w in warnings)
    assert any(s.value.startswith("**Next:** Note given to the DLSA") for s in at.success)
    captions = " ".join(c.value for c in at.caption)
    assert source(timeline.S479_ENTRY) in captions


def test_my_cases_update_a_step(my_cases):
    case_id = approve_undertrial(my_cases)
    at = open_my_cases()
    at.selectbox(key=f"tl-step-{case_id}").set_value("s479-note").run()
    at.radio(key=f"tl-action-{case_id}").set_value("Mark done").run()
    at.text_input(key=f"tl-by-{case_id}").set_value("Volunteer A")
    at.button(key=f"tl-save-{case_id}").click().run()
    assert not at.exception
    assert any("Saved" in s.value for s in at.success)
    note = steps(case_id, my_cases)["s479-note"]
    assert note.status == timeline.DONE and note.done_by == "Volunteer A"


# ---------- eligibility dates are not deadlines; the "ask" step is ----------

def test_ask_step_turns_red_when_past_its_date(tmp_path):
    case_id = approve_undertrial(tmp_path)
    s = steps(case_id, tmp_path)
    later = date(2026, 11, 11)  # the day after the ask step's suggested date
    assert timeline.is_overdue(s["s479-ask"], later)
    assert not timeline.is_overdue(s["s479-third"], later)
    items = {(step.id, state) for _, step, state in timeline.due_this_week(later, base=tmp_path)}
    assert ("s479-ask", "overdue") in items
    assert not any(i == "s479-third" for i, _ in items)


def test_eligibility_date_this_week_is_listed_in_amber(tmp_path):
    case_id = approve_undertrial(tmp_path, custody_began=date(2024, 7, 2), offence_date=date(2024, 7, 1))
    third = steps(case_id, tmp_path)["s479-third"]
    assert third.due == "2026-11-02"
    items = timeline.due_this_week(date(2026, 10, 30), base=tmp_path)
    assert ("s479-third", "eligibility") in {(s.id, state) for _, s, state in items}


def test_reached_eligibility_date_marked_done_is_no_longer_highlighted(tmp_path):
    case_id = approve_undertrial(tmp_path)
    timeline.mark_done(case_id, "s479-third", TODAY, "VA", base=tmp_path)
    third = steps(case_id, tmp_path)["s479-third"]
    assert not timeline.is_reached(third, TODAY) and not timeline.is_overdue(third, TODAY)


def test_appeal_date_stays_a_suggestion(tmp_path):
    case_id = approve_undertrial(tmp_path, lawyer="None")
    timeline.mark_done(case_id, "dlsa-submitted", date(2026, 11, 5), "VA", base=tmp_path)
    timeline.mark_done(case_id, "dlsa-refused", date(2026, 11, 12), "VA", base=tmp_path)
    appeal = steps(case_id, tmp_path)["dlsa-appeal"]
    assert appeal.label() == timeline.SUGGESTED_LABEL and appeal.due_editable
