"""Final fixes D2: two clear rejections on the Supervisor page. Section A: research points (untick =
"Point rejected", only out of the letter; the case stays). Section B: the drafts (Approve, Edit then
approve, or "Reject the drafts — send back to the volunteer", at any time). Approve is locked until every
point is decided. Fake practice data only."""

import pytest
from streamlit.testing.v1 import AppTest

import audit
import lang
import research
import store
import tracker
from test_research import fake_ai, resolve  # noqa: F401  (fake_ai is a fixture)
from test_supervisor_review import make, supervisor_screen

ISSUE = "electricity connection cut, department not responding"


@pytest.fixture
def case(fake_ai, monkeypatch, tmp_path):  # noqa: F811
    """A draft waiting for review, with research asked by Volunteer A (p1 kept, p2 left out with a reason).
    Each test has its own empty data folder."""
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))
    record = tracker.open_case("Undertrial", "Volunteer A")
    tracker.merge_facts(record["id"], {"state": "Bihar"}, "Volunteer A", "story")
    r = research.run(record["id"], "Bihar", ISSUE, "Volunteer A", resolve=resolve)
    research.volunteer_review(r["id"], {"p1": True, "p2": False}, {"p2": "the forum is for a later step"}, "Volunteer A")
    facts, text = make()
    store.submit(text, facts, case_id=record["id"], by="Volunteer A")
    return record["id"], r["id"]


def test_two_sections_and_two_different_rejections(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    page = " ".join(m.value for m in at.markdown if "<style" not in m.value)
    assert page.index("Check the research points") < page.index("Decide on the drafts")   # E: steps 2 and 3
    assert [at.button(key=f"{k}-{case_id}").label for k in ("approve", "edit-open", "back-open")] == \
        ["Approve drafts", "Edit then approve", "Send back to the volunteer"]
    assert not any(str(b.key).startswith("rs-save-") for b in at.button)    # ticks are applied in step 3
    assert not any(r.label == "Why reject this point? (needed)" for r in at.radio)       # nothing unticked yet


def test_approve_is_never_locked_by_undecided_points(monkeypatch, case):  # D3: approve independently
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    assert not at.button(key=f"approve-{case_id}").disabled
    assert not any("Approve after every research point" in m.value for m in at.markdown)


def test_reject_one_point_then_approve_the_drafts(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.checkbox(key=f"rsx-{rid}-p1").uncheck().run()                      # reject this point (a reason)
    at.radio(key=f"rsr-{rid}-p1").set_value("not_about").run()
    at.checkbox(key=f"rsx-{rid}-p2").check().run()                        # include the volunteer's left-out point
    assert store.get_pending(case_id)["status"] == store.WAITING          # the case stays with the supervisor
    assert not at.button(key=f"approve-{case_id}").disabled
    at.button(key=f"approve-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert store.approved_draft(case_id)
    events = audit.read_record(case_id)["events"]
    point_events = [e for e in events if e["event"].startswith("research point")]
    assert [e["event"] for e in point_events] == ["research point rejected", "research point approved"]
    assert all(e["by"] == "Supervisor S" for e in point_events)            # one entry per decision, with the name


def test_send_the_drafts_back_before_deciding_any_point(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.button(key=f"back-open-{case_id}").click().run()
    assert any("not decided yet go back with the case, unchanged" in c.value for c in at.caption)
    at.text_area(key=f"reason-{case_id}").set_value("the dates in the story do not match").run()
    at.button(key=f"reject-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert store.get_pending(case_id)["status"] == store.SENT_BACK
    assert all(p["status"] == research.WAITING for p in research.load(rid)["points"])   # unchanged
    assert not any(str(c.key).startswith(f"rsx-{rid}") for c in at.checkbox)  # not shown on its own meanwhile
    assert any("Drafts for case" in s.value and "sent back to the volunteer" in s.value for s in at.success)


def test_the_volunteer_sees_the_send_back_reason(monkeypatch, case):
    case_id, _ = case
    store.reject(case_id, "the dates in the story do not match", by="Supervisor S")
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "My cases"
    at.run()
    table = next(m.value for m in at.markdown if 'class="tracker"' in m.value)
    row = next(r for r in table.split("<tr") if case_id in r)
    assert "Drafts sent back" in row and "Sent back: the dates in the story do not match" in row
    card = next(m.value for m in at.markdown if 'class="case-head"' in m.value and case_id in m.value)
    assert "Sent back: the dates in the story do not match" in card


def test_wording_never_just_rejected():
    assert lang.t("aud.ev.research point rejected") == "Point rejected"
    assert lang.t("aud.ev.sent back") == "Drafts sent back"
    assert lang.t("aud.st.sent back") == lang.t("ui.status.sent_back") == "Drafts sent back"
    assert lang.t("rs.decided.rejected", by="S", on="14 November 2026") == "Point rejected by S on 14 November 2026."
    assert lang.t("aud.ev.sent back", "hi") == "ड्राफ़्ट वापस भेजे गए" and lang.t("aud.ev.research point rejected", "hi")
    for key in ("ui.status.sent_back", "aud.st.sent back", "rs.decided.rejected", "agent.ev.sent_back",
                "agent.ev.point_rejected", "sup.send_back_open"):
        assert lang.t(key, by="S", on="x") not in ("Rejected", "Sent back")
