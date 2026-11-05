"""The clinic's shared case tracker. Plain code, no AI.

A case is opened when intake starts. It gets a case number and a short code for the person's case
slip, so any volunteer can continue it later. The tracker record holds:
- facts known, each with the date and the volunteer who added it (never asked again);
- contradictions: a new value that differs from an earlier one is NOT saved over it. It waits as
  "Cannot conclude yet" until a volunteer chooses which is right;
- the summary, problems and documents from the notes (never the notes themselves);
- the visit log: every contact (camp visit, call, clinic meeting) with who, how, what was learned,
  what was done and the next step;
- the camp the case was opened at (village, district, date);
- who did what, and when.

Never stored: names of people seeking help, pasted notes, phone / Aadhaar / email numbers (removed
from any text before saving). Volunteers are recorded by the name or initials they type.
"""

import copy
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import audit
import privacy
import storage
import store
import timeline

HERE = Path(__file__).resolve().parent

# The slip code: 6 characters, no 0/O or 1/I, so it is easy to read out and type.
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 6

INTAKE = "intake not finished"
SUBMITTED, ACKNOWLEDGED = "submitted", "acknowledged"
# A case edited after the supervisor approved it: the approved version is kept, and the new one waits
# for the supervisor to look at the changes.
CHANGED = "changed after approval"
REVIEW_AGAIN = "Changed after approval: needs supervisor review again"
APPROVED_STATUSES = (store.APPROVED, SUBMITTED, ACKNOWLEDGED)
STATUSES = [INTAKE, store.WAITING, store.SENT_BACK, store.APPROVED, CHANGED, SUBMITTED, ACKNOWLEDGED]
VISIT_WAYS = ["camp visit", "phone call", "clinic meeting", "jail visit", "other"]

# Facts that are dates (saved as YYYY-MM-DD), and facts never merged: today's date changes at every visit.
DATE_FACTS = {"custody_began", "offence_date"}
NOT_MERGED = {"today", "all_sections", "_precautions"}
TEXT_LIMIT = 300


class TrackerError(ValueError):
    """A message safe to show to the volunteer."""


def now() -> str:
    return datetime.now().isoformat(timespec="minutes")


def clean_text(text: str, limit: int = TEXT_LIMIT) -> str:
    """Trimmed, with phone, Aadhaar and email numbers removed."""
    return privacy.redact((text or "").strip()[:limit])[0]


def clean_name(by: str) -> str:
    by = clean_text(by, 40)
    if not by:
        raise TrackerError("Type your name or initials first.")
    return by


# ---------- the slip code ----------

def new_code(taken: set) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in taken:
            return code


def normalise_code(text: str) -> str:
    """'abc 234', 'ABC-234' -> 'ABC234'. Raises if it can't be a slip code."""
    code = re.sub(r"[\s\-–.]", "", privacy.normalise_digits(text or "")).upper()
    if len(code) != CODE_LENGTH:
        raise TrackerError(f"A case code has {CODE_LENGTH} letters and numbers, for example K7M2QX.")
    bad = sorted({c for c in code if c not in CODE_ALPHABET})
    if bad:
        hint = " (codes never use 0, O, 1 or I)" if set(bad) & set("01OI") else ""
        raise TrackerError("A case code can't contain " + ", ".join(bad) + hint + ".")
    return code


# ---------- reading and saving ----------

def _save(record: dict, base: Path) -> None:
    storage.write_json("tracker", record["id"], record, base)


def load(case_id: str, base: Path = HERE) -> Optional[dict]:
    store._check_id(case_id)
    return storage.read_json("tracker", case_id, base)


def _must_load(case_id: str, base: Path) -> dict:
    record = load(case_id, base)
    if record is None:
        raise TrackerError("No such case in the tracker.")
    return record


def all_records(base: Path = HERE) -> List[dict]:
    return [r for r in storage.all_json("tracker", base) if store.ID_PATTERN.match(r.get("id", ""))]


def find_by_code(code: str, base: Path = HERE) -> dict:
    code = normalise_code(code)
    for record in all_records(base):
        if record.get("code") == code:
            return record
    raise TrackerError("No case has this code. Check the slip and type it again.")


def _note(record: dict, by: str, what: str) -> None:
    record.setdefault("history", []).append({"time": now(), "by": by, "what": what})
    record["last_by"], record["last_at"] = by, now()


def open_case(case_type: str, by: str, base: Path = HERE, camp: Optional[dict] = None) -> dict:
    """Open a case when intake starts. Returns the record with its case number and slip code."""
    by = clean_name(by)
    case_id = store.new_case_id(base)
    code = new_code({r.get("code") for r in all_records(base)})
    record = {"id": case_id, "code": code, "case_type": case_type, "created": now(), "created_by": by,
              "camp": None, "facts": {}, "answers": [], "summary": [], "issues": [], "documents_held": [],
              "conflicts": [], "visits": [], "history": [], "ai_model": None, "ai_read_at": None}
    if camp:
        record["camp"] = _clean_camp(**camp)
    _note(record, by, "case opened (intake started)")
    _save(record, base)
    audit.add_event(case_id, "case opened (intake started)", audit.VOLUNTEER, f"by {by}; slip code given", base=base)
    return record


# ---------- facts: merge, never ask again, flag contradictions ----------

def plain(value):
    """A fact value as saved: dates as YYYY-MM-DD, text cleaned."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return clean_text(str(value))


def _same(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return re.sub(r"\s+", " ", a).strip().casefold() == re.sub(r"\s+", " ", b).strip().casefold()
    return a == b


def known(record: dict) -> Dict[str, object]:
    """fact -> value, as saved (dates as text)."""
    return {fact: entry["value"] for fact, entry in record.get("facts", {}).items()}


def known_for_form(record: dict) -> Dict[str, object]:
    """Known facts with dates turned back into dates, for the forms and questions."""
    values = {}
    for fact, value in known(record).items():
        values[fact] = date.fromisoformat(value) if fact in DATE_FACTS and isinstance(value, str) else value
    return values


def open_conflicts(record: dict) -> List[dict]:
    return [c for c in record.get("conflicts", []) if not c.get("resolved")]


def merge_facts(case_id: str, new: Dict[str, object], by: str, source: str, base: Path = HERE) -> List[dict]:
    """Add new facts to the case. A fact already known with the same value is left alone; a new fact is
    added (with date and volunteer); a DIFFERENT value is not saved over the earlier one: it becomes a
    contradiction to resolve. Returns the new contradictions."""
    by = clean_name(by)
    record = _must_load(case_id, base)
    facts, added, conflicts = record.setdefault("facts", {}), [], []
    for fact, value in new.items():
        if fact in NOT_MERGED or fact.startswith("_") or value is None:
            continue
        value = plain(value)
        entry = {"value": value, "on": now(), "by": by, "source": clean_text(source, 80)}
        if fact not in facts:
            facts[fact] = entry
            added.append(fact)
        elif not _same(facts[fact]["value"], value):
            already = any(c["fact"] == fact and _same(c["new"]["value"], value) for c in open_conflicts(record))
            if not already:
                conflict = {"fact": fact, "earlier": dict(facts[fact]), "new": entry, "resolved": None}
                record.setdefault("conflicts", []).append(conflict)
                conflicts.append(conflict)
    if added or conflicts:
        what = []
        if added:
            what.append("facts added: " + ", ".join(added))
        if conflicts:
            what.append("contradictions found: " + ", ".join(c["fact"] for c in conflicts))
        _note(record, by, "; ".join(what))
        _save(record, base)
        if conflicts:
            audit.add_event(case_id, "contradiction found", audit.VOLUNTEER,
                            "; ".join(f"{c['fact']}: earlier {c['earlier']['value']}, now {c['new']['value']}"
                                      for c in conflicts) + f" (by {by})", base=base)
    return conflicts


def resolve(case_id: str, fact: str, keep: str, by: str, base: Path = HERE) -> None:
    """keep: "earlier" or "new". The choice and who made it are saved."""
    if keep not in ("earlier", "new"):
        raise TrackerError("Choose the earlier value or the new value.")
    by = clean_name(by)
    record = _must_load(case_id, base)
    pending = [c for c in open_conflicts(record) if c["fact"] == fact]
    if not pending:
        raise TrackerError("There is no contradiction to resolve for this fact.")
    for c in pending:
        c["resolved"] = {"keep": keep, "by": by, "on": now()}
    chosen = pending[-1]["new"] if keep == "new" else pending[-1]["earlier"]
    record["facts"][fact] = dict(chosen, confirmed_by=by, confirmed_on=now())
    _note(record, by, f"contradiction resolved: {fact} = {chosen['value']} ({keep} value kept)")
    _save(record, base)
    audit.add_event(case_id, "contradiction resolved", audit.VOLUNTEER,
                    f"{fact} = {chosen['value']} ({keep} value kept, by {by})", base=base)


def confirm_facts(case_id: str, final: Dict[str, object], by: str, base: Path = HERE) -> List[str]:
    """When a volunteer sends the draft, the facts on the checked form are the confirmed ones. Any change
    from an earlier value is saved with who changed it (and goes into the audit record)."""
    by = clean_name(by)
    record = _must_load(case_id, base)
    changed = []
    for fact, value in final.items():
        if fact in NOT_MERGED or fact.startswith("_") or value is None:
            continue
        value = plain(value)
        before = record["facts"].get(fact)
        if before is None or not _same(before["value"], value):
            if before is not None:
                changed.append(f"{fact}: {before['value']} → {value}")
            record["facts"][fact] = {"value": value, "on": now(), "by": by, "source": "checked form"}
    _note(record, by, "draft sent to the supervisor" + (f"; corrected: {', '.join(changed)}" if changed else ""))
    _save(record, base)
    if changed:
        audit.add_event(case_id, "facts corrected on the form", audit.VOLUNTEER, "; ".join(changed) + f" (by {by})",
                        base=base)
    return changed


def add_answers(case_id: str, answers: List[Tuple[str, str]], by: str, base: Path = HERE) -> None:
    """Answers to the AI's questions, so they are never asked again."""
    by = clean_name(by)
    record = _must_load(case_id, base)
    saved = {q for q, _ in record.get("answers", [])}
    new = [(clean_text(q, 200), clean_text(a)) for q, a in answers if q not in saved and (a or "").strip()]
    if new:
        record.setdefault("answers", []).extend([list(x) for x in new])
        _note(record, by, f"{len(new)} answers added")
        _save(record, base)


def add_summary(case_id: str, what_happened: List[str], issues: List[Tuple[str, str]], documents_held: List[str],
                by: str, ai_model: Optional[str] = None, base: Path = HERE) -> None:
    """Lines from the checked summary (never the notes). New lines are added after the earlier ones."""
    by = clean_name(by)
    record = _must_load(case_id, base)

    def add(key, items):
        have = [x if isinstance(x, str) else tuple(x) for x in record.get(key, [])]
        for item in items:
            item = clean_text(item) if isinstance(item, str) else tuple(clean_text(str(x), 100) for x in item)
            if item and item not in have:
                have.append(item)
        record[key] = [x if isinstance(x, str) else list(x) for x in have]

    add("summary", what_happened)
    add("issues", issues)
    add("documents_held", documents_held)
    if ai_model:
        record["ai_model"], record["ai_read_at"] = ai_model, now()
    _note(record, by, "summary updated from new notes")
    _save(record, base)


# ---------- visit log and camps ----------

def add_visit(case_id: str, on: date, by: str, how: str, learned: str = "", done: str = "", next_step: str = "",
              next_due: Optional[date] = None, base: Path = HERE, today: Optional[date] = None) -> dict:
    by = clean_name(by)
    today = today or date.today()
    if how not in VISIT_WAYS:
        raise TrackerError("Choose how you met: " + ", ".join(VISIT_WAYS) + ".")
    if on > today:
        raise TrackerError("The visit date can't be in the future.")
    if next_due and not next_step.strip():
        raise TrackerError("Write the next step for the due date.")
    if not any(x.strip() for x in (learned, done, next_step)):
        raise TrackerError("Write what was learned, what was done or the next step.")
    record = _must_load(case_id, base)
    visit = {"on": on.isoformat(), "by": by, "how": how, "learned": clean_text(learned), "done": clean_text(done),
             "next_step": clean_text(next_step, 200), "next_due": next_due.isoformat() if next_due else None,
             "added": now()}
    record.setdefault("visits", []).append(visit)
    _note(record, by, f"visit logged ({how}, {visit['on']})")
    _save(record, base)
    audit.add_event(case_id, "visit logged", audit.VOLUNTEER, f"{how} on {visit['on']}, by {by}", base=base)
    return visit


def _clean_camp(village: str, district: str, on) -> dict:
    village, district = clean_text(village, 60), clean_text(district, 60)
    if not village or not district:
        raise TrackerError("Give the camp's village and district.")
    if isinstance(on, str):
        on = date.fromisoformat(on)
    return {"village": village, "district": district, "date": on.isoformat()}


def set_camp(case_id: str, village: str, district: str, on: date, by: str, base: Path = HERE) -> dict:
    by = clean_name(by)
    record = _must_load(case_id, base)
    record["camp"] = _clean_camp(village, district, on)
    _note(record, by, f"tagged with camp {camp_label(record['camp'])}")
    _save(record, base)
    return record["camp"]


def camp_label(camp: Optional[dict]) -> str:
    return f"{camp['village']}, {camp['district']} ({camp['date']})" if camp else ""


# ---------- status, next step, the tracker list ----------

def _here(fn, *args, base: Path):
    """Call store / timeline readers the same way the screens do (no folder for the app's own records)."""
    return fn(*args) if Path(base).resolve() == HERE else fn(*args, base=base)


def _status(case_id: str, listed: Optional[dict], base: Path) -> str:
    if listed is None:
        return INTAKE
    if listed["status"] != store.APPROVED:
        return listed["status"]
    stage = timeline.stage(_here(timeline.load, case_id, base=base))
    return {timeline.SUBMITTED_STAGE: SUBMITTED, timeline.ACKNOWLEDGED_STAGE: ACKNOWLEDGED}.get(stage, store.APPROVED)


def _with_review(status: str, record: Optional[dict]) -> str:
    return CHANGED if status in APPROVED_STATUSES and (record or {}).get("review_needed") else status


def status_of(case_id: str, base: Path = HERE) -> str:
    """intake not finished -> waiting / sent back -> approved (or changed after approval) -> submitted ->
    acknowledged."""
    listed = next((c for c in _here(store.list_cases, base=base) if c["id"] == case_id), None)
    return _with_review(_status(case_id, listed, base), load(case_id, base))


NEXT_REVIEW, NEXT_FIX, NEXT_INTAKE = "Supervisor to review the draft", "Fix the draft and resend it", \
    "Finish the intake and send the draft to the supervisor"
NEXT_RECHECK = "Supervisor to review the changes"


def next_step(record: Optional[dict], status: str, case_id: str, base: Path = HERE,
              today: Optional[date] = None) -> Tuple[str, Optional[str], Optional[timeline.Step]]:
    """(next step, due date YYYY-MM-DD or None, the timeline step if it is one)."""
    if status == store.WAITING:
        return NEXT_REVIEW, None, None
    if status == store.SENT_BACK:
        return NEXT_FIX, None, None
    if status == CHANGED:
        return NEXT_RECHECK, None, None
    chosen = (record or {}).get("next")  # set with "Edit case"; newer than any visit's next step
    if chosen and chosen.get("step") and not any(v.get("next_step") and v.get("added", "") > chosen["on"]
                                                 for v in (record or {}).get("visits", [])):
        return chosen["step"], chosen.get("due"), None
    if status in APPROVED_STATUSES:
        tl = _here(timeline.load, case_id, base=base)
        if tl:
            step = timeline.next_due(timeline.steps_of(tl), today or date.today())
            if step:
                return step.title, step.due, step
        return "", None, None
    for visit in reversed((record or {}).get("visits", [])):
        if visit.get("next_step"):
            return visit["next_step"], visit.get("next_due"), None
    return NEXT_INTAKE, None, None


next_step_of = next_step


def volunteers(record: Optional[dict]) -> List[str]:
    names = []
    for h in (record or {}).get("history", []) + (record or {}).get("visits", []):
        if h.get("by") and h["by"] not in names:
            names.append(h["by"])
    return names


def rows(base: Path = HERE, today: Optional[date] = None) -> List[dict]:
    """Every case: from the tracker, plus older cases sent before the tracker existed."""
    today = today or date.today()
    records = {r["id"]: r for r in all_records(base)}
    listed = {c["id"]: c for c in _here(store.list_cases, base=base)}
    out = []
    for case_id in sorted(set(records) | set(listed), reverse=True):
        record = records.get(case_id)
        status = _with_review(_status(case_id, listed.get(case_id), base), record)
        step, due, tl_step = next_step(record, status, case_id, base, today)
        # Eligibility dates are not deadlines, so they are never overdue (timeline.next_due leaves out
        # the ones already reached).
        overdue = bool(due) and date.fromisoformat(due) < today and not (tl_step and tl_step.eligibility_date)
        out.append({"id": case_id, "code": (record or {}).get("code", ""),
                    "case_type": listed.get(case_id, {}).get("case_type") or (record or {}).get("case_type", ""),
                    "status": status, "next_step": step, "step": tl_step, "due": due, "overdue": overdue,
                    "camp": camp_label((record or {}).get("camp")), "volunteers": volunteers(record),
                    "last_by": (record or {}).get("last_by", ""), "last_at": (record or {}).get("last_at", "")})
    return out


def filter_rows(all_rows: List[dict], status: Optional[str] = None, camp: Optional[str] = None,
                volunteer: Optional[str] = None, hide_intake: bool = False) -> List[dict]:
    return [r for r in all_rows
            if (not status or r["status"] == status)
            and (not camp or r["camp"] == camp)
            and (not volunteer or volunteer in r["volunteers"])
            and not (hide_intake and r["status"] == INTAKE)]


# ---------- editing a case: every change audited, approved versions kept ----------

def _show(value) -> str:
    return "(empty)" if value in (None, "") else str(value)


def edit_case(case_id: str, by: str, facts: Optional[Dict[str, object]] = None, note: str = "",
              next_step: Optional[str] = None, next_due: Optional[date] = None, base: Path = HERE,
              today: Optional[date] = None) -> List[dict]:
    """Change facts, add a note, or change the next step and its date. Returns the changes, each
    {"field", "old", "new"}. Every change goes into the case's edit list and the audit record (who,
    when, old -> new). If the case was already approved, the approved version is kept as it was and
    the edited case becomes a new version marked "Changed after approval: needs supervisor review
    again". Nothing changed: an error."""
    by = clean_name(by)
    today = today or date.today()
    record = _must_load(case_id, base)
    status = status_of(case_id, base)
    changes = []
    for fact, value in (facts or {}).items():
        if fact in NOT_MERGED or fact.startswith("_") or value is None or value == "":
            continue
        value = plain(value)
        before = record.get("facts", {}).get(fact)
        if before is None or not _same(before["value"], value):
            changes.append({"field": fact, "old": before["value"] if before else None, "new": value})
    note = clean_text(note)
    if note:
        changes.append({"field": "note", "old": None, "new": note})
    if next_step is not None or next_due is not None:
        step = clean_text(next_step or "", 200)
        if next_due and not step:
            raise TrackerError("Write the next step for the due date.")
        due = next_due.isoformat() if next_due else None
        if due and next_due < today - timedelta(days=365):
            raise TrackerError("The due date is more than a year ago. Check it.")
        old_step, old_due, _ = next_step_of(record, status, case_id, base, today)
        if step and step != old_step:
            changes.append({"field": "next step", "old": old_step or None, "new": step})
        if step and due != old_due:
            changes.append({"field": "next step date", "old": old_due, "new": due})
    if not changes:
        raise TrackerError("Nothing was changed.")

    after_approval = status in APPROVED_STATUSES or status == CHANGED
    if after_approval and not record.get("review_needed"):
        # Keep the approved version exactly as it was (the approved draft and case file are not touched).
        record.setdefault("versions", []).append({
            "version": record.get("version", 1), "approved": True, "kept_on": now(),
            "facts": copy.deepcopy(record.get("facts", {})), "next": copy.deepcopy(record.get("next")),
            "notes": copy.deepcopy(record.get("notes", []))})
        record["version"] = record.get("version", 1) + 1
        record["review_needed"] = {"since": now(), "by": by, "version": record["version"]}

    stamp = now()
    for c in changes:
        if c["field"] == "note":
            record.setdefault("notes", []).append({"on": stamp, "by": by, "text": c["new"]})
        elif c["field"] not in ("next step", "next step date"):
            record.setdefault("facts", {})[c["field"]] = {"value": c["new"], "on": stamp, "by": by,
                                                          "source": "edited by a volunteer", "previous": c["old"]}
            for conflict in open_conflicts(record):  # an edit settles an open contradiction on this fact
                if conflict["fact"] == c["field"]:
                    conflict["resolved"] = {"keep": "edited", "by": by, "on": stamp}
    if any(c["field"] in ("next step", "next step date") for c in changes):
        record["next"] = {"step": clean_text(next_step or "", 200),
                          "due": next_due.isoformat() if next_due else None, "on": stamp, "by": by}
    record.setdefault("edits", []).append({"time": stamp, "by": by, "version": record.get("version", 1),
                                           "after_approval": after_approval, "changes": changes})
    said = "; ".join(f"{c['field']}: {_show(c['old'])} -> {_show(c['new'])}" for c in changes)
    _note(record, by, "case edited: " + said)
    _save(record, base)
    event = "case edited" + (f" ({REVIEW_AGAIN}, version {record['version']})" if after_approval else "")
    audit.add_event(case_id, event, audit.VOLUNTEER, f"by {by}: {said}", base=base, changes=changes)
    return changes


def mark_reviewed(case_id: str, base: Path = HERE) -> None:
    """The supervisor has looked at the changes made after approval."""
    record = _must_load(case_id, base)
    pending = record.get("review_needed")
    if not pending:
        raise TrackerError("This case has no changes waiting for review.")
    record.setdefault("reviews", []).append({"version": pending["version"], "on": now(), "by": audit.SUPERVISOR})
    record["review_needed"] = None
    _note(record, "supervisor", f"changes after approval reviewed (version {pending['version']})")
    _save(record, base)
    audit.add_event(case_id, "changes after approval reviewed", audit.SUPERVISOR,
                    f"version {pending['version']}", base=base)


def needs_review(base: Path = HERE) -> List[dict]:
    return [r for r in all_records(base) if r.get("review_needed")]


# ---------- the case slip ----------

SLIP_EN, SLIP_HI = "Bring this next time", "अगली बार यह साथ लाएँ"


def continue_link(app_url: str, code: str) -> str:
    """The QR code's link: the app with the code, so a phone camera opens the case (after the passcode)."""
    return f"{app_url.rstrip('/')}/?code={code}" if app_url else code


def code_from_qr_text(text: str) -> str:
    """The case code inside a slip's QR code: the link "https://.../?code=K7M2QX", or the code alone
    (no app address set). Raises TrackerError if it is not a case slip."""
    text = (text or "").strip()
    found = re.search(r"[?&]code=([^&#\s]+)", text)
    try:
        return normalise_code(found.group(1) if found else text)
    except TrackerError:
        raise TrackerError("This QR code is not from a case slip. Type the code instead.")


def read_qr(image_bytes: bytes) -> str:
    """The case code from a photo of the slip (zxing-cpp, a small QR reader). Raises TrackerError."""
    import io

    import zxingcpp
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise TrackerError("Could not read the photo. Try again, or type the code.")
    results = zxingcpp.read_barcodes(image)
    if not results:
        raise TrackerError("No QR code found in the photo. Hold the slip flat and close, or type the code.")
    return code_from_qr_text(results[0].text)


def qr_png_data_uri(app_url: str, code: str) -> str:
    import segno
    return segno.make(continue_link(app_url, code), error="m").png_data_uri(scale=8, border=2)


def slip_lines(record: dict, clinic: str) -> Dict[str, str]:
    """Everything printed on the slip. On purpose NOT the case type, the problem or any legal issue:
    someone else may see the slip (for example in a domestic violence case)."""
    return {"clinic": clean_text(clinic, 80) or "Legal aid clinic", "case_id": record["id"], "code": record["code"],
            "bring_en": SLIP_EN, "bring_hi": SLIP_HI, "help_112": "112", "help_15100": "15100"}
