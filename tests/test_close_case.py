"""Close a case (supervisor only): approved cases, with a reason and a short note (no names); closed cases
are read-only, show "Closed", and can be reopened with a reason. Every close and reopen is in the audit
record with the supervisor's name. Fake data only."""

import time
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import audit
import store
import timeline
import tracker
from test_compliance import make


def approved_case(base=None, by="Volunteer A"):
    kw = {"base": base} if base else {}
    record = tracker.open_case("Undertrial", by, **kw)
    facts, text = make()
    store.submit(text, facts, case_id=record["id"], by=by, **kw)
    store.approve(record["id"], by="SK", **kw)
    return record["id"], record["code"]


def test_only_an_approved_case_can_be_closed(tmp_path):
    record = tracker.open_case("Undertrial", "Volunteer A", base=tmp_path)
    with pytest.raises(tracker.TrackerError, match="Only an approved case"):
        tracker.close_case(record["id"], "resolved", "", "SK", base=tmp_path)


@pytest.mark.parametrize("reason, note, message", [
    ("", "", "Choose why"), ("finished", "", "Choose why"),
    ("other", "", "short note"),
    ("resolved", "Ramesh got his money", "seems to contain a person's name"),
])
def test_close_needs_a_reason_and_a_note_without_names(tmp_path, reason, note, message):
    case_id, _ = approved_case(tmp_path)
    with pytest.raises(tracker.TrackerError, match=message):
        tracker.close_case(case_id, reason, note, "SK", base=tmp_path)


def test_a_closed_case_is_read_only_until_reopened(tmp_path):
    case_id, code = approved_case(tmp_path)
    tracker.close_case(case_id, "resolved", "the wages were paid", "SK", base=tmp_path)
    assert tracker.status_of(case_id, base=tmp_path) == tracker.CLOSED
    for change in (lambda: tracker.edit_case(case_id, "Volunteer B", note="x", base=tmp_path),
                   lambda: tracker.add_visit(case_id, date(2026, 11, 10), "Volunteer B", "phone call",
                                             learned="called back", base=tmp_path),
                   lambda: tracker.merge_facts(case_id, {"state": "Bihar"}, "Volunteer B", "x", base=tmp_path),
                   lambda: tracker.add_answers(case_id, [("q", "a")], "Volunteer B", base=tmp_path)):
        with pytest.raises(tracker.TrackerError, match="closed"):
            change()
    step = timeline.steps_of(timeline.load(case_id, tmp_path))[0]
    with pytest.raises(ValueError, match="closed"):
        timeline.set_due(case_id, step.id, date(2026, 12, 1), "Volunteer B", base=tmp_path)
    assert tracker.find_by_code(code, base=tmp_path)["id"] == case_id  # it can still be found and read
    with pytest.raises(tracker.TrackerError, match="already closed"):
        tracker.close_case(case_id, "resolved", "", "SK", base=tmp_path)
    tracker.reopen_case(case_id, "the person came back with a new problem", "SK2", base=tmp_path)
    assert tracker.status_of(case_id, base=tmp_path) == store.APPROVED
    tracker.add_visit(case_id, date(2026, 11, 10), "Volunteer B", "phone call", learned="called back",
                      base=tmp_path)  # changes allowed again


def test_reopen_needs_a_reason_without_names(tmp_path):
    case_id, _ = approved_case(tmp_path)
    with pytest.raises(tracker.TrackerError, match="not closed"):
        tracker.reopen_case(case_id, "x", "SK", base=tmp_path)
    tracker.close_case(case_id, "could not contact", "", "SK", base=tmp_path)
    with pytest.raises(tracker.TrackerError, match="Write why"):
        tracker.reopen_case(case_id, "  ", "SK", base=tmp_path)
    with pytest.raises(tracker.TrackerError, match="name"):
        tracker.reopen_case(case_id, "Sunita called again", "SK", base=tmp_path)


def test_close_and_reopen_are_in_the_audit_with_the_supervisors_name(tmp_path):
    case_id, _ = approved_case(tmp_path)
    tracker.close_case(case_id, "referred elsewhere", "sent to the labour office", "SK", base=tmp_path)
    tracker.reopen_case(case_id, "the labour office sent it back", "Asha R", base=tmp_path)
    tracker.close_case(case_id, "resolved", "", "Asha R", base=tmp_path)
    events = [(e["event"], e["by"], e.get("role"), e.get("details")) for e in audit.read_record(case_id, base=tmp_path)["events"]
              if "case" in e["event"]]
    assert events[0][0] == "case opened (intake started)"  # kept when the case was sent
    events = events[1:]
    assert events == [("case closed", "SK", "supervisor", "reason: referred elsewhere; note: sent to the labour office"),
                      ("case reopened", "Asha R", "supervisor", "reason: the labour office sent it back"),
                      ("case closed", "Asha R", "supervisor", "reason: resolved")]
    row = audit.summary_row(audit.read_record(case_id, base=tmp_path))
    assert row["status"] == "closed" and row["decision_by"] == "SK (supervisor)"  # the approval stays the decision
    assert len(tracker.load(case_id, base=tmp_path)["closures"]) == 2


# ---------- on screen ----------

def supervisor(monkeypatch, **state):
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "Supervisor"
    for k, v in {"supervisor_ok": True, "supervisor_name": "SK", "sup_last_active": time.time(), **state}.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, at.exception[0].stack_trace
    return at


def test_supervisor_closes_and_reopens_on_screen(monkeypatch):
    case_id, code = approved_case()
    at = supervisor(monkeypatch, **{"aud-open": case_id})
    at.text_input(key="aud-q").set_value(code).run()
    assert at.button(key=f"close-go-{case_id}").disabled                     # a reason first
    at.selectbox(key=f"close-reason-{case_id}").set_value("resolved")
    at.text_input(key=f"close-note-{case_id}").set_value("the wages were paid").run()
    at.button(key=f"close-go-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert tracker.status_of(case_id) == tracker.CLOSED
    assert at.dataframe[0].value.iloc[0]["Status"] == "Closed"               # the audit table
    assert any("Closed: Resolved · the wages were paid · by SK" in m.value for m in at.markdown)
    at.text_input(key=f"reopen-reason-{case_id}").set_value("a new problem came up")
    at.button(key=f"reopen-go-{case_id}").click().run()
    assert tracker.status_of(case_id) == store.APPROVED


def test_tracker_shows_closed_read_only_and_continuing_is_refused(monkeypatch):
    case_id, code = approved_case()
    tracker.close_case(case_id, "person withdrew", "", "SK")
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "My cases"
    at.run()
    at.button(key=f"tr-open-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    card = " ".join(m.value for m in at.markdown)
    assert "Closed" in card and not any(b.key == f"tr-edit-{case_id}" for b in at.button)
    assert not any(str(b.key).startswith(f"vis-") and case_id in str(b.key) for b in at.button)  # no visit log form
    assert any("Closed: Person withdrew · by SK" in c.value for c in at.caption)
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.session_state["continue_code"] = code
    at.run()
    assert any("This case is closed, so it can't be continued" in e.value for e in at.error)
    assert at.session_state["case_id"] != case_id if "case_id" in at.session_state else True
