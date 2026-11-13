"""Audit records and the problems log, through storage.py (local files kept out of git, or the
clinic's Supabase table).

- audit/<case number>.json  what happened to each case: when, which AI model (or none),
  the facts the AI extracted, which fields the volunteer changed, and each decision.
- problems/problems.jsonl   problems reported by volunteers or supervisors.

Never stored: names, pasted case notes, the AI's quotes from the notes, or personal
numbers (phone, Aadhaar, email are removed from any text before saving).
"""

import csv
import io
import json
import re
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


def start_record(case_id: str, final_facts: dict, ai: Optional[dict] = None, base: Path = HERE,
                 by: str = "", case_type: str = "") -> dict:
    """Create the audit record when a draft is first sent to the supervisor, with one event:
    "sent to supervisor", by the volunteer's name (or "volunteer" when no name was given).

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
        "case_type": case_type,
        # what happened during intake (case opened, story read, questions, research, drafts) is kept
        "events": [e for e in ((storage.read_json("audit", case_id, base) or {}).get("events") or [])] +
                  [{"time": now(), "event": SENT, "by": _plain(by) or VOLUNTEER, "role": "volunteer"}],
    }
    _save(record, base)
    return record


def add_event(case_id: str, event: str, by: str, details: str = "", base: Path = HERE,
              changes: Optional[List[dict]] = None, role: str = "") -> None:
    """changes: [{"field", "old", "new"}] for an edit, saved with the event (old -> new).
    role: "volunteer" or "supervisor" when by is a person's name."""
    record = storage.read_json("audit", case_id, base)
    if record is None:  # a draft sent before audit records existed
        record = {"case_id": case_id, "created": now(), "model": NOT_RECORDED, "ai_extracted": {},
                  "ai_answers_not_accepted": [], "volunteer_changed": [], "entered_by_volunteer": [],
                  "events": []}
    entry = {"time": now(), "event": event, "by": _plain(by)}
    if role:
        entry["role"] = role
    if details:
        entry["details"] = _plain(details)
    if changes:
        entry["changes"] = [{"field": _plain(c["field"]), "old": _plain(c["old"]), "new": _plain(c["new"])}
                            for c in changes]
    record["events"].append(entry)
    _save(record, base)


SENT = "sent to supervisor"
RESENT = "fixed and resent"
SENT_BACK = "sent back"
APPROVED = "approved"
DELETED = "case deleted"
# Stage of a case, from its audit events (the last of these events decides). A case with none of
# them was never sent to the supervisor: its intake is still in progress.
INTAKE = "intake"
STATUS_EVENTS = {SENT: "waiting", "sent to the supervisor": "waiting", RESENT: "waiting",
                 SENT_BACK: "sent back", APPROVED: "approved", DELETED: "deleted",
                 "case closed": "closed", "case reopened": "approved"}
STATUSES = [INTAKE, "waiting", "sent back", "approved", "closed", "deleted"]
NOT_RECORDED = "not recorded"


def who_did(event: dict) -> str:
    """"Asha (supervisor)" when a name and role were saved; otherwise what was saved."""
    by = event.get("by", "")
    role = event.get("role") or ""
    if not role or by in (VOLUNTEER, SUPERVISOR) or by.strip().casefold() == role.casefold():
        return by  # "Supervisor", never "Supervisor (supervisor)"
    return f"{by} ({role})"


def _sender(event: dict) -> str:
    """The volunteer who sent or resent: the name saved with the event (older records: "by <name>")."""
    if event.get("by") not in (VOLUNTEER, "", None):
        return event["by"]
    found = re.match(r"by (.+)$", event.get("details", ""))
    return found.group(1) if found else ""


def summary_row(record: dict, code: str = "", case_type: str = "", ai_model: str = "") -> dict:
    """One row of the supervisor's table of all cases, from the case's audit record. ai_model: the model
    that read the story (from the case tracker), for a case not yet sent; "-" until the story is read."""
    events = record.get("events", [])
    status, sent, decision = "", None, None
    for e in events:
        if e["event"] in STATUS_EVENTS:
            status = STATUS_EVENTS[e["event"]]
            if status == "waiting":
                sent = e  # the last send or resend (older records: the second copy, which has the name)
            elif e["event"] not in ("case reopened", "case closed"):  # closing is not a decision on the draft
                decision = e
    return {"case_id": record["case_id"], "code": code or record["case_id"],
            "case_type": record.get("case_type") or case_type, "status": status or INTAKE,
            "sent_by": _sender(sent) if sent else "", "sent_on": (sent or {}).get("time", "")[:16].replace("T", " "),
            "decision_by": who_did(decision) if decision else "",
            "decision_on": (decision or {}).get("time", "")[:16].replace("T", " "),
            "ai_used": (ai_model or "-") if record.get("model") in (None, "", NOT_RECORDED) else record["model"],
            "last_step": events[-1]["event"] if events else "",
            "created": record.get("created", "")}


def opened_record(tracker_record: dict) -> dict:
    """For a case opened in the tracker with nothing in its audit record yet: one "case opened" event."""
    return {"case_id": tracker_record["id"], "created": tracker_record.get("created", ""), "model": NOT_RECORDED,
            "case_type": tracker_record.get("case_type", ""),
            "events": [{"time": tracker_record.get("created", ""), "event": "case opened",
                        "by": tracker_record.get("created_by") or VOLUNTEER, "role": "volunteer"}]}


def counts_line(rows: List[dict]) -> Dict[str, int]:
    """How many cases are at each stage (for the line above the table)."""
    return {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}


def filter_rows(rows: List[dict], search: str = "", status: str = "", start: Optional[date] = None,
                end: Optional[date] = None) -> List[dict]:
    """Search by case code (or case number), one status, and the day it was sent (or recorded)."""
    q = (search or "").strip().casefold()
    out = []
    for r in rows:
        if q and q not in r["code"].casefold() and q not in r["case_id"].casefold():
            continue
        if status and r["status"] != status:
            continue
        day = (r["sent_on"] or r["created"])[:10]
        if start and (not day or day < start.isoformat()):
            continue
        if end and (not day or day > end.isoformat()):
            continue
        out.append(r)
    return sorted(out, key=lambda r: r["sent_on"] or r["created"], reverse=True)  # newest first


def history_rows(record: dict) -> List[dict]:
    """A case's full history: one row per event (Time, What happened, By, Details)."""
    rows = []
    for e in record.get("events", []):
        details = e.get("details", "")
        if e.get("changes"):
            details = "; ".join(filter(None, [details] + [f"{c['field']}: {c['old']} -> {c['new']}"
                                                          for c in e["changes"]]))
        rows.append({"time": e["time"][:16].replace("T", " "), "event": e["event"], "by": who_did(e),
                     "details": details})
    return rows


def to_csv(rows: List[dict], columns: List[tuple]) -> str:
    """columns: [(key, heading)]. Plain CSV of what the table shows (no notes, no personal numbers)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([h for _, h in columns])
    for r in rows:
        writer.writerow([r.get(k, "") for k, _ in columns])
    return out.getvalue()


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
        line = f"- {e['time'].replace('T', ' ')}: {e['event']}, by {who_did(e)}"
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


AI_SERVICE = "AI service"


def log_ai_failure(attempts: List[dict], outcome: str, base: Path = HERE) -> dict:
    """One AI request that failed at least once: each try's error type and model, and the outcome.
    Never any case text (only the fixed error types from llm.py and model names are written)."""
    tries = "; ".join(f"{a['model']}: {a['error']}" + (f" (error {a['code']})" if a.get("code") else "")
                      for a in attempts)
    entry = {"time": now(), "case_id": "no case number (AI service)", "where": AI_SERVICE,
             "text": f"AI failure. Tries: {tries}. Outcome: {outcome}.",
             "ai_failures": [{"model": str(a["model"]), "error": str(a["error"]), "code": a.get("code")}
                             for a in attempts], "outcome": outcome}
    storage.backend(base).log_append("problems", entry)
    return entry


def log_research_search(case_id: str, search: str, reason: str, base: Path = HERE) -> dict:
    """Which search a research brief used, when the backup was needed (problems log and audit record).
    Never the story or the key."""
    entry = {"time": now(), "case_id": case_id, "where": AI_SERVICE,
             "text": _plain(f"Research search: {search} used. Reason: {reason}"), "research_search": search}
    storage.backend(base).log_append("problems", entry)
    add_event(case_id, "research search", VOLUNTEER, f"{search} used; reason: {reason}", base=base)
    return entry


def list_problems(base: Path = HERE) -> List[dict]:
    return list(reversed(storage.backend(base).log_entries("problems")))  # newest first


def replace_with_deletion(case_id: str, base: Path = HERE, by: str = "") -> None:
    """After a case is deleted, its audit record keeps only "case deleted", the date and who deleted it."""
    record = {"case_id": case_id, "created": now(), "model": "deleted", "ai_extracted": {},
              "ai_answers_not_accepted": [], "volunteer_changed": [], "entered_by_volunteer": [],
              "events": [{"time": now(), "event": DELETED, "by": _plain(by) or SUPERVISOR,
                          **({"role": "supervisor"} if by else {})}]}
    _save(record, base)
