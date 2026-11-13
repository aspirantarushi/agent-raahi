"""Final fixes E: the Supervisor page reads top to bottom. "Waiting for you" (one row per case, one case
open at a time), then the open case in three steps (understand, research points, drafts), then "All
cases (audit records)" and "Tools", folded. Fake practice data only."""

from pathlib import Path

import pytest

import readiness
import research
import store
import tracker
from test_new_case_fixes import facts as make_facts
from test_research import fake_ai, resolve  # noqa: F401  (fake_ai is a fixture)
from test_supervisor_review import supervisor_screen

ROOT = Path(__file__).resolve().parents[1]
ISSUE = "electricity connection cut, department not responding"


def general_case(by="Volunteer A", research_too=True, ready=None):
    case_id = tracker.open_case("General", by)["id"]
    tracker.merge_facts(case_id, {"state": "Bihar"}, by, "story")
    store.submit("DRAFT — to be checked by a lawyer\n\nCase summary (practice).\n", make_facts(), case_id=case_id, by=by,
                 readiness=ready)
    rid = None
    if research_too:
        rid = research.run(case_id, "Bihar", ISSUE, by, resolve=resolve)["id"]
        research.volunteer_review(rid, {"p1": True, "p2": False}, {"p2": "the forum is for a later step"}, by)
    return case_id, rid


@pytest.fixture
def fresh(fake_ai, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))


def page(at):
    return " ".join(m.value for m in at.markdown if "<style" not in m.value)


def test_research_only_ever_shows_on_its_own_case(monkeypatch, fresh):
    with_research, rid = general_case()
    without, _ = general_case(research_too=False)
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": without})
    assert f"Case {without} ·" in page(at)
    assert not any(str(c.key).startswith(f"rsx-{rid}") for c in at.checkbox)     # not the other case's points
    assert "Write first to the Assistant Engineer" not in page(at) + " ".join(c.label for c in at.checkbox)
    assert "Check the research points" not in page(at)                            # no research step at all
    assert research.for_case(without) == [] and [r["id"] for r in research.for_case(with_research)] == [rid]


def test_three_steps_and_the_draft_tabs(monkeypatch, fresh):
    case_id, rid = general_case()
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": case_id})
    text = page(at)
    assert text.index("Understand the case") < text.index("Check the research points") < text.index("Decide on the drafts")
    assert [tab.label for tab in at.tabs] == ["Case summary", "Letter"]           # only the drafts that exist
    assert any(c.value == "1 point not decided is not in this letter." for c in at.caption)
    letter = next(d for d in at.session_state["shown_drafts"] if "Complaint about" in d)
    assert "Write first to the Assistant Engineer" in letter and "Consumer Grievance Redressal Forum" not in letter
    assert not any(e.label == "Readiness when sent" for e in at.expander)         # no repeat of the readiness


def test_sent_anyway_reason_shown_once_in_step_1(monkeypatch, fresh):
    ready = [{"key": "case_documents", "status": "missing", "note": readiness.NOT_TICKED},
             {"key": "send_reason", "status": "ok", "note": "practice run: papers come next week"}]
    case_id, _ = general_case(research_too=False, ready=ready)
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": case_id})
    notes = [w.value for w in at.warning if "practice run: papers come next week" in w.value]
    assert len(notes) == 1
    row = next(m.value for m in at.markdown if 'class="sup-row' in m.value)
    assert "Sent with 1 item not ticked" in row and "Drafts ready" in row


def test_after_a_decision_the_next_case_opens(monkeypatch, fresh):
    first, _ = general_case(research_too=False)
    second, _ = general_case(by="Volunteer B", research_too=False)
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": first})
    assert at.subheader[0].value == "Waiting for you (2)"
    at.button(key=f"approve-{first}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert any(f"{first}" in s.value for s in at.success)                          # a confirmation line
    assert at.subheader[0].value == "Waiting for you (1)"                          # it left the list
    assert f"Case {second} ·" in page(at)                                          # the next one is open


def test_list_comes_first_then_all_cases_then_tools(monkeypatch, fresh):
    general_case(research_too=False)
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    folds = [e.label for e in list(at.expander) + list(at.status)]
    assert folds.index("All cases (audit records)") < folds.index("Tools")
    tools = next(e for e in list(at.expander) + list(at.status) if e.label == "Tools")
    assert not tools.proto.expanded and "Problems reported" in " ".join(m.value for m in tools.markdown)


def test_phone_layout_rules():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    phone = css[css.index("Final fixes E: Supervisor page"):]
    assert 'div[class*="st-key-sup-row-"] { flex-direction: column !important;' in phone          # list rows stack
    assert 'div[class*="st-key-sup-decide-"] { flex-direction: column !important;' in phone       # buttons stack
