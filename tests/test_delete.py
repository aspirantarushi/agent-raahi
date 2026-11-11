"""Delete this case: everything goes; the audit record keeps only "case deleted" with the date."""

import functools
import subprocess
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import store
import timeline
from test_timeline import approve_undertrial

ROOT = Path(__file__).resolve().parent.parent


def test_delete_an_approved_case(tmp_path):
    case_id = approve_undertrial(tmp_path)
    timeline.record_submission(case_id, "VA", date(2026, 11, 6), "email", base=tmp_path)
    audit.report_problem("The court name was wrong.", case_id, "My cases", base=tmp_path)
    audit.report_problem("Another case's problem.", "U-20261104-k7f1", "My cases", base=tmp_path)
    removed = store.delete_case(case_id, base=tmp_path)
    assert set(removed) == {"drafts", "cases", "timelines", "problems"}
    for folder, ext in (("drafts", ".md"), ("cases", ".md"), ("timelines", ".json")):
        assert not (tmp_path / folder / f"{case_id}{ext}").exists()
    assert [p["case_id"] for p in audit.list_problems(base=tmp_path)] == ["U-20261104-k7f1"]
    record = audit.read_record(case_id, base=tmp_path)
    assert [e["event"] for e in record["events"]] == ["case deleted"]
    assert record["ai_extracted"] == {} and record["events"][0]["time"].startswith(str(date.today()))
    assert store.list_cases(tmp_path) == []


def test_delete_a_waiting_case(tmp_path):
    from test_drafts import practice_draft
    facts, _, text = practice_draft()
    case_id = store.submit(text, facts, base=tmp_path)
    assert store.delete_case(case_id, base=tmp_path) == ["pending"]
    assert store.list_pending(tmp_path) == []


def test_delete_unknown_case(tmp_path):
    with pytest.raises(ValueError, match="No such case"):
        store.delete_case("U-20261104-k7f1", base=tmp_path)
    with pytest.raises(ValueError):
        store.delete_case("../../etc/passwd", base=tmp_path)


def test_new_case_files_stay_out_of_git():
    for path in ("cases/U-20261199-k000.md", "drafts/U-20261199-k000.md"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0


def test_privacy_note_covers_the_questions():
    text = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
    for heading in ["## In short", "## Never stored", "## What is stored, and where",
                    "## Sent outside the clinic's computer", "## For how long", "## Who can see it",
                    "## Closing a case", "## How a case is deleted", "## Consent before any real case",
                    "## The person's rights (DPDP Act, 2023)", "## What could not be confirmed from the code"]:
        assert heading in text
    assert "Prototype: practice data only. No real person's data has been entered." in text
    assert "Streamlit Community Cloud" in text and "United States" in text and "1 year after it is" in text


def test_supervisor_deletes_on_screen(monkeypatch, tmp_path):
    case_id = approve_undertrial(tmp_path)
    monkeypatch.setattr(store, "list_cases", functools.partial(store.list_cases, base=tmp_path))
    monkeypatch.setattr(store, "list_pending", functools.partial(store.list_pending, base=tmp_path))
    monkeypatch.setattr(store, "delete_case", functools.partial(store.delete_case, base=tmp_path))
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "test-pass")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.button(key="nav-supervisor").click().run()
    at.text_input[0].set_value("test-pass")
    next(b for b in at.button if b.label == "Sign in").click().run()
    at.text_input(key="sup-name").set_value("Supervisor S")  # then the name or initials
    at.button(key="sup-name-go").click().run()
    at.selectbox(key="del-case").set_value(case_id).run()
    at.button(key="del-go").click().run()
    assert any("Type DELETE" in e.value for e in at.error)  # not confirmed: nothing deleted
    assert (tmp_path / "cases" / f"{case_id}.md").exists()
    at.text_input(key="del-confirm").set_value("DELETE")
    at.button(key="del-go").click().run()
    assert not at.exception
    assert not (tmp_path / "cases" / f"{case_id}.md").exists()
