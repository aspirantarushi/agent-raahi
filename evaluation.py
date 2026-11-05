"""Evaluation mode, for an honest impact study (practice data only). Plain code.

- 10 fictional cases in evaluation/cases/, each with an answer key of required facts.
- A volunteer does a case "by hand" (a plain form, no AI, no checklist) or "with the agent"; the app
  records the start and end times.
- A reviewer scores each finished session: required fields correct, material errors, major corrections
  needed, accepted yes/no.
- Export raw counts to CSV. No averages are filled in in advance and no results are invented.
Sessions are saved through storage.py (evaluation/sessions, kept out of git).
"""

import csv
import io
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import privacy
import storage

HERE = Path(__file__).resolve().parent
BY_HAND, WITH_AGENT = "by hand", "with the agent"
METHODS = [BY_HAND, WITH_AGENT]
CSV_COLUMNS = ["case", "method", "reviewer", "minutes", "missing_fields", "material_errors", "major_corrections",
               "accepted"]


def cases(base: Path = HERE) -> List[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((base / "evaluation" / "cases").glob("*.json"))]


def case(case_id: str, base: Path = HERE) -> dict:
    for c in cases(base=base):
        if c["id"] == case_id:
            return c
    raise ValueError("No such evaluation case.")


def _save(session: dict, base: Path) -> None:
    storage.write_json("eval_sessions", session["session_id"], session, base)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(text: str, limit: int = 60) -> str:
    return privacy.redact((text or "").strip()[:limit])[0]


def start(case_id: str, method: str, volunteer: str, base: Path = HERE, started: Optional[str] = None) -> dict:
    """Start timing a case. volunteer: a pseudonym such as "Volunteer 1" (no real names needed)."""
    case(case_id, base=base)
    if method not in METHODS:
        raise ValueError("Choose a method: by hand or with the agent.")
    volunteer = _clean(volunteer)
    if not volunteer:
        raise ValueError("Enter a volunteer pseudonym, for example Volunteer 1.")
    session = {"session_id": f"S-{datetime.now():%Y%m%d}-{secrets.token_hex(3)}", "case": case_id,
               "method": method, "volunteer": volunteer, "started": started or now(), "finished": None,
               "submission": {}, "scores": [], "practice": True}
    _save(session, base)
    return session


def load(session_id: str, base: Path = HERE) -> dict:
    if "/" in session_id or ".." in session_id:
        raise ValueError("No such evaluation session.")
    session = storage.read_json("eval_sessions", session_id, base)
    if session is None:
        raise ValueError("No such evaluation session.")
    return session


def finish(session_id: str, submission: Dict[str, str], base: Path = HERE, finished: Optional[str] = None) -> dict:
    """Stop the clock. submission: the by-hand answers, or {"agent_case": case number, "draft": text}."""
    session = load(session_id, base=base)
    if session["finished"]:
        raise ValueError("This session is already finished.")
    session["finished"] = finished or now()
    session["submission"] = {k: privacy.redact(str(v))[0] for k, v in submission.items()}
    _save(session, base)
    return session


def minutes(session: dict) -> Optional[float]:
    if not session.get("finished"):
        return None
    took = datetime.fromisoformat(session["finished"]) - datetime.fromisoformat(session["started"])
    return round(took.total_seconds() / 60, 1)


def sessions(base: Path = HERE, finished_only: bool = False) -> List[dict]:
    found = [s for s in storage.all_json("eval_sessions", base) if str(s.get("session_id", "")).startswith("S-")]
    return [s for s in found if s["finished"]] if finished_only else found


def score(session_id: str, reviewer: str, fields_correct: int, material_errors: int, major_corrections: int,
          accepted: bool, base: Path = HERE) -> dict:
    """A reviewer's raw counts for one finished session."""
    session = load(session_id, base=base)
    if not session["finished"]:
        raise ValueError("Score a session only after it is finished.")
    total = len(case(session["case"], base=base)["required"])
    reviewer = _clean(reviewer)
    if not reviewer:
        raise ValueError("Enter the reviewer's name or initials.")
    for n in (fields_correct, material_errors, major_corrections):
        if not isinstance(n, int) or n < 0:
            raise ValueError("Counts must be whole numbers, 0 or more.")
    if fields_correct > total:
        raise ValueError(f"This case has {total} required fields.")
    entry = {"reviewer": reviewer, "fields_correct": fields_correct, "missing_fields": total - fields_correct,
             "material_errors": material_errors, "major_corrections": major_corrections,
             "accepted": bool(accepted), "scored_at": now()}
    session["scores"] = [s for s in session["scores"] if s["reviewer"] != reviewer] + [entry]
    _save(session, base)
    return entry


def export_csv(base: Path = HERE) -> str:
    """One row per (session, reviewer score): raw counts only, nothing averaged or filled in."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for s in sessions(base=base, finished_only=True):
        for sc in s["scores"]:
            writer.writerow([s["case"], s["method"], sc["reviewer"], minutes(s), sc["missing_fields"],
                             sc["material_errors"], sc["major_corrections"], "yes" if sc["accepted"] else "no"])
    return out.getvalue()
