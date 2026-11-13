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


def test_research_only_case_is_labelled_and_built_from_the_tracker(monkeypatch, fresh):
    """Research run, drafts not sent: the chip, heading and steps all say so (never "sent" or "Drafts ready")."""
    case_id = tracker.open_case("General", "Volunteer A")["id"]
    tracker.merge_facts(case_id, {"state": "Bihar", "woman": False}, "Volunteer A", "story")
    tracker.add_summary(case_id, ["The electricity was disconnected on 2 November 2026."],
                        [("electricity_or_water", "electricity cut off despite a paid bill")], [], "Volunteer A")
    rid = research.run(case_id, "Bihar", ISSUE, "Volunteer A", resolve=resolve)["id"]
    sent_case, _ = general_case(by="Volunteer B", research_too=False)        # a case whose drafts were sent
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": case_id})
    rows = {m.value.split("</b>")[0]: m.value for m in at.markdown if 'class="sup-row' in m.value}
    ro = next(v for v in rows.values() if tracker.load(case_id)["code"] in v)
    sent = next(v for v in rows.values() if tracker.load(sent_case)["code"] in v)
    assert "Research only — no drafts yet" in ro and "Drafts ready" not in ro
    assert "Drafts ready" in sent and "Research only" not in sent
    head = next(m.value for m in at.markdown if 'class="sup-case-head"' in m.value and "<style" not in m.value)
    code = tracker.load(case_id)["code"]
    assert f"Case {case_id} · Code {code} · Any problem · Volunteer A · drafts not sent yet" in head
    assert "November" not in head                                                  # no date in the heading
    assert any(c.value.startswith("Research run ") for c in at.caption)           # the date is in step 1
    text = page(at)
    assert 'class="infocard glance"' in text and "The electricity was disconnected on" in text  # from the tracker
    assert "The case cards come with the drafts" not in text
    assert any(c.value == "The volunteer has not sent drafts yet." for c in at.caption)
    assert "Check the research points" in text and "Decide on the drafts" not in text            # no step 3
    assert at.button(key=f"rs-save-{rid}") and not any(str(b.key).startswith("approve-") for b in at.button)
    # the case whose drafts were sent: heading says "sent", and step 3 is there
    at.button(key=f"sup-open-{sent_case}").click().run()
    head = next(m.value for m in at.markdown if 'class="sup-case-head"' in m.value and "<style" not in m.value)
    assert "drafts not sent yet" not in head and "Decide on the drafts" in page(at)
    assert any(c.value.startswith("Sent ") for c in at.caption)


def test_open_case_in_one_box_and_close_returns_to_the_list(monkeypatch, fresh):
    case_id, _ = general_case(research_too=False)
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": case_id})
    heads = [m.value for m in at.markdown if 'class="sup-case-head"' in m.value and "<style" not in m.value]
    assert len(heads) == 1 and at.button(key=f"approve-{case_id}")                # heading .. decision buttons
    close = at.button(key=f"sup-close-{case_id}")
    assert close.label == "Back to the list"
    close.click().run()
    assert not any('class="sup-case-head"' in m.value and "<style" not in m.value for m in at.markdown)
    assert at.subheader[0].value == "Waiting for you (1)"                           # the list stays
    assert not at.button(key=f"sup-open-{case_id}").disabled                        # nothing open
    at.button(key=f"sup-open-{case_id}").click().run()
    assert at.button(key=f"approve-{case_id}")                                       # open again
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    assert 'div[class*="st-key-review-"][data-testid="stVerticalBlock"] { background: var(--card) !important;\n  border: 2px solid var(--line2)' in css
    rule = css[css.index("never a box inside a box"):]
    assert 'div[class*="st-key-review-"])' in rule[:2000]                             # no second border inside


def row_blocks(node, found=None):
    """Every list row (the block holding a "sup-row" line), with all it holds."""
    found = [] if found is None else found
    kids = list(getattr(node, "children", {}).values())
    if any("class=\"sup-row" in str(getattr(k, "value", "")) for k in kids):
        found.append(kids)
    for k in kids:
        row_blocks(k, found)
    return found


def all_text(nodes):
    out = []
    for n in nodes:
        out.append(str(getattr(n, "value", "")))
        out += all_text(list(getattr(n, "children", {}).values()))
    return " ".join(out)


def test_a_list_row_never_contains_case_cards(monkeypatch, fresh):
    """Every row type, with a case open and with none open: a row holds only its line and its "Open" button."""
    research_only = tracker.open_case("General", "Volunteer D")["id"]
    tracker.merge_facts(research_only, {"state": "Bihar", "woman": True}, "Volunteer D", "story")
    tracker.add_summary(research_only, ["The electricity was disconnected on 2 November 2026."],
                        [("electricity_or_water", "electricity cut off despite a paid bill")], [], "Volunteer D")
    research.run(research_only, "Bihar", ISSUE, "Volunteer D", resolve=resolve)
    sent, _ = general_case(by="Volunteer A")                                    # drafts sent, with research
    back, _ = general_case(by="Volunteer B")
    store.reject(back, "add the dates", by="Supervisor S")                     # sent back: not in the list
    at = supervisor_screen(monkeypatch, name="Supervisor S", **{"sup-open": research_only})
    for state in ("research-only open", "drafts case open", "none open"):
        if state == "drafts case open":
            at.button(key=f"sup-open-{sent}").click().run()
        if state == "none open":
            at.button(key=next(b.key for b in at.button if str(b.key).startswith("sup-close-"))).click().run()
        rows = row_blocks(at.main)
        assert len(rows) == 2, state                                            # the sent-back case is not a row
        for kids in rows:
            assert len(kids) == 2 and kids[1].type == "button", state           # the line and "Open", nothing else
            assert "infocard" not in all_text(kids) and "has not sent drafts" not in all_text(kids), state
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    assert 'div[class*="st-key-sup-row-"] > div:nth-child(n+3) { display: none !important; }' in css
