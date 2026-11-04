"""Saving drafts and cases. Plain files, no database.

- pending/  drafts waiting for the supervisor, or sent back (kept out of git)
- drafts/   approved drafts only
- cases/    approved case files only

Nothing is written to drafts/ or cases/ until the supervisor approves.
"""

import json
import os
import re
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import audit
import drafts
import general
from drafts import UndertrialFacts

HERE = Path(__file__).resolve().parent
# The random part starts with a letter, so a case number never looks like a
# 12-digit Aadhaar number. Older numbers (4 hex characters) are still accepted.
ID_PATTERN = re.compile(r"^U-\d{8}-[0-9a-z]{4}$")

WAITING = "waiting"
SENT_BACK = "sent back"
APPROVED = "approved"


def _dirs(base: Path):
    return base / "pending", base / "drafts", base / "cases"


def _write(path: Path, text: str) -> None:
    """Write via a temporary file, so a half-written file is never left behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _check_id(case_id: str) -> None:
    if not ID_PATTERN.match(case_id):
        raise ValueError(f"Not a valid case id: {case_id!r}")


def new_case_id(base: Path = HERE, today: Optional[date] = None) -> str:
    today = today or date.today()
    pending, drafts_dir, cases = _dirs(base)
    while True:
        case_id = f"U-{today:%Y%m%d}-{secrets.choice('abcdefghjkmnpqrstuvwxyz')}{secrets.token_hex(2)[:3]}"
        if not any((d / f"{case_id}{ext}").exists()
                   for d, ext in ((pending, ".json"), (drafts_dir, ".md"), (cases, ".md"))):
            return case_id


def submit(draft_text: str, facts: UndertrialFacts, base: Path = HERE, ai: Optional[dict] = None) -> str:
    """Send a draft to the supervisor. Saved in pending/ only, plus its audit record.

    ai: what the AI did for this case ({"model", "read_at", "extracted", "not_accepted"}),
        or None if no AI was used.
    """
    if not draft_text.startswith(drafts.DRAFT_HEADER):
        raise ValueError(f"A draft must start with '{drafts.DRAFT_HEADER}'.")
    found = drafts.personal_details_found(draft_text)
    if found:
        raise ValueError("The draft seems to contain " + " and ".join(found) + ". Remove it first.")
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
    }
    pending, _, _ = _dirs(base)
    _write(pending / f"{case_id}.json", json.dumps(record, indent=2, ensure_ascii=False))
    audit.start_record(case_id, facts.to_dict(), ai, base=base)
    return case_id


def _load(case_id: str, base: Path) -> dict:
    _check_id(case_id)
    pending, _, _ = _dirs(base)
    return json.loads((pending / f"{case_id}.json").read_text(encoding="utf-8"))


def list_pending(base: Path = HERE, status: str = WAITING) -> List[dict]:
    pending, _, _ = _dirs(base)
    if not pending.exists():
        return []
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(pending.glob("U-*.json"))]
    return [r for r in records if r["status"] == status]


def approve(case_id: str, edited_text: Optional[str] = None, base: Path = HERE,
            approved_on: Optional[date] = None) -> None:
    """Save the draft in drafts/ and a case file in cases/, then remove it from pending/."""
    record = _load(case_id, base)
    if record["status"] != WAITING:
        raise ValueError("Only waiting drafts can be approved.")
    text = edited_text if edited_text is not None else record["draft"]
    text = text.replace("\r\n", "\n")
    edited = text.strip() != record["draft"].strip()
    approved_on = approved_on or date.today()
    is_general = record.get("case_type") == general.CASE_TYPE
    text = drafts.fill_approval_date(text, approved_on, record.get("ai_model"),
                                     general.RULES_USED if is_general else drafts.RULES_DATES)
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

    pending, drafts_dir, cases = _dirs(base)
    _write(drafts_dir / f"{case_id}.md", text if text.endswith("\n") else text + "\n")
    _write(cases / f"{case_id}.md", case_text)
    (pending / f"{case_id}.json").unlink()
    audit.add_event(case_id, "approved", audit.SUPERVISOR,
                    "edited by the supervisor before approval" if edited else "approved as sent", base=base)


def reject(case_id: str, reason: str, base: Path = HERE) -> None:
    reason = reason.strip()
    if not reason:
        raise ValueError("Please give a reason for sending it back.")
    record = _load(case_id, base)
    if record["status"] != WAITING:
        raise ValueError("Only waiting drafts can be sent back.")
    record["status"] = SENT_BACK
    record["reason"] = reason
    pending, _, _ = _dirs(base)
    _write(pending / f"{case_id}.json", json.dumps(record, indent=2, ensure_ascii=False))
    audit.add_event(case_id, "sent back", audit.SUPERVISOR, f"reason: {reason}", base=base)


def resend(case_id: str, fixed_text: str, base: Path = HERE) -> None:
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
    record.update(status=WAITING, reason="", draft=text)
    pending, _, _ = _dirs(base)
    _write(pending / f"{case_id}.json", json.dumps(record, indent=2, ensure_ascii=False))
    audit.add_event(case_id, "fixed and resent", audit.VOLUNTEER, base=base)


def get_pending(case_id: str, base: Path = HERE) -> dict:
    return _load(case_id, base)


def list_cases(base: Path = HERE) -> List[dict]:
    """Every case with its status: waiting, sent back (with reason) or approved."""
    cases_list = []
    pending, _, cases = _dirs(base)
    if pending.exists():
        for p in sorted(pending.glob("U-*.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            cases_list.append({"id": r["id"], "case_type": r["case_type"], "status": r["status"],
                               "reason": r.get("reason", ""), "date": r["submitted"][:10]})
    if cases.exists():
        for p in sorted(cases.glob("U-*.md")):
            if not ID_PATTERN.match(p.stem):
                continue
            case_type = "Undertrial"
            for line in p.read_text(encoding="utf-8").splitlines()[:8]:
                if line.startswith("- Case type: "):
                    case_type = (general.CASE_TYPE if line.endswith(general.CASE_TYPE_LABEL)
                                 else line[len("- Case type: "):].split(" (")[0])
            cases_list.append({"id": p.stem, "case_type": case_type, "status": APPROVED,
                               "reason": "", "date": "", "file": p})
    return sorted(cases_list, key=lambda c: c["id"], reverse=True)
