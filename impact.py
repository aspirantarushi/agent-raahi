"""Impact log for real use: only for cases a partner organisation has given permission to log. Plain code.

Each entry: case ID (the app's pseudonymous case number), permission status, workflow type, start and
end times, review outcome, referral made by an authorised worker, external acknowledgement or
reference, reviewer feedback. Facts are taken from what the app already recorded (audit record,
timeline, case status), not typed again. Practice cases (evaluation sessions) are refused, so practice
and real use stay separate. Saved through storage.py (impact log, kept out of git).
"""

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import audit
import evaluation
import privacy
import storage
import store
import timeline

HERE = Path(__file__).resolve().parent
CSV_COLUMNS = ["case_id", "partner", "permission", "permission_reference", "workflow", "started", "ended",
               "review_outcome", "referral_by_authorised_worker", "referral_on", "external_acknowledgement",
               "acknowledgement_reference", "reviewer_feedback", "logged_at"]


def practice_case_ids(base: Path = HERE) -> set:
    """Case numbers created during evaluation sessions (practice): never logged as real use."""
    return {s["submission"].get("agent_case") for s in evaluation.sessions(base=base, finished_only=True)
            if s["submission"].get("agent_case")}


def _clean(text: str, limit: int) -> str:
    return privacy.redact((text or "").strip()[:limit])[0]


def entry_for(case_id: str, base: Path = HERE) -> dict:
    """What the app already knows about a case, for the impact log."""
    record = audit.read_record(case_id, base=base)
    if record is None:
        raise ValueError("No such case.")
    events = record.get("events", [])
    status = next((c["status"] for c in store.list_cases(base) if c["id"] == case_id), "deleted")
    tl = timeline.load(case_id, base) or {}
    handoff = tl.get("handoff", {})
    workflow = "Any case" if tl.get("case_type") == "General" or any(
        c["case_type"] == "General" for c in store.list_cases(base) if c["id"] == case_id) else "Section 479 aid"
    return {
        "case_id": case_id, "workflow": workflow,
        "started": record.get("ai_read_at") or (events[0]["time"] if events else record.get("created")),
        "ended": events[-1]["time"] if events else "",
        "review_outcome": status,
        "referral_by_authorised_worker": "yes" if handoff.get("submitted") else "no",
        "referral_on": (handoff.get("submitted") or {}).get("on", ""),
        "external_acknowledgement": "yes" if handoff.get("acknowledged") else "no",
        "acknowledgement_reference": (handoff.get("acknowledged") or {}).get("reference", ""),
    }


def log(case_id: str, partner: str, permission_given: bool, permission_reference: str, reviewer_feedback: str = "",
        base: Path = HERE) -> dict:
    """Add a real-use case to the impact log. Refused without the partner's permission, and for practice cases."""
    store._check_id(case_id)
    if not permission_given:
        raise ValueError("Log a real case only when the partner organisation has given permission.")
    partner, reference = _clean(partner, 100), _clean(permission_reference, 100)
    if not partner or not reference:
        raise ValueError("Enter the partner organisation and how permission was given (for example, letter of 5 Nov 2026).")
    if case_id in practice_case_ids(base):
        raise ValueError("This is a practice (evaluation) case. Practice and real use are kept separate.")
    if any(e["case_id"] == case_id for e in entries(base)):
        raise ValueError("This case is already in the impact log.")
    entry = {**entry_for(case_id, base), "partner": partner, "permission": "given",
             "permission_reference": reference, "reviewer_feedback": _clean(reviewer_feedback, 300),
             "logged_at": datetime.now().isoformat(timespec="seconds"), "kind": "real"}
    storage.backend(base).log_append("impact", entry)
    audit.add_event(case_id, "added to the impact log", audit.SUPERVISOR, f"partner permission: {reference}", base=base)
    return entry


def entries(base: Path = HERE) -> List[dict]:
    return storage.backend(base).log_entries("impact")


def export_csv(base: Path = HERE) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for e in entries(base):
        writer.writerow(e)
    return out.getvalue()
