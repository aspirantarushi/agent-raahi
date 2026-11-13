"""Final fixes D3: research points and drafts approved independently, inside each case. Approving the
drafts is one click: it saves the point decisions on screen, rebuilds the letter from the approved points
only (points not decided are left out, and the notes say how many), and approves. Research with no drafts
sent yet is shown inside its own case card. Fake practice data only."""

import pytest

import audit
import casework
import research
import store
import tracker
from test_new_case_fixes import facts as make_facts
from test_research import fake_ai, resolve  # noqa: F401  (fake_ai is a fixture)
from test_supervisor_review import supervisor_screen

ISSUE = "electricity connection cut, department not responding"
P1 = "Write first to the Assistant Engineer"           # kept by the volunteer
P2 = "Consumer Grievance Redressal Forum"              # left out by the volunteer


def research_for(case_id):
    r = research.run(case_id, "Bihar", ISSUE, "Volunteer A", resolve=resolve)
    research.volunteer_review(r["id"], {"p1": True, "p2": False}, {"p2": "the forum is for a later step"}, "Volunteer A")
    return r["id"]


@pytest.fixture
def case(fake_ai, monkeypatch, tmp_path):  # noqa: F811
    """A general case: drafts waiting for review, with research (p1 kept, p2 left out). Its own data folder."""
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))
    case_id = tracker.open_case("General", "Volunteer A")["id"]
    tracker.merge_facts(case_id, {"state": "Bihar"}, "Volunteer A", "story")
    store.submit("DRAFT — to be checked by a lawyer\n\nCase summary (practice).\n", make_facts(), case_id=case_id,
                 by="Volunteer A")
    return case_id, research_for(case_id)


def letter_of(text):
    return next((p for p in casework.split_bundle(text) if "Complaint about" in p), "")


def approve(at, case_id):
    at.button(key=f"approve-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace


def test_approve_drafts_with_undecided_points_they_are_not_in_the_letter(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    assert any("(1 approved, 0 rejected, 1 not decided)" in c.value for c in at.caption)
    assert any(c.value == "1 point not decided is not in this letter." for c in at.caption)   # the Letter tab (E)
    at.button(key=f"approve-{case_id}").click().run()                      # one click, nothing saved before
    assert not at.exception, at.exception[0].stack_trace
    letter = letter_of(store.approved_draft(case_id))
    assert P1 in letter and P2 not in letter
    assert "1 research point was not decided and is not in this letter." in letter
    p1, p2 = [p for p in research.load(rid)["points"] if p["kind"] != "letter"]
    assert p1["status"] == "approved" and p1["decided_by"] == "Supervisor S" and p2["status"] == research.WAITING
    approved = [e for e in audit.read_record(case_id)["events"] if e["event"] == "approved"]
    assert len(approved) == 1 and approved[0]["details"].endswith("1 point approved, 0 rejected, 1 not decided")
    # the undecided point stays listed for later, in the case's own card, marked "Not decided"
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    code = tracker.load(case_id)["code"]                                    # the list shows the case code
    row = next(m.value for m in at.markdown if 'class="sup-row' in m.value and code in m.value)
    assert "Drafts already approved" in row and "1 research point" in row
    assert any("already approved. Points you decide now are not added to that letter." in c.value for c in at.caption)
    assert any('<span class="tag undecided">Not decided</span>' in m.value for m in at.markdown)


def test_approve_all_points_then_approve(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.checkbox(key=f"rsx-{rid}-p1").uncheck().run()
    assert at.button(key=f"rs-all-{rid}").label == "Approve all points (1)"   # E: only the points in the list
    at.button(key=f"rs-all-{rid}").click().run()                            # ticks them again (applied on approval)
    assert not at.exception, at.exception[0].stack_trace
    assert at.checkbox(key=f"rsx-{rid}-p1").value is True and at.checkbox(key=f"rsx-{rid}-p2").value is False
    approve(at, case_id)
    letter = letter_of(store.approved_draft(case_id))
    assert P1 in letter and P2 not in letter and "1 research point was not decided" in letter
    events = [e["event"] for e in audit.read_record(case_id)["events"]]
    assert events.count("research point approved") == 1 and events.count("approved") == 1


def test_reject_a_point_and_approve_the_drafts_in_one_go(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.checkbox(key=f"rsx-{rid}-p1").uncheck().run()                      # reject p1 (a reason)...
    assert at.button(key=f"approve-{case_id}").disabled                    # ...the reason is still needed
    assert any("Give a reason for the unticked point." in m.value for m in at.markdown)
    at.radio(key=f"rsr-{rid}-p1").set_value("looks_wrong").run()
    at.button(key=f"approve-{case_id}").click().run()                      # no "Save point decisions" first
    assert not at.exception, at.exception[0].stack_trace
    p1, p2 = [p for p in research.load(rid)["points"] if p["kind"] != "letter"]
    assert p1["status"] == "rejected" and p1["reject_reason"] == "Looks wrong" and p2["status"] == research.WAITING
    letter = letter_of(store.approved_draft(case_id))
    assert P1 not in letter and P2 not in letter                          # no approved point: facts only
    assert "Facts-only letter" in letter and "1 research point was not decided" in letter
    approved = next(e for e in audit.read_record(case_id)["events"] if e["event"] == "approved")
    assert "0 points approved, 1 rejected, 1 not decided" in approved["details"]


def test_edit_then_approve_rebuilds_first(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    assert not any(a.key == f"edit-{case_id}" for a in at.text_area)
    at.button(key=f"edit-open-{case_id}").click().run()                     # the letter is rebuilt first
    assert not at.exception, at.exception[0].stack_trace
    box = at.text_area(key=f"edit-{case_id}")
    assert P1 in box.value and P2 not in box.value
    box.set_value(box.value.replace("Case summary (practice).", "Case summary (practice, checked).")).run()
    at.button(key=f"edit-approve-{case_id}").click().run()
    assert "Case summary (practice, checked)." in store.approved_draft(case_id)


def test_research_without_drafts_shows_inside_its_case_card(monkeypatch, fake_ai, tmp_path):  # noqa: F811
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))
    case_id = tracker.open_case("General", "Volunteer A")["id"]
    tracker.merge_facts(case_id, {"state": "Bihar"}, "Volunteer A", "story")
    rid = research_for(case_id)
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    assert not any("AI research, not yet checked: for supervisor approval" in s.value for s in at.subheader)
    assert any(s.value == "Waiting for you (1)" for s in at.subheader)
    code = tracker.load(case_id)["code"]                                    # the list shows the case code
    row = next(m.value for m in at.markdown if 'class="sup-row' in m.value and code in m.value)
    assert "Research only — no drafts yet" in row and "Drafts ready" not in row
    assert any(c.value == "The volunteer has not sent drafts yet." for c in at.caption)
    assert at.checkbox(key=f"rsx-{rid}-p1").value is True                   # the research step as usual
    save = at.button(key=f"rs-save-{rid}")
    assert save.label == "Save point decisions (1 approved, 0 rejected, 1 not decided)"
    assert not any(str(b.key).startswith(("approve-", "edit-open-")) for b in at.button)   # no step 3
    save.click().run()                                                       # research-only case saves points
    assert not at.exception, at.exception[0].stack_trace
    p1, p2 = [p for p in research.load(rid)["points"] if p["kind"] != "letter"]
    assert p1["status"] == "approved" and p2["status"] == research.WAITING


def test_self_approval_block_still_holds(monkeypatch, case):
    case_id, rid = case
    at = supervisor_screen(monkeypatch, name="Volunteer A")                 # sent the drafts, asked for the research
    assert not any(str(c.key).startswith("rsx-") for c in at.checkbox)
    assert not any(str(b.key).startswith(("rs-all-", "rs-save-", "approve-", "edit-open-", "back-open-", "reject-"))
                   for b in at.button)
