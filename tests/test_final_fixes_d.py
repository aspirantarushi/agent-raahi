"""Final fixes D: Home Learn cards (no box inside a box, aligned, "Open guide"), and the supervisor's
research points as one checklist (tick = approve, Edit = edit then approve, untick = reject with a
reason, the volunteer's left-out points folded below, one button that saves every decision and rebuilds
the letter). Fake practice data only."""

from pathlib import Path

import pytest

import audit
import research
import ui
from test_research import fake_ai, resolve  # noqa: F401  (fake_ai is a fixture)
from test_supervisor_review import supervisor_screen

ROOT = Path(__file__).resolve().parents[1]
ISSUE = "electricity connection cut, department not responding"


# ---------- Part 1: Home ----------

def test_no_box_inside_a_box_rule_and_learn_card_layout():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    rule = css[css.index("never a box inside a box"):]
    assert 'div[class*="st-key-learn-card-"]' in rule and ".st-key-signin-wide" in rule and '[data-testid="stForm"]' in rule
    assert "border: 0 !important; box-shadow: none !important; background: transparent !important; padding: 0 !important;" in rule
    assert 'div[class*="st-key-learn-card-"] > div:has(.stButton) { margin-top: auto !important;' in css  # buttons line up
    assert "minmax(200px, 1fr)" in css   # "How a case moves": "acknowledgement." keeps its full stop


def test_coming_soon_pill_sits_next_to_the_title():
    html = ui.guide_card("phishing", "Online fraud: the first hours", "What to do first.", "Coming soon")
    assert '<h3>Online fraud: the first hours <span class="soon">Coming soon</span></h3>' in html
    assert ui.guide_card("gavel", "Bail", "Text.").count("soon") == 0


# ---------- Part 2: the supervisor's research checklist ----------

@pytest.fixture
def brief(fake_ai, monkeypatch, tmp_path):  # noqa: F811
    """A case with research asked by Volunteer A; the volunteer kept p1 and left p2 out (with a reason).
    Each test has its own empty data folder (only this case on the Supervisor page)."""
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))
    import tracker
    record = tracker.open_case("General", "Volunteer A")
    tracker.merge_facts(record["id"], {"state": "Bihar"}, "Volunteer A", "story")
    r = research.run(record["id"], "Bihar", ISSUE, "Volunteer A", resolve=resolve)
    research.volunteer_review(r["id"], {"p1": True, "p2": False}, {"p2": "the forum is for a later step"}, "Volunteer A")
    return research.load(r["id"])


def rows(at, rid):
    return {c.key: c for c in at.checkbox if str(c.key).startswith(f"rsx-{rid}-")}


def test_one_list_ticked_for_kept_points_no_old_controls(monkeypatch, brief):
    rid = brief["id"]
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    ticks = rows(at, rid)
    assert ticks[f"rsx-{rid}-p1"].value is True and ticks[f"rsx-{rid}-p2"].value is False   # kept / left out
    assert not any(str(r.key).startswith("rsd-") for r in at.radio)                       # no Approve / Edit / Reject
    assert not any(str(b.key).startswith("rss-") for b in at.button)                      # no "Save decision" per point
    assert any("AI research, not yet checked by a lawyer" in w.value for w in at.warning)
    assert any(e.label == "Left out by the volunteer (1)" for e in at.status)   # (a fold-out with an icon)
    assert any("The volunteer's reason: the forum is for a later step" in c.value for c in at.caption)
    page = "".join(m.value for m in at.markdown if "<style" not in m.value)
    assert '<span class="tag">Route</span>' in page and "p1 ·" not in page and "waiting for the supervisor" not in page
    asked = brief["asked_at"][:10]
    assert any(f"Asked by Volunteer A on " in c.value and asked not in c.value for c in at.caption)  # "13 November 2026"
    assert at.button(key=f"rs-save-{rid}").label == "Save point decisions (1 approved, 0 rejected, 1 not decided)"
    assert at.button(key=f"rs-all-{rid}").label == "Approve all points (1)"   # only the points in the list
    assert '<span class="tag undecided">Not decided</span>' in page     # the left-out point, until decided


def test_approve_all_saves_every_point_with_name_and_one_audit_entry_each(monkeypatch, brief):
    rid = brief["id"]
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.checkbox(key=f"rsx-{rid}-p2").check().run()                       # include the volunteer's left-out point
    save = at.button(key=f"rs-save-{rid}")
    assert save.label == "Save point decisions (2 approved, 0 rejected, 0 not decided)"
    save.click().run()
    assert not at.exception, at.exception[0].stack_trace
    record = research.load(rid)
    assert [p["status"] for p in record["points"] if p["kind"] != "letter"] == ["approved", "approved"]
    assert all(p["decided_by"] == "Supervisor S" and p["decided_on"] for p in record["points"])
    assert record["status"] == research.REVIEWED
    events = [e["event"] for e in audit.read_record(record["case_id"])["events"]]
    assert events.count("research point approved") == 2                   # one audit entry per point


def test_edit_one_and_reject_one_with_a_required_reason(monkeypatch, brief):
    rid = brief["id"]
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.button(key=f"rsedit-{rid}-p1").click().run()                      # "Edit" opens the text in place
    at.text_area(key=f"rse-{rid}-p1").set_value("Write first to the Assistant Engineer (supply), in writing.").run()
    at.button(key=f"rsedit-{rid}-p1").click().run()                      # closed again: the edit is kept
    assert any('<span class="tag edited">edited</span>' in m.value for m in at.markdown)
    at.checkbox(key=f"rsx-{rid}-p2").check().run()
    at.checkbox(key=f"rsx-{rid}-p2").uncheck().run()                     # left out again: not decided
    at.radio(key=f"rsr-{rid}-p2").set_value("repeats").run()            # ...until the supervisor rejects it
    assert not at.button(key=f"rs-save-{rid}").disabled
    # a kept point unticked needs the supervisor's own reason
    at2 = supervisor_screen(monkeypatch, name="Supervisor S")
    at2.checkbox(key=f"rsx-{rid}-p1").uncheck().run()
    save = at2.button(key=f"rs-save-{rid}")
    assert save.disabled and save.label == "Save point decisions (0 approved, 0 rejected, 1 not decided)"
    assert any("Give a reason for the unticked point." in m.value for m in at2.markdown)
    at2.radio(key=f"rsr-{rid}-p1").set_value("other").run()
    at2.text_input(key=f"rsrt-{rid}-p1").set_value("the sub-division is wrong").run()
    assert not at2.button(key=f"rs-save-{rid}").disabled
    # back to the first screen: save the edit
    at.button(key=f"rs-save-{rid}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    record = research.load(rid)
    p1, p2 = [p for p in record["points"] if p["kind"] != "letter"]
    assert p1["status"] == "approved after editing" and p1["text"].endswith("in writing.")
    assert p2["status"] == "rejected" and p2["reject_reason"] == "Repeats another point"
    last = audit.read_record(record["case_id"])["events"][-1]
    assert last["event"] == "research point rejected" and "Repeats another point" in last["details"]
    assert any(c.value.startswith("Edited and approved by Supervisor S on ") for c in at.caption)  # a readable date


def test_reject_reason_quick_choice_is_saved(monkeypatch, brief):
    rid = brief["id"]
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.checkbox(key=f"rsx-{rid}-p1").uncheck().run()
    at.radio(key=f"rsr-{rid}-p1").set_value("looks_wrong").run()
    at.button(key=f"rs-save-{rid}").click().run()
    p1 = research.load(rid)["points"][0]
    assert p1["status"] == "rejected" and p1["reject_reason"] == "Looks wrong"


def test_self_approval_block_no_ticks_no_button(monkeypatch, brief):
    rid = brief["id"]
    at = supervisor_screen(monkeypatch, name="volunteer a")       # the same person who asked for the research
    assert not any(str(c.key).startswith("rsx-") for c in at.checkbox)
    assert not any(str(b.key).startswith(("rs-save-", "rsedit-")) for b in at.button)
    assert any("another supervisor must approve it" in m.value for m in at.markdown)
    assert all(p["status"] == research.WAITING for p in research.load(rid)["points"])


def test_hindi_strings_for_the_checklist():
    import lang
    assert lang.t("rs.save_all_no_letter", "hi", a=5, r=1, u=2) == "बिंदुओं के फ़ैसले सेव करें (5 मंज़ूर, 1 अस्वीकार, 2 पर फ़ैसला नहीं)"
    assert lang.t("rs.save_all_no_letter", a=5, r=1, u=2) == "Save point decisions (5 approved, 1 rejected, 2 not decided)"
    assert lang.t("home.learn_go") == "Open guide" and lang.t("home.eval_go") == "Test yourself"
