"""Saving drafts and cases, through storage.py (local files, or the clinic's Supabase table).

- pending   drafts waiting for the supervisor, or sent back (kept out of git)
- drafts    approved drafts only
- cases     approved case files only

Nothing is written to drafts or cases until the supervisor approves.
"""

import json
import re
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import audit
import drafts
import general
import storage
import timeline
from drafts import UndertrialFacts

HERE = Path(__file__).resolve().parent
# The random part starts with a letter, so a case number never looks like a
# 12-digit Aadhaar number. Older numbers (4 hex characters) are still accepted.
ID_PATTERN = re.compile(r"^U-\d{8}-[0-9a-z]{4}$")

WAITING = "waiting"
SENT_BACK = "sent back"
APPROVED = "approved"


class AlreadyDecided(ValueError):
    """The case is no longer waiting: approved or sent back already (a double click, or two supervisors)."""
    def __init__(self):
        super().__init__("This case was already decided.")


class OwnDraft(ValueError):
    """A supervisor may not approve a draft they sent or resent themselves."""
    def __init__(self):
        super().__init__("You sent this draft, so another supervisor must approve it.")


def same_person(a: str, b: str) -> bool:
    """Names or initials compared without case, spaces or dots ("A.K. Rao" = "ak rao")."""
    def plain(x):
        return re.sub(r"[\W_]+", "", (x or "").casefold())
    return bool(plain(a)) and plain(a) == plain(b)


def sent_this(record: dict, supervisor: str) -> bool:
    """True if the supervisor is the volunteer who sent the draft or last resent it."""
    return same_person(supervisor, record.get("sent_by", "")) or same_person(supervisor, record.get("resent_by", ""))


def _waiting(case_id: str, base: Path) -> dict:
    """The waiting draft, or AlreadyDecided if it was approved or sent back in the meantime."""
    _check_id(case_id)
    record = storage.read_json("pending", case_id, base)
    if record is None:
        if storage.backend(base).read("drafts", case_id) is not None or audit.read_record(case_id, base=base):
            raise AlreadyDecided()
        raise ValueError("No such draft waiting or sent back.")
    if record["status"] != WAITING:
        raise AlreadyDecided()
    return record


def _save_pending(record: dict, base: Path) -> None:
    storage.write_json("pending", record["id"], record, base)


def _check_id(case_id: str) -> None:
    if not ID_PATTERN.match(case_id):
        raise ValueError(f"Not a valid case id: {case_id!r}")


def new_case_id(base: Path = HERE, today: Optional[date] = None) -> str:
    today = today or date.today()
    store = storage.backend(base)
    while True:
        case_id = f"U-{today:%Y%m%d}-{secrets.choice('abcdefghjkmnpqrstuvwxyz')}{secrets.token_hex(2)[:3]}"
        if not any(store.read(kind, case_id) is not None for kind in ("pending", "drafts", "cases", "tracker")):
            return case_id


def submit(draft_text: str, facts: UndertrialFacts, base: Path = HERE, ai: Optional[dict] = None,
           draft_lang: str = "en", readiness: Optional[list] = None, ledger: Optional[list] = None,
           case_id: Optional[str] = None, by: str = "") -> str:
    """Send a draft to the supervisor. Saved in pending only, plus its audit record.

    ai: what the AI did for this case ({"model", "read_at", "extracted", "not_accepted"}),
        or None if no AI was used.
    case_id: the case number given when intake started (case slip); a new one if None.
    by: the volunteer's name or initials, saved with the action.
    """
    if not draft_text.startswith(drafts.DRAFT_HEADER):
        raise ValueError(f"A draft must start with '{drafts.DRAFT_HEADER}'.")
    found = drafts.personal_details_found(draft_text)
    if found:
        raise ValueError("The draft seems to contain " + " and ".join(found) + ". Remove it first.")
    if case_id:
        _check_id(case_id)
        if storage.backend(base).read("pending", case_id) is not None:
            raise ValueError("This case already has a draft waiting for the supervisor.")
    else:
        case_id = new_case_id(base)
    record = {
        "id": case_id,
        "case_type": getattr(facts, "CASE_TYPE", "Undertrial"),
        "status": WAITING,
        "submitted": datetime.now().isoformat(timespec="minutes"),
        "facts": facts.to_dict(),
        "draft": draft_text,
        "reason": "",
        "ai_model": (ai or {}).get("model"),
        "draft_lang": draft_lang,
        "readiness": readiness or [],  # [{"key", "status", "note"}] when sent
        "ledger": ledger or [],        # [{"fact", "value", "source", "source_line"}]: where each fact came from
        "sent_by": by,
    }
    _save_pending(record, base)
    audit.start_record(case_id, facts.to_dict(), ai, base=base, by=by, case_type=record["case_type"])  # one event
    if readiness is not None:
        open_items = [r for r in readiness if r["status"] in ("missing", "uncertain")]
        reason = any(r.get("key") == "send_reason" and (r.get("note") or "").strip() for r in readiness)
        audit.add_event(case_id, "readiness when sent", audit.VOLUNTEER,
                        "ready for review" if not open_items else f"not ready: {len(open_items)} items missing"
                        + ("; reason given" if reason else ""), base=base)
    return case_id


def _load(case_id: str, base: Path) -> dict:
    _check_id(case_id)
    record = storage.read_json("pending", case_id, base)
    if record is None:
        raise ValueError("No such draft waiting or sent back.")
    return record


def list_pending(base: Path = HERE, status: str = WAITING) -> List[dict]:
    records = [r for r in storage.all_json("pending", base) if ID_PATTERN.match(r.get("id", ""))]
    return [r for r in records if r["status"] == status]


def approve(case_id: str, edited_text: Optional[str] = None, base: Path = HERE,
            approved_on: Optional[date] = None, by: str = "") -> None:
    """Save the draft in drafts/ and a case file in cases/, then remove it from pending/.
    by: the supervisor's name or initials, recorded with the approval. A supervisor who sent (or last
    resent) the draft cannot approve it (OwnDraft); a case no longer waiting raises AlreadyDecided."""
    record = _waiting(case_id, base)
    if sent_this(record, by):
        raise OwnDraft()
    text = edited_text if edited_text is not None else record["draft"]
    text = text.replace("\r\n", "\n")
    edited = text.strip() != record["draft"].strip()
    approved_on = approved_on or date.today()
    is_general = record.get("case_type") == general.CASE_TYPE
    text = drafts.fill_approval_date(text, approved_on, record.get("ai_model"),
                                     general.RULES_USED if is_general else drafts.RULES_DATES,
                                     record.get("draft_lang", "en"))
    if not text.startswith(drafts.DRAFT_HEADER):
        text = drafts.DRAFT_HEADER + "\n\n" + text.lstrip()
    found = drafts.personal_details_found(text)
    if found:
        raise ValueError("The draft seems to contain " + " and ".join(found)
                         + ". Remove it before approving: personal details are never stored.")

    if is_general:
        case_text = general.make_case_file(case_id, record["facts"], approved_on)
    else:
        facts = UndertrialFacts.from_dict(record["facts"])
        result = drafts.recalculate(facts)
        case_text = drafts.make_case_file(case_id, facts, result, approved_on)

    store = storage.backend(base)
    store.write("drafts", case_id, text if text.endswith("\n") else text + "\n")
    store.write("cases", case_id, case_text)
    store.delete("pending", case_id)
    audit.add_event(case_id, "approved", by or audit.SUPERVISOR,
                    "edited by the supervisor before approval" if edited else "approved as sent", base=base,
                    role="supervisor" if by else "")
    # Next-step timeline for the approved case
    if is_general:
        g = general.GeneralFacts.from_dict(record["facts"])
        timeline.create(case_id, general.CASE_TYPE, timeline.general_steps(general.case_next_steps(g)),
                        approved_on, base=base)
    else:
        timeline.create_for_undertrial(case_id, facts, result, approved_on, base=base)


def reject(case_id: str, reason: str, base: Path = HERE, by: str = "") -> None:
    """Send a waiting draft back with a reason. by: the supervisor's name or initials."""
    reason = reason.strip()
    if not reason:
        raise ValueError("Please give a reason for sending it back.")
    record = _waiting(case_id, base)
    record["status"] = SENT_BACK
    record["reason"] = reason
    record["sent_back_by"] = by
    _save_pending(record, base)
    audit.add_event(case_id, "sent back", by or audit.SUPERVISOR, f"reason: {reason}", base=base,
                    role="supervisor" if by else "")


def resend(case_id: str, fixed_text: str, base: Path = HERE, by: str = "") -> None:
    """Fix a sent-back draft and send it to the supervisor again (same case number)."""
    record = _load(case_id, base)
    if record["status"] != SENT_BACK:
        raise ValueError("Only drafts that were sent back can be fixed and resent.")
    text = fixed_text.replace("\r\n", "\n")
    if not text.startswith(drafts.DRAFT_HEADER):
        raise ValueError(f"A draft must start with '{drafts.DRAFT_HEADER}'.")
    found = drafts.personal_details_found(text)
    if found:
        raise ValueError("The draft seems to contain " + " and ".join(found) + ". Remove it first.")
    record.setdefault("history", []).append(
        {"sent_back_reason": record["reason"], "resent": datetime.now().isoformat(timespec="minutes")}
    )
    record.update(status=WAITING, reason="", draft=text, resent_by=by)
    _save_pending(record, base)
    audit.add_event(case_id, "fixed and resent", by or audit.VOLUNTEER, base=base, role="volunteer" if by else "")


LETTER_MARKERS = ("For the volunteer and the supervisor (remove this part", "स्वयंसेवक और सुपरवाइज़र के लिए (पत्र भेजने")


def replace_letter(case_id: str, letter: str, base: Path = HERE) -> None:
    """Put the complaint letter (made from the supervisor's approved research points) into the draft
    waiting for review, replacing an earlier version of it. Recorded in the audit record."""
    import casework
    record = _load(case_id, base)
    if record["status"] != WAITING:
        raise ValueError("Only a waiting draft can get the letter.")
    if not letter.startswith(drafts.DRAFT_HEADER) or drafts.personal_details_found(letter):
        raise ValueError("The letter is not a valid draft.")
    parts = [p.strip() + "\n" for p in casework.split_bundle(record["draft"])
             if not any(m in p for m in LETTER_MARKERS)]
    parts.insert(1 if parts else 0, letter.strip() + "\n")
    record["draft"] = casework.DOC_SEPARATOR.join(parts)
    record["letter_rebuilt"] = True  # the supervisor rebuilt it from the approved points
    _save_pending(record, base)
    audit.add_event(case_id, "complaint letter added from approved research", audit.SUPERVISOR,
                    "built only from the facts of the case and the approved points", base=base)


def remove_letter(case_id: str, base: Path = HERE) -> None:
    """Take the complaint letter out of a waiting draft (the supervisor rejected every research point)."""
    import casework
    record = _load(case_id, base)
    if record["status"] != WAITING:
        return
    parts = [p.strip() + "\n" for p in casework.split_bundle(record["draft"]) if not any(m in p for m in LETTER_MARKERS)]
    record["letter_rebuilt"] = True
    if len(parts) != len(casework.split_bundle(record["draft"])):
        record["draft"] = casework.DOC_SEPARATOR.join(parts)
        _save_pending(record, base)
        audit.add_event(case_id, "complaint letter taken out", audit.SUPERVISOR,
                        "every research point it used was rejected", base=base)


def get_pending(case_id: str, base: Path = HERE) -> dict:
    return _load(case_id, base)


def list_cases(base: Path = HERE) -> List[dict]:
    """Every case with its status: waiting, sent back (with reason) or approved."""
    cases_list = []
    store = storage.backend(base)
    for r in storage.all_json("pending", base):
        if ID_PATTERN.match(r.get("id", "")):
            cases_list.append({"id": r["id"], "case_type": r["case_type"], "status": r["status"],
                               "reason": r.get("reason", ""), "date": r["submitted"][:10]})
    for case_id, text in store.all("cases"):
        if not ID_PATTERN.match(case_id):
            continue
        case_type = "Undertrial"
        for line in text.splitlines()[:8]:
            if line.startswith("- Case type: "):
                case_type = (general.CASE_TYPE if line.endswith(general.CASE_TYPE_LABEL)
                             else line[len("- Case type: "):].split(" (")[0])
        cases_list.append({"id": case_id, "case_type": case_type, "status": APPROVED,
                           "reason": "", "date": "", "text": text})
    return sorted(cases_list, key=lambda c: c["id"], reverse=True)


def approved_draft(case_id: str, base: Path = HERE) -> Optional[str]:
    _check_id(case_id)
    return storage.backend(base).read("drafts", case_id)


def delete_case(case_id: str, base: Path = HERE, by: str = "") -> List[str]:
    """Remove a case completely: waiting or sent-back record, approved draft, case file, timeline, the
    tracker record (facts, visit log) and its problem reports. The audit record keeps only "case deleted"
    with the date. Returns what was removed."""
    _check_id(case_id)
    store = storage.backend(base)
    removed = [kind for kind in ("pending", "drafts", "cases", "timelines", "tracker") if store.delete(kind, case_id)]
    if not removed and audit.read_record(case_id, base=base) is None:
        raise ValueError("No such case.")
    if store.log_remove("problems", lambda e: e.get("case_id") == case_id):
        removed.append("problems")
    for research_id in [i for i in store.ids("research") if i.startswith(case_id + ".")]:
        if store.delete("research", research_id):
            removed.append("research")
    audit.replace_with_deletion(case_id, base=base, by=by)
    return removed
