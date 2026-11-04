"""Handoff stages: Ready -> Approved -> Submitted by an authorised worker -> Acknowledged."""

import functools
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import audit
import store
import timeline
from test_timeline import approve_undertrial


def events(case_id, base):
    return [(e["event"], e["by"], e.get("details", "")) for e in audit.read_record(case_id, base=base)["events"]]


def test_full_handoff(tmp_path):
    case_id = approve_undertrial(tmp_path)
    assert timeline.stage(timeline.load(case_id, tmp_path)) == "approved"
    timeline.record_submission(case_id, "Volunteer A (para-legal)", date(2026, 11, 6), "in person", base=tmp_path)
    assert timeline.stage(timeline.load(case_id, tmp_path)) == "submitted"
    timeline.record_acknowledgement(case_id, "DLSA", date(2026, 11, 7), "Diary No. 451/2026", "Volunteer A",
                                    base=tmp_path)
    record = timeline.load(case_id, tmp_path)
    assert timeline.stage(record) == "acknowledged"
    assert record["handoff"]["acknowledged"]["reference"] == "Diary No. 451/2026"
    steps = {s.id: s for s in timeline.steps_of(record)}
    assert steps["handoff-submitted"].status == steps["handoff-acknowledged"].status == "done"
    assert events(case_id, tmp_path)[-2:] == [
        ("submitted by an authorised worker", "Volunteer A (para-legal)", "on 2026-11-06, in person"),
        ("acknowledged", "Volunteer A", "by DLSA on 2026-11-07, reference Diary No. 451/2026")]


def test_approval_is_not_a_submission(tmp_path):
    case_id = approve_undertrial(tmp_path)
    assert "submitted by an authorised worker" not in [e[0] for e in events(case_id, tmp_path)]


def test_cannot_skip_or_repeat_stages(tmp_path):
    case_id = approve_undertrial(tmp_path)
    with pytest.raises(ValueError, match="Record the submission first"):
        timeline.record_acknowledgement(case_id, "DLSA", date(2026, 11, 7), "", "VA", base=tmp_path)
    timeline.record_submission(case_id, "VA", date(2026, 11, 6), "post", base=tmp_path)
    with pytest.raises(ValueError, match="already recorded"):
        timeline.record_submission(case_id, "VA", date(2026, 11, 6), "post", base=tmp_path)
    with pytest.raises(ValueError, match="before the submission"):
        timeline.record_acknowledgement(case_id, "DLSA", date(2026, 11, 5), "", "VA", base=tmp_path)


def test_submission_needs_who_and_how(tmp_path):
    case_id = approve_undertrial(tmp_path)
    with pytest.raises(ValueError, match="who did this"):
        timeline.record_submission(case_id, " ", date(2026, 11, 6), "email", base=tmp_path)
    with pytest.raises(ValueError, match="in person, post, email or portal"):
        timeline.record_submission(case_id, "VA", date(2026, 11, 6), "pigeon", base=tmp_path)


def test_unapproved_case_cannot_be_submitted(tmp_path):
    with pytest.raises(ValueError, match="Only an approved case"):
        timeline.record_submission("U-20261104-k7f1", "VA", date(2026, 11, 6), "email", base=tmp_path)


def test_handoff_steps_only_through_their_forms(tmp_path):
    case_id = approve_undertrial(tmp_path)
    with pytest.raises(ValueError, match="Submitted / Acknowledged form"):
        timeline.mark_done(case_id, "handoff-submitted", date(2026, 11, 6), "VA", base=tmp_path)


def test_reference_is_privacy_filtered(tmp_path):
    case_id = approve_undertrial(tmp_path)
    timeline.record_submission(case_id, "VA", date(2026, 11, 6), "email", base=tmp_path)
    timeline.record_acknowledgement(case_id, "court", date(2026, 11, 7), "call 9876543210", "VA", base=tmp_path)
    assert "9876543210" not in timeline.load(case_id, tmp_path)["handoff"]["acknowledged"]["reference"]


def test_my_cases_handoff_forms(monkeypatch, tmp_path):
    case_id = approve_undertrial(tmp_path)
    original_load = timeline.load
    monkeypatch.setattr(timeline, "load", lambda cid, base=tmp_path: original_load(cid, base))
    for module, name in [(store, "list_cases"), (timeline, "due_this_week"), (timeline, "record_submission"),
                         (timeline, "record_acknowledgement")]:
        monkeypatch.setattr(module, name, functools.partial(getattr(module, name), base=tmp_path))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.sidebar.radio[0].set_value("My cases").run()
    assert any("A draft is not a filing" in c.value for c in at.caption)
    at.text_input(key=f"ho-who-{case_id}").set_value("Volunteer A")
    at.radio(key=f"ho-how-{case_id}").set_value("portal").run()
    at.button(key=f"ho-save-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert any("Submitted by an authorised worker" in m.value for m in at.markdown)
    assert timeline.stage(original_load(case_id, tmp_path)) == "submitted"
