"""Editing a case: change facts, add notes, change the next step and date. Every change is audited
(who, when, old -> new). Editing an approved case keeps the approved version and makes a new version
that needs the supervisor's review again. Practice data only."""

from datetime import date

import pytest

import audit
import store
import tracker
from test_drafts import practice_facts

DRAFT = "DRAFT — to be checked by a lawyer\n\nPractice draft."


def opened(tmp_path, case_type="Undertrial", by="Volunteer A"):
    record = tracker.open_case(case_type, by, base=tmp_path)
    tracker.merge_facts(record["id"], {"custody_began": date(2024, 3, 15), "section_typed": "380"}, by, "story",
                        base=tmp_path)
    return record["id"]


def approved(tmp_path):
    case_id = opened(tmp_path)
    store.submit(DRAFT, practice_facts(), base=tmp_path, case_id=case_id, by="Volunteer A")
    store.approve(case_id, base=tmp_path, approved_on=date(2026, 11, 2))
    return case_id


def last_event(case_id, tmp_path):
    return audit.read_record(case_id, base=tmp_path)["events"][-1]


def test_edit_a_fact_records_who_when_old_and_new(tmp_path):
    case_id = opened(tmp_path)
    changes = tracker.edit_case(case_id, "Volunteer B", facts={"custody_began": date(2024, 3, 16)}, base=tmp_path)
    assert changes == [{"field": "custody_began", "old": "2024-03-15", "new": "2024-03-16"}]
    record = tracker.load(case_id, base=tmp_path)
    fact = record["facts"]["custody_began"]
    assert fact["value"] == "2024-03-16" and fact["by"] == "Volunteer B" and fact["previous"] == "2024-03-15"
    edit = record["edits"][-1]
    assert edit["by"] == "Volunteer B" and edit["time"] and edit["changes"] == changes
    event = last_event(case_id, tmp_path)
    assert event["event"] == "case edited" and event["time"]
    assert "Volunteer B" in event["details"] and "2024-03-15 -> 2024-03-16" in event["details"]
    assert event["changes"] == [{"field": "custody_began", "old": "2024-03-15", "new": "2024-03-16"}]
    assert tracker.status_of(case_id, base=tmp_path) == tracker.INTAKE  # not approved: no new version
    assert not record.get("versions") and not record.get("review_needed")


def test_unchanged_values_are_not_changes(tmp_path):
    case_id = opened(tmp_path)
    with pytest.raises(tracker.TrackerError, match="Nothing was changed"):
        tracker.edit_case(case_id, "Volunteer B", facts={"custody_began": date(2024, 3, 15), "section_typed": " 380 "},
                          base=tmp_path)


def test_a_note_is_added_and_personal_numbers_are_removed(tmp_path):
    case_id = opened(tmp_path)
    tracker.edit_case(case_id, "Volunteer B", note="Called on 9876543210; FIR copy promised.", base=tmp_path)
    note = tracker.load(case_id, base=tmp_path)["notes"][-1]
    assert note["by"] == "Volunteer B" and "9876543210" not in note["text"] and "FIR copy promised" in note["text"]
    assert "9876543210" not in str(audit.read_record(case_id, base=tmp_path))


def test_next_step_and_date_change(tmp_path):
    today = date(2026, 11, 5)
    case_id = opened(tmp_path)
    changes = tracker.edit_case(case_id, "Volunteer B", next_step="Collect the FIR copy",
                                next_due=date(2026, 11, 12), base=tmp_path, today=today)
    assert {"field": "next step", "old": tracker.NEXT_INTAKE, "new": "Collect the FIR copy"} in changes
    assert {"field": "next step date", "old": None, "new": "2026-11-12"} in changes
    row = next(r for r in tracker.rows(base=tmp_path, today=today) if r["id"] == case_id)
    assert row["next_step"] == "Collect the FIR copy" and row["due"] == "2026-11-12" and not row["overdue"]
    with pytest.raises(tracker.TrackerError, match="Write the next step"):
        tracker.edit_case(case_id, "Volunteer B", next_step="", next_due=date(2026, 11, 20), base=tmp_path)
    # a visit logged later sets the next step again
    tracker.add_visit(case_id, today, "Volunteer A", "phone call", next_step="Meet at the clinic", base=tmp_path,
                      today=today)
    record = tracker.load(case_id, base=tmp_path)
    record["next"]["on"] = "2026-11-05T09:00"  # the edit came before the visit
    tracker._save(record, tmp_path)
    assert tracker.next_step(tracker.load(case_id, base=tmp_path), tracker.INTAKE, case_id, base=tmp_path,
                             today=today)[0] == "Meet at the clinic"


def test_editing_an_approved_case_keeps_the_approved_version(tmp_path):
    case_id = approved(tmp_path)
    approved_draft = store.approved_draft(case_id, base=tmp_path)
    before = tracker.load(case_id, base=tmp_path)
    assert tracker.status_of(case_id, base=tmp_path) == store.APPROVED

    tracker.edit_case(case_id, "Volunteer B", facts={"custody_began": date(2024, 3, 16)}, base=tmp_path)
    record = tracker.load(case_id, base=tmp_path)
    assert record["version"] == 2 and record["review_needed"]["version"] == 2
    kept = record["versions"][0]
    assert kept["version"] == 1 and kept["approved"] is True
    assert kept["facts"]["custody_began"]["value"] == "2024-03-15" == before["facts"]["custody_began"]["value"]
    assert record["facts"]["custody_began"]["value"] == "2024-03-16"
    assert store.approved_draft(case_id, base=tmp_path) == approved_draft  # the approved draft is untouched
    assert tracker.status_of(case_id, base=tmp_path) == tracker.CHANGED
    row = next(r for r in tracker.rows(base=tmp_path) if r["id"] == case_id)
    assert row["status"] == tracker.CHANGED and row["next_step"] == tracker.NEXT_RECHECK
    event = last_event(case_id, tmp_path)
    assert tracker.REVIEW_AGAIN in event["event"] and event["changes"][0]["old"] == "2024-03-15"

    # a second edit before the review stays in version 2 (no second copy of the approved version)
    tracker.edit_case(case_id, "Volunteer A", note="Bail application filed.", base=tmp_path)
    record = tracker.load(case_id, base=tmp_path)
    assert record["version"] == 2 and len(record["versions"]) == 1

    # the supervisor reviews the changes
    assert [r["id"] for r in tracker.needs_review(base=tmp_path)] == [case_id]
    tracker.mark_reviewed(case_id, base=tmp_path)
    assert tracker.status_of(case_id, base=tmp_path) == store.APPROVED
    assert last_event(case_id, tmp_path)["by"] == audit.SUPERVISOR
    with pytest.raises(tracker.TrackerError):
        tracker.mark_reviewed(case_id, base=tmp_path)

    # editing again after the review makes version 3 and keeps version 2
    tracker.edit_case(case_id, "Volunteer A", facts={"section_typed": "381"}, base=tmp_path)
    record = tracker.load(case_id, base=tmp_path)
    assert record["version"] == 3 and [v["version"] for v in record["versions"]] == [1, 2]


def test_edit_needs_a_name(tmp_path):
    case_id = opened(tmp_path)
    with pytest.raises(tracker.TrackerError, match="name"):
        tracker.edit_case(case_id, "  ", note="x", base=tmp_path)


def test_audit_description_shows_the_change(tmp_path):
    case_id = approved(tmp_path)
    tracker.edit_case(case_id, "Volunteer B", facts={"custody_began": date(2024, 3, 16)}, base=tmp_path)
    text = audit.describe(audit.read_record(case_id, base=tmp_path))
    assert "custody_began: 2024-03-15 -> 2024-03-16" in text and "needs supervisor review again" in text


# ---------- scanning the slip's QR code ----------

def qr_photo(text: str) -> bytes:
    import io

    import segno
    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="png", scale=8, border=4)
    return out.getvalue()


def test_qr_on_the_slip_gives_the_code():
    assert tracker.read_qr(qr_photo(tracker.continue_link("https://raahi.example/", "K7M2QX"))) == "K7M2QX"
    assert tracker.read_qr(qr_photo("k7m2qx")) == "K7M2QX"  # no app address: the code alone


def test_qr_that_is_not_a_slip_is_refused():
    with pytest.raises(tracker.TrackerError, match="not from a case slip"):
        tracker.read_qr(qr_photo("https://example.com/something-else"))
    with pytest.raises(tracker.TrackerError, match="No QR code"):
        import io

        from PIL import Image
        blank = io.BytesIO()
        Image.new("RGB", (200, 200), "white").save(blank, format="PNG")
        tracker.read_qr(blank.getvalue())
    with pytest.raises(tracker.TrackerError, match="Could not read"):
        tracker.read_qr(b"not a picture")


# ---------- on screen: "Edit case" on the tracker card, "Edit / make changes" in the case file ----------

def tracker_screen(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "practice-sup")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_input(key="volunteer").set_value("Volunteer B").run()
    at.button(key="nav-tracker").click().run()
    assert not at.exception, at.exception[0].stack_trace
    return at


def test_edit_on_screen_saves_and_audits(monkeypatch):
    record = tracker.open_case("Undertrial", "Volunteer A")
    case_id = record["id"]
    tracker.merge_facts(case_id, {"custody_began": date(2024, 3, 15), "section_typed": "380"}, "Volunteer A", "story")
    at = tracker_screen(monkeypatch)
    assert at.button(key=f"tr-edit-{case_id}").label == "Edit case"
    at.button(key=f"tr-open-{case_id}").click().run()
    html = " ".join(m.value for m in at.markdown)
    assert '<span class="tag">added ' in html and "by Volunteer A</span>" in html  # who added each fact

    # Cancel changes nothing
    at.button(key=f"tr-edit-{case_id}").click().run()
    at.text_input(key=f"ed-{case_id}-section_typed").set_value("381")
    at.button(key=f"ed-cancel-{case_id}").click().run()
    assert tracker.load(case_id)["facts"]["section_typed"]["value"] == "380"

    # Save changes: a fact, a note, the next step and its date
    at.button(key=f"tr-edit-{case_id}").click().run()
    assert at.button(key=f"ed-save-{case_id}").label == "Save changes"
    at.text_input(key=f"ed-{case_id}-section_typed").set_value("381")
    at.text_area(key=f"ed-{case_id}-note").set_value("FIR copy promised for next week.")
    at.text_input(key=f"ed-{case_id}-next").set_value("Collect the FIR copy")
    at.date_input(key=f"ed-{case_id}-due").set_value(date.today())
    at.button(key=f"ed-save-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert any("Changes saved (4)" in s.value for s in at.success)
    saved = tracker.load(case_id)
    assert saved["facts"]["section_typed"]["value"] == "381" and saved["notes"][-1]["by"] == "Volunteer B"
    assert saved["next"]["step"] == "Collect the FIR copy"
    event = audit.read_record(case_id)["events"][-1]
    assert event["event"] == "case edited" and "Volunteer B" in event["details"]
    assert {"field": "section_typed", "old": "380", "new": "381"} in event["changes"]
    html = " ".join(m.value for m in at.markdown)
    assert "Changes made" in html and "380 → <b>381</b>" in html


def test_editing_an_approved_case_on_screen_needs_review_again(monkeypatch):
    record = tracker.open_case("Undertrial", "Volunteer A")
    case_id = record["id"]
    tracker.merge_facts(case_id, {"section_typed": "380"}, "Volunteer A", "story")
    store.submit(DRAFT, practice_facts(), case_id=case_id, by="Volunteer A")
    store.approve(case_id, approved_on=date(2026, 11, 2))
    at = tracker_screen(monkeypatch)
    at.button(key=f"tr-edit-{case_id}").click().run()
    assert any("The approved version is kept" in w.value for w in at.warning)
    at.text_input(key=f"ed-{case_id}-section_typed").set_value("381")
    at.button(key=f"ed-save-{case_id}").click().run()
    assert any("Changed after approval: needs supervisor review again" in s.value for s in at.success)
    assert tracker.status_of(case_id) == tracker.CHANGED
    assert "Changed after approval" in " ".join(m.value for m in at.markdown)  # the status chip

    # the supervisor sees it and marks the changes as reviewed
    at.button(key="nav-supervisor").click().run()
    pw = next(t for t in at.text_input if t.label == "Supervisor password")
    pw.set_value("practice-sup")
    next(b for b in at.button if b.label == "Sign in").click().run()
    at.button(key=f"reviewed-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert tracker.status_of(case_id) == store.APPROVED


def test_opening_a_case_shows_edit_make_changes(monkeypatch):
    record = tracker.open_case("General", "Volunteer A")
    tracker.merge_facts(record["id"], {"state": "Bihar"}, "Volunteer A", "story")
    at = tracker_screen(monkeypatch)
    at.button(key=f"tr-cont-{record['id']}").click().run()  # "Continue this case" opens it on New case
    assert at.session_state["screen"] == "New case"
    edit = at.button(key=f"cf-edit-{record['id']}")
    assert edit.label == "Edit / make changes"
    edit.click().run()
    assert at.button(key=f"ed-save-{record['id']}").label == "Save changes"
    assert at.button(key=f"ed-cancel-{record['id']}").label == "Cancel"
    at.text_input(key=f"ed-{record['id']}-state").set_value("Uttar Pradesh")
    at.button(key=f"ed-save-{record['id']}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert tracker.load(record["id"])["facts"]["state"]["value"] == "Uttar Pradesh"
