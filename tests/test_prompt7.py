"""Prompt 7: "Try the Practice Clinic" (README and sign-in hint), the Practice Clinic snapshot and reset (never in
a real clinic), and small fixes (no "since after", no "The person wants" inside its own field, pension papers,
"New case" until a case is open). Fake practice data only."""

import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest

import casework
import lang
import practice
import storage
import store
import tracker
from test_new_case_fixes import facts as make_facts
from test_supervisor_review import supervisor_screen

ROOT = Path(__file__).resolve().parents[1]
PRACTICE = "Agent Raahi Practice Clinic"


@pytest.fixture
def clinic(monkeypatch, tmp_path):
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLINIC_NAME", PRACTICE)
    return tmp_path


def sent_case(by="Volunteer A"):
    case_id = tracker.open_case("General", by)["id"]
    store.submit("DRAFT — to be checked by a lawyer\n\nCase summary (practice).\n", make_facts(), case_id=case_id, by=by)
    return case_id


# ---------- snapshot and reset ----------

def test_reset_puts_every_practice_case_back_and_logs_who(clinic):
    kept = sent_case()
    manifest = practice.take_snapshot("Supervisor", now=datetime(2026, 11, 14, 9, 30))
    assert manifest["taken_at"] == "2026-11-14T09:30" and manifest["counts"]["pending"] == 1
    assert not (ROOT / "practice_snapshot").exists()                                   # never in the repository
    added = sent_case(by="Volunteer B")                                               # tried after the snapshot
    store.approve(kept, by="Supervisor S")                                            # and a case changed
    restored = practice.reset("Supervisor S", now=datetime(2026, 11, 15, 10, 0))
    assert store.get_pending(kept)["status"] == store.WAITING                         # back as it was
    assert tracker.load(added) is None and storage.read_json("audit", added) is None   # added since: gone
    assert store.approved_draft(kept) is None and restored["pending"] == 1
    assert practice.latest()["resets"] == [{"at": "2026-11-15T10:00", "by": "Supervisor S"}]


def test_a_large_snapshot_is_saved_in_parts(clinic, monkeypatch):
    for n in range(3):
        sent_case(by=f"Volunteer {n}")
    monkeypatch.setattr(practice, "PART_SIZE", 2000)
    manifest = practice.take_snapshot("Supervisor")
    assert len(manifest["parts"]) > 1
    assert all(len(storage.backend().read("practice_snapshot", p)) < 3000 for p in manifest["parts"])
    assert sorted(practice.snapshot_data()["pending"]) == sorted(r["id"] for r in store.list_pending())


def test_never_in_a_real_clinic(monkeypatch, tmp_path):
    monkeypatch.setenv("RAAHI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLINIC_NAME", "Gaya District Legal Aid Clinic")
    assert not practice.is_practice()
    with pytest.raises(practice.PracticeError):
        practice.take_snapshot("Supervisor")
    with pytest.raises(practice.PracticeError):
        practice.reset("Supervisor")
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    assert not any(str(b.key).startswith("pr-") for b in at.button)
    assert not any("Reset the Practice Clinic" in m.value for m in at.markdown)


def test_reset_button_has_a_confirm_step(clinic, monkeypatch):
    kept = sent_case()
    practice.take_snapshot("Supervisor", now=datetime(2026, 11, 14, 9, 30))
    added = sent_case(by="Volunteer B")
    at = supervisor_screen(monkeypatch, name="Supervisor S")
    at.button(key="pr-start").click().run()
    assert any("back to how they were on 14 November 2026, 09:30" in w.value for w in at.warning)
    assert tracker.load(added) is not None                                           # nothing changed yet
    at.button(key="pr-yes").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert tracker.load(added) is None and store.get_pending(kept)["status"] == store.WAITING
    assert any("Reset by Supervisor S" in i.value for i in at.info)


def test_the_database_allows_the_snapshot_record():
    sql = (ROOT / "supabase" / "tracker.sql").read_text(encoding="utf-8")
    assert sql.count("'practice_snapshot'") == 2                                     # new tables and older ones


# ---------- README and the sign-in hint ----------

def test_try_the_practice_clinic_and_no_judges():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    top = readme[:readme.index("## What Agent Raahi does")]
    assert "## Try the Practice Clinic" in top and "https://agent-raahi.streamlit.app" in top
    assert "`volunteerpassword`" in top and "`supervisorpassword`" in top and "fictional" in top
    assert "docs/EVALUATION_RESULTS.md" in top and "docs/PRACTICE_RUN.md" in top
    assert lang.t("signin.practice_hint") == "Trying the Practice Clinic? The practice passcodes are in the README."
    assert lang.t("signin.practice_hint", "hi") == "Practice Clinic आज़मा रहे हैं? अभ्यास के पासकोड README में हैं।"
    found = subprocess.run(["git", "grep", "-n", "-i", "judges", "--", "README.md", "docs", "i18n", "*.py",
                            ":!docs/hindi_review.csv", ":!tests"], cwd=ROOT, capture_output=True, text=True).stdout
    assert found == "", found


# ---------- small fixes ----------

def test_never_since_after():
    g = make_facts(timeline=[("after April 2026", "Pension stopped")], what_happened=["The pension stopped."])
    text = casework.duration_text(g, date(2026, 11, 14))
    assert "since after" not in text and "(after April 2026: pension stopped)" in text


def test_what_the_person_wants_without_the_person_wants():
    assert casework.wants_text("The person wants the pension restarted with arrears.") == \
        "The pension restarted with arrears."
    assert casework.wants_text("वे चाहती हैं कि पेंशन फिर से शुरू हो।") == "पेंशन फिर से शुरू हो।"


def test_pensions_have_their_own_papers():
    g = make_facts(issues=[("ration_or_welfare", "widow pension stopped since April")],
                   what_happened=["The widow pension stopped after April 2026."], documents_held=[])
    assert casework.problem_type(g) == "pension"
    docs, _ = casework.documents_needed(g, [])
    assert "Pension order or sanction letter" in docs and "Bank passbook" in docs
    assert not any("Ration card" in d or "family members" in d for d in docs)


def test_new_case_until_a_case_is_open():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    assert at.title[0].value == "New case" and at.button(key="nav-new").label == "New case"
    at.session_state["case_id"] = tracker.open_case("General", "Volunteer A")["id"]
    at.run()
    assert at.button(key="nav-new").label == "Current case"
