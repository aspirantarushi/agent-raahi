"""Audit records and the problems log, through storage.py (local files kept out of git, or the
clinic's Supabase table).

- audit/<case number>.json  what happened to each case: when, which AI model (or none),
  the facts the AI extracted, which fields the volunteer changed, and each decision.
- problems/problems.jsonl   problems reported by volunteers or supervisors.

Never stored: names, pasted case notes, the AI's quotes from the notes, or personal
numbers (phone, Aadhaar, email are removed from any text before saving).
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import privacy
import storage

HERE = Path(__file__).resolve().parent
NO_AI = "no AI"
SUPERVISOR = "supervisor (signed in with the supervisor password)"
VOLUNTEER = "volunteer"

# Facts the AI can extract -> the matching field in the saved case facts.
AI_FACT_TO_CASE_FIELD = {
    "custody_began": "custody_began", "offence_date": "offence_date", "today": "today",
    "law": "law_typed", "section": "section_typed", "never_convicted": "never_convicted",
    "other_cases_pending": "other_cases_pending", "more_than_one_section": "more_than_one_section",
    "delay_days_by_accused": "delay_days_by_accused", "lawyer": "lawyer", "answer": "answer",
    # general intake
    "danger_now": "danger_now", "money_lost_online": "money_lost_online",
    "money_lost_in_last_few_days": "money_lost_in_last_few_days", "called_1930": "called_1930",
    "woman": "woman", "under_18": "under_18", "sc_st": "sc_st", "disability": "disability",
    "state": "state", "annual_income": "annual_income", "in_custody": "in_custody",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _plain(value):
    """Make a value safe to save as JSON, with personal numbers removed from text."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return privacy.redact(value)[0]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return privacy.redact(str(value))[0]


def _save(record: dict, base: Path) -> None:
    storage.write_json("audit", record["case_id"], record, base)


# ---------- audit records ----------

def volunteer_changes(ai_extracted: Dict[str, object], final_facts: Dict[str, object]) -> List[dict]:
    """Fields where the volunteer's final value differs from what the AI extracted."""
    changes = []
    for fact, value in ai_extracted.items():
        field = AI_FACT_TO_CASE_FIELD.get(fact)
        if field is None:
            continue
        final = final_facts.get(field)
        if _plain(final) != _plain(value):
            changes.append({"field": field, "ai_value": _plain(value), "final_value": _plain(final)})
    return changes


def start_record(case_id: str, final_facts: dict, ai: Optional[dict] = None, base: Path = HERE) -> dict:
    """Create the audit record when a draft is first sent to the supervisor.

    ai: {"model": ..., "read_at": ..., "extracted": {fact: value}, "not_accepted": [fact, ...]}
        or None when no AI was used.
    """
    extracted = {k: _plain(v) for k, v in (ai or {}).get("extracted", {}).items()
                 if k in AI_FACT_TO_CASE_FIELD}
    record = {
        "case_id": case_id,
        "created": now(),
        "model": (ai or {}).get("model") or NO_AI,
        "ai_read_at": (ai or {}).get("read_at"),
        "ai_extracted": extracted,
        "ai_answers_not_accepted": sorted((ai or {}).get("not_accepted", [])),
        "volunteer_changed": volunteer_changes(extracted, final_facts) if ai else [],
        "entered_by_volunteer": sorted(
            field for fact, field in AI_FACT_TO_CASE_FIELD.items()
            if fact not in extracted and final_facts.get(field) not in (None, "")
        ) if ai else [],
        "events": [{"time": now(), "event": "sent to supervisor", "by": VOLUNTEER}],
    }
    _save(record, base)
    return record


def add_event(case_id: str, event: str, by: str, details: str = "", base: Path = HERE) -> None:
    record = storage.read_json("audit", case_id, base)
    if record is None:  # a draft sent before audit records existed
        record = {"case_id": case_id, "created": now(), "model": "not recorded", "ai_extracted": {},
                  "ai_answers_not_accepted": [], "volunteer_changed": [], "entered_by_volunteer": [],
                  "events": []}
    entry = {"time": now(), "event": event, "by": by}
    if details:
        entry["details"] = _plain(details)
    record["events"].append(entry)
    _save(record, base)


def read_record(case_id: str, base: Path = HERE) -> Optional[dict]:
    return storage.read_json("audit", case_id, base)


def list_records(base: Path = HERE) -> List[dict]:
    return sorted((r for r in storage.all_json("audit", base) if str(r.get("case_id", "")).startswith("U-")),
                  key=lambda r: r["created"], reverse=True)


def describe(record: dict) -> str:
    """The audit record in plain words (Markdown), for the supervisor."""
    lines = [f"- Case number: {record['case_id']}",
             f"- Record started: {record['created'].replace('T', ' ')}",
             f"- AI model used: {record['model']}"]
    if record.get("ai_read_at"):
        lines.append(f"- Notes read by the AI at: {record['ai_read_at'].replace('T', ' ')}")
    if record["ai_extracted"]:
        lines.append("- Facts the AI extracted: "
                     + "; ".join(f"{k} = {v}" for k, v in record["ai_extracted"].items()))
    if record.get("ai_answers_not_accepted"):
        lines.append("- AI answers not accepted by the checks: " + ", ".join(record["ai_answers_not_accepted"]))
    if record["model"] != NO_AI:
        if record["volunteer_changed"]:
            lines.append("- Fields the volunteer changed: " + "; ".join(
                f"{c['field']} ({c['ai_value']} → {c['final_value']})" for c in record["volunteer_changed"]))
        else:
            lines.append("- Fields the volunteer changed: none")
        if record.get("entered_by_volunteer"):
            lines.append("- Entered by the volunteer (not found by the AI): "
                         + ", ".join(record["entered_by_volunteer"]))
    for e in record["events"]:
        line = f"- {e['time'].replace('T', ' ')}: {e['event']}, by {e['by']}"
        if e.get("details"):
            line += f" ({e['details']})"
        lines.append(line)
    return "\n".join(lines)


# ---------- problems log ----------

MAX_PROBLEM_LENGTH = 500


def report_problem(text: str, case_id: Optional[str], where: str, base: Path = HERE) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Please describe the problem first.")
    clean, removed = privacy.redact(text[:MAX_PROBLEM_LENGTH])
    entry = {"time": now(), "case_id": case_id or "no case number yet", "where": where, "text": clean}
    if removed:
        entry["removed"] = ", ".join(removed)
    storage.backend(base).log_append("problems", entry)
    return entry


def list_problems(base: Path = HERE) -> List[dict]:
    return list(reversed(storage.backend(base).log_entries("problems")))  # newest first


def replace_with_deletion(case_id: str, base: Path = HERE) -> None:
    """After a case is deleted, its audit record keeps only "case deleted" and the date."""
    record = {"case_id": case_id, "created": now(), "model": "deleted", "ai_extracted": {},
              "ai_answers_not_accepted": [], "volunteer_changed": [], "entered_by_volunteer": [],
              "events": [{"time": now(), "event": "case deleted", "by": SUPERVISOR}]}
    _save(record, base)
