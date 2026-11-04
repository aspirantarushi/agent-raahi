"""Draft SC "Regulations for Use of AI in Courts, 2026": disclosure, no risk scoring, audit trail."""

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import drafts
import llm
import store
from drafts import DRAFT_HEADER, UndertrialFacts
from test_drafts import practice_facts
from test_intake import NOTES, practice_answer

ROOT = Path(__file__).resolve().parent.parent
MODEL = "gemini-3.5-flash-lite"
AI_SENTENCE = (f"How this draft was prepared: facts were read from case notes with AI assistance ({MODEL}) "
               "and checked by a volunteer; dates were calculated by rule-based code from the statute; "
               "the draft was reviewed and approved by the supervisor on [date]. If this is filed in any "
               "court, AI assistance must be declared as the court requires.")
NO_AI_SENTENCE = ("How this draft was prepared: facts were entered by a volunteer; dates were calculated "
                  "by rule-based code from the statute; the draft was reviewed and approved by the "
                  "supervisor on [date].")


def make(ai_model=None, **changes):
    facts = practice_facts(**changes)
    result = drafts.recalculate(facts)
    return facts, drafts.make_undertrial_draft(facts, result, ai_model=ai_model)


def ai_info(final_facts: UndertrialFacts, **extracted_changes):
    extracted = {"custody_began": date(2024, 3, 15), "today": date(2026, 11, 2), "law": "IPC",
                 "section": "380", "more_than_one_section": False, "never_convicted": True,
                 "other_cases_pending": False, "delay_days_by_accused": 0, "lawyer": "Legal aid lawyer"}
    extracted.update(extracted_changes)
    return {"model": MODEL, "read_at": "2026-11-04T10:00:00", "extracted": extracted,
            "not_accepted": ["offence_date"]}


# ---------- 1. AI disclosure on every draft ----------

def test_disclosure_names_the_model_when_ai_was_used():
    _, text = make(ai_model=MODEL)
    assert text.startswith(DRAFT_HEADER)
    assert text.rstrip().endswith(AI_SENTENCE)


def test_disclosure_without_ai():
    _, text = make()
    assert text.rstrip().endswith(NO_AI_SENTENCE)
    assert "gemini" not in text
    assert "AI assistance must be declared" not in text


def test_disclosure_comes_after_the_dlsa_application():
    _, text = make(ai_model=MODEL, lawyer="None")
    assert text.index("APPLICATION FOR FREE LEGAL SERVICES") < text.index("How this draft was prepared:")
    assert text.count("How this draft was prepared:") == 1


def test_approval_date_filled_on_approval(tmp_path):
    facts, text = make(ai_model=MODEL)
    case_id = store.submit(text, facts, base=tmp_path, ai=ai_info(facts))
    pending = store.get_pending(case_id, base=tmp_path)["draft"]
    assert "approved by the supervisor on [date]." in pending  # not approved yet
    store.approve(case_id, base=tmp_path, approved_on=date(2026, 11, 5))
    saved = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "approved by the supervisor on 5 November 2026." in saved
    assert "[date]. If this is filed" not in saved
    assert f"with AI assistance ({MODEL})" in saved


def test_disclosure_put_back_if_supervisor_deleted_it(tmp_path):
    facts, text = make(ai_model=MODEL)
    case_id = store.submit(text, facts, base=tmp_path, ai=ai_info(facts))
    edited = text.split("\n---\n\nHow this draft")[0]
    store.approve(case_id, edited_text=edited, base=tmp_path, approved_on=date(2026, 11, 5))
    saved = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert saved.rstrip().endswith(AI_SENTENCE.replace("[date]", "5 November 2026"))


def test_template_blanks_are_unaffected():
    _, text = make()
    assert "Date: [date]" in text  # the letter's own date blank is still for a person to fill


# ---------- 2. No risk scoring ----------

@pytest.mark.parametrize("path", ["README.md", "CLAUDE.md"])
def test_never_do_section_in_docs(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "## What this tool will never do" in text
    section = text.split("## What this tool will never do")[1].split("\n## ")[0]
    for words in ["bail", "flight risk", "re-offending", "credibility", "statutory deadlines",
                  "plain", "not an assessment of whether bail should", "only to extract facts"]:
        assert words in " ".join(section.split()), words


def test_prompt_contains_the_no_judgement_instruction():
    assert llm.NO_JUDGEMENT_RULE in " ".join(llm.UNDERTRIAL_PROMPT.split())


# ---------- 3. Audit record ----------

def test_audit_record_with_ai(tmp_path):
    facts, text = make(ai_model=MODEL, offence_date=date(2024, 2, 15))
    # The volunteer changed one AI value: the AI said "Legal aid lawyer", the volunteer chose "None".
    final = practice_facts(offence_date=date(2024, 2, 15), lawyer="None")
    case_id = store.submit(text, final, base=tmp_path, ai=ai_info(final))
    r = audit.read_record(case_id, base=tmp_path)
    assert r["case_id"] == case_id and r["model"] == MODEL
    assert r["ai_read_at"] == "2026-11-04T10:00:00"
    assert r["ai_extracted"]["custody_began"] == "2024-03-15"
    assert r["ai_extracted"]["section"] == "380"
    assert r["volunteer_changed"] == [{"field": "lawyer", "ai_value": "Legal aid lawyer", "final_value": "None"}]
    assert r["entered_by_volunteer"] == ["offence_date"]
    assert r["ai_answers_not_accepted"] == ["offence_date"]
    assert [e["event"] for e in r["events"]] == ["sent to supervisor"]


def test_audit_record_without_ai(tmp_path):
    facts, text = make()
    case_id = store.submit(text, facts, base=tmp_path)
    r = audit.read_record(case_id, base=tmp_path)
    assert r["model"] == "no AI" and r["ai_extracted"] == {} and r["volunteer_changed"] == []


def test_audit_records_each_decision(tmp_path):
    facts, text = make(ai_model=MODEL)
    case_id = store.submit(text, facts, base=tmp_path, ai=ai_info(facts))
    store.reject(case_id, "Add the court.", base=tmp_path)
    store.resend(case_id, text.replace("[court, CNR]", "Saket Court, CNR [___]"), base=tmp_path)
    store.approve(case_id, edited_text=text + "\nEdited.", base=tmp_path)
    events = audit.read_record(case_id, base=tmp_path)["events"]
    assert [(e["event"], e["by"]) for e in events] == [
        ("sent to supervisor", "volunteer"),
        ("sent back", audit.SUPERVISOR),
        ("fixed and resent", "volunteer"),
        ("approved", audit.SUPERVISOR),
    ]
    assert events[1]["details"] == "reason: Add the court."
    assert events[3]["details"] == "edited by the supervisor before approval"
    assert all(e["time"] for e in events)


def test_audit_has_no_notes_quotes_or_personal_numbers(tmp_path):
    facts, text = make(ai_model=MODEL)
    info = ai_info(facts)
    info["extracted"]["answer"] = "call 9876543210"  # even if a personal number slipped into a value
    case_id = store.submit(text, facts, base=tmp_path, ai=info)
    store.reject(case_id, "Ring the sister on 98765 43210", base=tmp_path)
    saved = (tmp_path / "audit" / f"{case_id}.json").read_text(encoding="utf-8")
    assert "9876543210" not in saved and "98765 43210" not in saved
    assert "Her brother was arrested" not in saved  # no pasted notes or quotes
    assert "quote" not in saved


def test_describe_reads_plainly(tmp_path):
    facts, text = make(ai_model=MODEL)
    final = practice_facts(lawyer="None")
    case_id = store.submit(text, final, base=tmp_path, ai=ai_info(final))
    store.approve(case_id, base=tmp_path)
    words = audit.describe(audit.read_record(case_id, base=tmp_path))
    assert f"AI model used: {MODEL}" in words
    assert "Fields the volunteer changed: lawyer (Legal aid lawyer → None)" in words
    assert f"approved, by {audit.SUPERVISOR} (approved as sent)" in words


# ---------- problems log ----------

def test_report_problem_saved_with_case_and_date(tmp_path):
    entry = audit.report_problem("The one-third date looks wrong.", "U-20261104-k7f1", "My cases", base=tmp_path)
    [saved] = audit.list_problems(base=tmp_path)
    assert saved == entry
    assert saved["case_id"] == "U-20261104-k7f1" and saved["time"].startswith(str(date.today()))


def test_report_problem_removes_personal_numbers(tmp_path):
    audit.report_problem("Call me on 9876543210 or a@b.com", None, "New case", base=tmp_path)
    [saved] = audit.list_problems(base=tmp_path)
    assert "9876543210" not in saved["text"] and "a@b.com" not in saved["text"]
    assert saved["case_id"] == "no case number yet"


def test_empty_problem_refused(tmp_path):
    with pytest.raises(ValueError):
        audit.report_problem("   ", None, "New case", base=tmp_path)


def test_problems_listed_newest_first(tmp_path):
    audit.report_problem("first", None, "New case", base=tmp_path)
    audit.report_problem("second", None, "New case", base=tmp_path)
    assert [p["text"] for p in audit.list_problems(base=tmp_path)] == ["second", "first"]


@pytest.mark.parametrize("path", ["audit/U-20261104-k7f1.json", "problems/problems.jsonl",
                                  "pending/U-20261104-k7f1.json", ".env"])
def test_records_are_kept_out_of_git(path):
    assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0


# ---------- in the app ----------

def test_report_problem_on_new_case(monkeypatch, tmp_path):
    saved = []
    monkeypatch.setattr(audit, "report_problem", lambda text, case_id, where: saved.append((text, case_id, where)))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_area(key="problem-new-case").set_value("The form is confusing.")
    next(b for b in at.button if b.label == "Send report").click().run()
    assert not at.exception
    assert saved == [("The form is confusing.", None, "New case")]
    assert any("Thank you" in s.value for s in at.success)


def test_draft_made_after_ai_reading_names_the_model(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes",
                        lambda notes: llm.NotesReading(practice_answer(), notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.text_area(key="f_notes").set_value(NOTES)
    next(b for b in at.button if b.label == "Read notes").click().run()
    at.date_input(key="q-offence_date").set_value(date(2024, 2, 15))
    next(b for b in at.button if b.label == "Next").click().run()
    at.checkbox(key="f_checked").check().run()
    next(b for b in at.button if b.label == "Make draft").click().run()
    assert not at.exception
    assert at.code[0].value.rstrip().endswith(AI_SENTENCE)
