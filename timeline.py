"""Next-step timelines for approved cases. Plain code, no AI.

Each approved case gets steps with a status (to do / done / not needed), a due date and who did
it. Dates that come from the law show their knowledge-file Source line; every other date is a
suggested follow-up (or a date the volunteer entered), never presented as a legal deadline.
Every change is added to the case's audit record. Saved through storage.py (timelines, kept out of git).
"""

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import audit
import knowledge
import privacy
import section479
import storage

HERE = Path(__file__).resolve().parent
TO_DO, DONE, NOT_NEEDED = "to do", "done", "not needed"
LEGAL, SUGGESTED, ENTERED = "legal", "suggested", "entered"
SUGGESTED_LABEL = "suggested follow-up, not a legal deadline"
ENTERED_LABEL = "date entered by the volunteer"
SUGGESTED_DAYS = 7
# Section 479 one-third and one-half dates: the person becomes eligible on them. They are not
# deadlines, so they are never "overdue"; the "ask whether the superintendent has applied" step is.
ELIGIBILITY_STEP_IDS = {"s479-third", "s479-half"}
ELIGIBILITY_LABEL = "eligibility date, not a deadline"

DECISION_ENTRY = ("legal_aid_eligibility.md", "How long a decision takes")
REFUSED_ENTRY = ("legal_aid_eligibility.md", "If the application is refused")
S479_ENTRY = ("undertrial_bail.md", "Section 479: release after a share of the maximum sentence")
WHO_APPLIES_ENTRY = ("undertrial_bail.md", "Who applies under Section 479")


@dataclass
class Step:
    id: str
    title: str
    status: str = TO_DO
    due: Optional[str] = None          # ISO date
    kind: str = SUGGESTED              # legal / suggested / entered
    source_line: str = ""              # for legal dates (and steps that rest on a legal duty)
    note: str = ""
    due_editable: bool = True          # legal due dates are worked out, never typed
    done_on: Optional[str] = None
    done_by: str = ""
    details: Dict[str, str] = field(default_factory=dict)

    def due_date(self) -> Optional[date]:
        return date.fromisoformat(self.due) if self.due else None

    @property
    def eligibility_date(self) -> bool:
        return self.id in ELIGIBILITY_STEP_IDS

    def label(self) -> str:
        if not self.due:
            return ""
        if self.eligibility_date:
            return ELIGIBILITY_LABEL
        if self.kind == LEGAL:
            return "legal date"
        return ENTERED_LABEL if self.kind == ENTERED else SUGGESTED_LABEL


# ---------- creating timelines (at approval) ----------

def _suggested(approved_on: date, days: int = SUGGESTED_DAYS) -> str:
    return (approved_on + timedelta(days=days)).isoformat()


def dlsa_steps(approved_on: date) -> List[Step]:
    decision = knowledge.get(*DECISION_ENTRY)
    refused = knowledge.get(*REFUSED_ENTRY)
    return [
        Step("dlsa-submitted", "Application submitted to the DLSA", due=_suggested(approved_on),
             note="Enter the date the application was handed in."),
        Step("dlsa-decision", "DLSA decision due", kind=LEGAL, due_editable=False,
             source_line=decision.source_line,
             note="Due 7 days after the application is submitted (the date appears once it is marked done)."),
        Step("dlsa-lawyer", "Lawyer assigned",
             note="Record the first meeting date and whether the documents were handed over."),
        Step("dlsa-refused", "Refused"),
        Step("dlsa-appeal", "Appeal to the Chairman", status=NOT_NEEDED, source_line=refused.source_line,
             note="Only if the application is refused. Our files give no time limit: set a date to follow up."),
    ]


def section479_steps(result: section479.Result, approved_on: date) -> List[Step]:
    s479 = knowledge.get(*S479_ENTRY)
    who = knowledge.get(*WHO_APPLIES_ENTRY)
    check = " Dates to be checked by a lawyer." if result.lawyer_check else ""
    steps = [Step("s479-note", "Note given to the DLSA / jail legal aid clinic", due=_suggested(approved_on))]
    upcoming = []
    for key, m in (("s479-third", result.one_third), ("s479-half", result.one_half)):
        if m and m.when:
            steps.append(Step(key, f"{m.name} date", due=m.when.isoformat(), kind=LEGAL, due_editable=False,
                              source_line=s479.source_line, note=(m.note + check).strip()))
            if m.when > approved_on:
                upcoming.append(m.when)
        else:
            steps.append(Step(key, f"{m.name} date", status=NOT_NEEDED, note=m.note if m else ""))
    ask_due = min(upcoming) if upcoming and not any(
        m and m.when and m.reached for m in (result.one_third, result.one_half)) else None
    steps.append(Step("s479-ask", "Ask whether the jail superintendent has applied",
                      due=ask_due.isoformat() if ask_due else _suggested(approved_on),
                      kind=LEGAL if ask_due else SUGGESTED, due_editable=not ask_due,
                      source_line=who.source_line,
                      note="The superintendent must apply once the period is complete; the court decides."))
    steps.append(Step("s479-court", "Next court date", kind=ENTERED,
                      note="Enter the next court date when it is known."))
    return steps


def general_steps(next_steps: List[str]) -> List[Step]:
    return [Step(f"step-{i}", text, note="Set a date to follow up.") for i, text in enumerate(next_steps, 1)]


def create(case_id: str, case_type: str, steps: List[Step], approved_on: date, base: Path = HERE) -> dict:
    steps = list(steps) + handoff_steps()
    record = {"case_id": case_id, "case_type": case_type, "created": approved_on.isoformat(),
              "steps": [asdict(s) for s in steps], "handoff": {}}
    _save(record, base)
    audit.add_event(case_id, "timeline created", "app", f"{len(steps)} steps", base=base)
    return record


def create_for_undertrial(case_id: str, facts, result: section479.Result, approved_on: date,
                          base: Path = HERE) -> dict:
    steps = section479_steps(result, approved_on)
    if getattr(facts, "lawyer", "") == "None":  # the draft included the DLSA application
        steps += dlsa_steps(approved_on)
    return create(case_id, "Undertrial", steps, approved_on, base)


# ---------- reading and saving ----------

def _save(record: dict, base: Path) -> None:
    case = storage.read_json("tracker", record["case_id"], base) or {}
    if case.get("closed"):  # a closed case is read-only until the supervisor reopens it
        raise ValueError("This case is closed, so it can't be changed. The supervisor can reopen it.")
    storage.write_json("timelines", record["case_id"], record, base)


def load(case_id: str, base: Path = HERE) -> Optional[dict]:
    return storage.read_json("timelines", case_id, base)


def load_all(base: Path = HERE) -> List[dict]:
    return storage.all_json("timelines", base)


def steps_of(record: dict) -> List[Step]:
    return [Step(**s) for s in record["steps"]]


def _store_steps(record: dict, steps: List[Step], base: Path) -> None:
    record["steps"] = [asdict(s) for s in steps]
    _save(record, base)


def _find(steps: List[Step], step_id: str) -> Step:
    for s in steps:
        if s.id == step_id:
            return s
    raise ValueError("No such step.")


def _clean_by(by: str) -> str:
    by = privacy.redact((by or "").strip()[:60])[0]
    if not by:
        raise ValueError("Please enter who did this (your name or initials).")
    return by


# ---------- changing steps (each change goes into the audit record) ----------

def mark_done(case_id: str, step_id: str, done_on: date, by: str, details: Optional[Dict[str, str]] = None,
              base: Path = HERE) -> None:
    record = load(case_id, base)
    steps = steps_of(record)
    step = _find(steps, step_id)
    if step.id in (HANDOFF_SUBMITTED, HANDOFF_ACKNOWLEDGED):
        raise ValueError("Use the Submitted / Acknowledged form for this step (who, date, how).")
    if step.status == NOT_NEEDED and step.id == "dlsa-appeal":
        raise ValueError("The appeal is only needed if the application is refused.")
    by = _clean_by(by)
    step.status, step.done_on, step.done_by = DONE, done_on.isoformat(), by
    step.details = {k: privacy.redact(str(v))[0][:100] for k, v in (details or {}).items()}

    # Knock-on effects
    if step.id == "dlsa-submitted":
        decision = _find(steps, "dlsa-decision")
        decision.due = (done_on + timedelta(days=7)).isoformat()
        decision.note = "Within 7 days of the application being received."
    elif step.id == "dlsa-lawyer":
        _find(steps, "dlsa-refused").status = NOT_NEEDED
        _find(steps, "dlsa-appeal").status = NOT_NEEDED
        _find(steps, "dlsa-decision").status = DONE
    elif step.id == "dlsa-refused":
        _find(steps, "dlsa-lawyer").status = NOT_NEEDED
        _find(steps, "dlsa-decision").status = DONE
        appeal = _find(steps, "dlsa-appeal")
        appeal.status = TO_DO
        appeal.due = appeal.due or (done_on + timedelta(days=SUGGESTED_DAYS)).isoformat()
        appeal.kind = SUGGESTED
    _store_steps(record, steps, base)
    detail = f"on {done_on.isoformat()}"
    if step.details:
        detail += "; " + "; ".join(f"{k}: {v}" for k, v in step.details.items())
    audit.add_event(case_id, f"step done: {step.title}", by, detail, base=base)


def mark_not_needed(case_id: str, step_id: str, by: str, reason: str = "", base: Path = HERE) -> None:
    record = load(case_id, base)
    steps = steps_of(record)
    step = _find(steps, step_id)
    if step.id in (HANDOFF_SUBMITTED, HANDOFF_ACKNOWLEDGED):
        raise ValueError("Use the Submitted / Acknowledged form for this step (who, date, how).")
    by = _clean_by(by)
    step.status, step.done_by = NOT_NEEDED, by
    _store_steps(record, steps, base)
    audit.add_event(case_id, f"step not needed: {step.title}", by, privacy.redact(reason[:200])[0], base=base)


def reopen(case_id: str, step_id: str, by: str, base: Path = HERE) -> None:
    record = load(case_id, base)
    steps = steps_of(record)
    step = _find(steps, step_id)
    by = _clean_by(by)
    step.status, step.done_on, step.done_by, step.details = TO_DO, None, "", {}
    _store_steps(record, steps, base)
    audit.add_event(case_id, f"step reopened: {step.title}", by, base=base)


def set_due(case_id: str, step_id: str, due: date, by: str, base: Path = HERE) -> None:
    record = load(case_id, base)
    steps = steps_of(record)
    step = _find(steps, step_id)
    if not step.due_editable:
        raise ValueError("This date comes from the law and is worked out by the app; it can't be changed.")
    by = _clean_by(by)
    step.due = due.isoformat()
    if step.kind == LEGAL:
        step.kind = SUGGESTED
    _store_steps(record, steps, base)
    audit.add_event(case_id, f"date set: {step.title}", by, f"due {due.isoformat()} ({step.label()})", base=base)


# ---------- what needs attention ----------

def is_overdue(step: Step, today: date) -> bool:
    """A to-do step past its date. Eligibility dates are never overdue (see is_reached)."""
    return (step.status == TO_DO and not step.eligibility_date
            and step.due_date() is not None and step.due_date() < today)


def is_reached(step: Step, today: date) -> bool:
    """An eligibility date (Section 479 one-third or one-half) that has come."""
    return step.status == TO_DO and step.eligibility_date and step.due_date() is not None \
        and step.due_date() <= today


def ordered(steps: List[Step]) -> List[Step]:
    """To-do steps with a date first (earliest first), then to-do without a date, then the rest."""
    def key(s: Step):
        if s.status == TO_DO and s.due:
            return (0, s.due)
        return (1, "") if s.status == TO_DO else (2, "")
    return sorted(steps, key=key)


def next_due(steps: List[Step], today: Optional[date] = None) -> Optional[Step]:
    """The earliest to-do step with a date, leaving out eligibility dates already reached
    (they are information, not a task: the "ask" step is the task)."""
    today = today or date.today()
    dated = [s for s in steps if s.status == TO_DO and s.due and not is_reached(s, today)]
    return min(dated, key=lambda s: s.due) if dated else None


OVERDUE, DUE, ELIGIBILITY = "overdue", "due", "eligibility"


def due_this_week(today: date, base: Path = HERE) -> List[Tuple[str, Step, str]]:
    """(case number, step, state) for to-do steps that are overdue or due in the next 7 days, earliest
    first. state: "overdue" (red), "due", or "eligibility" (an eligibility date falling this week).
    Eligibility dates already passed are left out: the "ask" step carries the follow-up."""
    found = []
    if True:
        for record in load_all(base):
            for s in steps_of(record):
                d = s.due_date()
                if s.status != TO_DO or d is None or d > today + timedelta(days=7):  # 7 days, inclusive
                    continue
                if s.eligibility_date:
                    if d >= today:
                        found.append((record["case_id"], s, ELIGIBILITY))
                else:
                    found.append((record["case_id"], s, OVERDUE if d < today else DUE))
    return sorted(found, key=lambda x: x[1].due)


# ---------- handoff: Approved -> Submitted by an authorised worker -> Acknowledged ----------
# A generated draft is never a filing. These two stages are recorded only through these functions,
# with who, when and how, and each goes into the audit record.

HANDOFF_SUBMITTED, HANDOFF_ACKNOWLEDGED = "handoff-submitted", "handoff-acknowledged"
HANDOFF_METHODS = ["in person", "post", "email", "portal"]
ACKNOWLEDGED_BY = ["DLSA", "legal aid clinic", "court", "other"]
APPROVED_STAGE, SUBMITTED_STAGE, ACKNOWLEDGED_STAGE = "approved", "submitted", "acknowledged"


def handoff_steps() -> List[Step]:
    return [Step(HANDOFF_SUBMITTED, "Submitted by an authorised worker", kind=ENTERED,
                 note="Only when an authorised worker has actually handed it in: who, date, and how."),
            Step(HANDOFF_ACKNOWLEDGED, "Acknowledged by the DLSA, clinic or court", kind=ENTERED,
                 note="Their date and reference number, if any.")]


def stage(record: Optional[dict]) -> str:
    handoff = (record or {}).get("handoff", {})
    if handoff.get("acknowledged"):
        return ACKNOWLEDGED_STAGE
    if handoff.get("submitted"):
        return SUBMITTED_STAGE
    return APPROVED_STAGE


def _ensure_handoff_steps(record: dict) -> List[Step]:
    steps = steps_of(record)
    for s in handoff_steps():
        if s.id not in {x.id for x in steps}:
            steps.append(s)
    return steps


def record_submission(case_id: str, who: str, on: date, how: str, base: Path = HERE) -> None:
    record = load(case_id, base)
    if record is None:
        raise ValueError("Only an approved case can be submitted.")
    if stage(record) != APPROVED_STAGE:
        raise ValueError("This case is already recorded as submitted.")
    if how not in HANDOFF_METHODS:
        raise ValueError("Choose how it was submitted: in person, post, email or portal.")
    who = _clean_by(who)
    steps = _ensure_handoff_steps(record)
    step = _find(steps, HANDOFF_SUBMITTED)
    step.status, step.done_on, step.done_by, step.details = DONE, on.isoformat(), who, {"how": how}
    record.setdefault("handoff", {})["submitted"] = {"by": who, "on": on.isoformat(), "how": how}
    _store_steps(record, steps, base)
    audit.add_event(case_id, "submitted by an authorised worker", who, f"on {on.isoformat()}, {how}", base=base)


def record_acknowledgement(case_id: str, by_whom: str, on: date, reference: str = "", recorded_by: str = "",
                           base: Path = HERE) -> None:
    record = load(case_id, base)
    if record is None or stage(record) != SUBMITTED_STAGE:
        raise ValueError("Record the submission first; a case can only be acknowledged after it was submitted.")
    if by_whom not in ACKNOWLEDGED_BY:
        raise ValueError("Choose who acknowledged it: DLSA, legal aid clinic, court or other.")
    submitted_on = date.fromisoformat(record["handoff"]["submitted"]["on"])
    if on < submitted_on:
        raise ValueError("The acknowledgement date can't be before the submission date.")
    recorded_by = _clean_by(recorded_by)
    reference = privacy.redact((reference or "").strip()[:60])[0]
    steps = _ensure_handoff_steps(record)
    step = _find(steps, HANDOFF_ACKNOWLEDGED)
    step.status, step.done_on, step.done_by = DONE, on.isoformat(), recorded_by
    step.details = {"by": by_whom, **({"reference": reference} if reference else {})}
    record["handoff"]["acknowledged"] = {"by": by_whom, "on": on.isoformat(), "reference": reference,
                                         "recorded_by": recorded_by}
    _store_steps(record, steps, base)
    audit.add_event(case_id, "acknowledged", recorded_by,
                    f"by {by_whom} on {on.isoformat()}" + (f", reference {reference}" if reference else ""), base=base)
