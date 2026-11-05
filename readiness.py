"""Readiness checklist for each draft type. Plain code.

Each draft type has required fields. Each field is "present", "missing", "uncertain", or
"cannot obtain" (the volunteer marks it, with a short reason, instead of guessing).
A draft is "Ready for review" only when every required field is present or marked cannot obtain;
otherwise it is "Not ready: N items missing". Sending is still allowed, with the gaps listed at
the top of the draft. Names, phone numbers and addresses are never required here: they are filled
in by hand, outside the app.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import lang

PRESENT, MISSING, UNCERTAIN, CANNOT = "present", "missing", "uncertain", "cannot obtain"

# Case details the volunteer may type (case numbers and places only; never personal details).
DETAIL_FIELDS = ["court", "cnr", "fir", "police_station", "jail", "district"]


@dataclass
class Item:
    key: str
    status: str
    note: str = ""      # for example the reason for "uncertain" or "cannot obtain"

    def label(self, code: str = "en") -> str:
        return lang.t(f"ready.{self.key}", code)


def _given(value) -> bool:
    return value is not None and str(value).strip() != ""


def apply_cannot(items: List[Item], cannot: Dict[str, str]) -> List[Item]:
    """Fields marked "cannot obtain" (with a reason) by the volunteer."""
    for item in items:
        reason = (cannot or {}).get(item.key, "").strip()
        if item.status in (MISSING, UNCERTAIN) and reason:
            item.status, item.note = CANNOT, reason
    return items


# ---------- the three draft types ----------

def section479_items(facts, result, details: Dict[str, str], skipped=(), cannot=None) -> List[Item]:
    """facts: drafts.UndertrialFacts; result: section479.Result; skipped: facts the volunteer said "don't know"."""
    o = result.offence
    items = [
        Item("sections", PRESENT),
        Item("offence_date", PRESENT if facts.offence_date else MISSING),
        Item("custody_began", PRESENT if facts.custody_began else MISSING),
        Item("previous_convictions", UNCERTAIN if "never_convicted" in skipped else PRESENT,
             "not known" if "never_convicted" in skipped else ""),
        Item("other_cases", UNCERTAIN if "other_cases_pending" in skipped else PRESENT,
             "not known" if "other_cases_pending" in skipped else ""),
    ]
    if o.ask_to_decide:
        answered = bool(facts.answer.strip()) and facts.question_answered
        items.append(Item("deciding_question", PRESENT if answered else UNCERTAIN,
                          "" if answered else "not answered and confirmed"))
    items.append(Item("one_section", UNCERTAIN if facts.more_than_one_section else PRESENT,
                      "more than one section: a lawyer must check Section 479(2)" if facts.more_than_one_section else ""))
    items += [
        Item("court", PRESENT if _given(details.get("court")) else MISSING),
        Item("cnr", PRESENT if _given(details.get("cnr")) else MISSING),
        Item("fir", PRESENT if _given(details.get("fir")) and _given(details.get("police_station")) else MISSING),
        Item("jail", PRESENT if _given(details.get("jail")) else MISSING),
        Item("district", PRESENT if _given(details.get("district")) else MISSING),
    ]
    return apply_cannot(items, cannot)


def dlsa_items(details: Dict[str, str], cannot=None) -> List[Item]:
    """The DLSA application added when the person in custody has no lawyer."""
    items = [
        Item("dlsa_district", PRESENT if _given(details.get("district")) else MISSING),
        Item("dlsa_case_number", PRESENT if _given(details.get("cnr")) or _given(details.get("fir")) else MISSING),
        Item("dlsa_eligibility_ground", PRESENT, "in custody: qualifies whatever the income"),
    ]
    return apply_cannot(items, cannot)


def general_items(g, eligibility, cannot=None) -> List[Item]:
    """g: general.GeneralFacts; eligibility: general.Eligibility."""
    f = g.facts
    items = [
        Item("what_happened", PRESENT if g.what_happened else MISSING),
        Item("person_role", PRESENT if _given(g.person) else MISSING),
        Item("danger_checked", PRESENT if f.get("danger_now") is not None else UNCERTAIN, "" if f.get(
            "danger_now") is not None else "not stated whether anyone is in danger"),
        Item("custody_checked", PRESENT if f.get("in_custody") is not None else UNCERTAIN),
        Item("problem_named", PRESENT if g.issues else MISSING),
        Item("legal_aid_decided", PRESENT if eligibility.status != "not decided yet" else UNCERTAIN),
        Item("documents_listed", PRESENT if g.documents_held else UNCERTAIN, "" if g.documents_held else "none mentioned"),
        Item("questions_answered", PRESENT if not g.still_to_ask else UNCERTAIN,
             "" if not g.still_to_ask else f"{len(g.still_to_ask)} question(s) still open"),
    ]
    return apply_cannot(items, cannot)


# ---------- step 3, "Draft and research": items that fit the case type, each with a fix ----------

# key -> how the volunteer fixes it on the spot (the screen draws the matching field)
FIXES = {"case_story": "back", "case_person": "text", "case_outcome": "text", "case_state": "state",
         "case_dates": "dates", "case_reference": "yesno", "case_documents": "documents",
         "case_legal_aid": "eligibility", "case_questions": "back", "case_danger": "yesno", "case_custody": "yesno",
         "case_1930": "yesno"}
TYPE_ITEMS = {
    "electricity": ["case_reference"], "water": ["case_reference"], "ration": ["case_reference"],
    "custody": ["case_custody", "case_danger"], "fraud": ["case_danger", "case_1930"],
    "family": ["case_danger"], "land": [], "wages": [], "other": ["case_danger"],
}


def case_items(g, eligibility, kind: str, missing_years, cannot=None) -> List[Item]:
    """The checklist for step 3 in plain words, with only the items that fit the problem type
    (no "in custody" for an electricity case). The consumer / application number is recorded only as
    "has it: yes or no"; the number itself is never typed or stored."""
    f = g.facts
    items = [
        Item("case_story", PRESENT if g.what_happened else MISSING),
        Item("case_person", PRESENT if _given(g.person) else MISSING),
        Item("case_outcome", PRESENT if _given(g.outcome) else MISSING),
        Item("case_state", PRESENT if _given(f.get("state")) else MISSING),
        Item("case_dates", PRESENT if not missing_years else MISSING,
             "" if not missing_years else "; ".join(w for w, _ in missing_years)),
        Item("case_documents", PRESENT if g.documents_held else MISSING),
        Item("case_legal_aid", PRESENT if eligibility.status != "not decided yet" else MISSING),
        Item("case_questions", PRESENT if not g.still_to_ask else MISSING,
             "" if not g.still_to_ask else str(len(g.still_to_ask))),
    ]
    for key in TYPE_ITEMS.get(kind, []):
        fact = {"case_reference": "has_reference_number", "case_danger": "danger_now", "case_custody": "in_custody",
                "case_1930": "called_1930"}[key]
        items.append(Item(key, PRESENT if f.get(fact) is not None else MISSING))
    return apply_cannot(items, cannot)


# ---------- the verdict and the gaps block ----------

def gaps(items: List[Item]) -> List[Item]:
    return [i for i in items if i.status in (MISSING, UNCERTAIN)]


def is_ready(items: List[Item]) -> bool:
    return not gaps(items)


def button_label(items: List[Item], code: str = "en") -> str:
    if is_ready(items):
        return lang.t("ready.button_ready", code)
    return lang.t("ready.button_not_ready", code, n=len(gaps(items)))


def gaps_block(items: List[Item], code: str = "en") -> str:
    """Listed at the top of a draft sent while not ready (and fields marked "cannot obtain")."""
    lines = []
    open_items = gaps(items)
    cannot = [i for i in items if i.status == CANNOT]
    if open_items:
        lines.append(lang.t("ready.block_not_ready", code, n=len(open_items)))
        lines += [f"- {i.label(code)}: {lang.t('ready.status.' + i.status, code)}" + (f" ({i.note})" if i.note else "")
                  for i in open_items]
    if cannot:
        lines.append(lang.t("ready.block_cannot", code))
        lines += [f"- {i.label(code)}: {i.note}" for i in cannot]
    return "\n".join(lines)


def add_gaps_to_draft(draft: str, items: List[Item], code: str = "en") -> str:
    """Put the gaps block under the draft's header lines (the DRAFT line stays first)."""
    block = gaps_block(items, code)
    if not block:
        return draft
    lines = draft.split("\n")
    header = 1
    while header < len(lines) and lines[header].strip() and header < 3:  # Hindi header + translation label
        header += 1
    return "\n".join(lines[:header] + ["", block] + lines[header:])


# ---------- filling case details into a draft ----------

DETAIL_BLANKS = {
    "en": {"[district]": "district", "[jail name]": "jail", "[court]": "court"},
    "hi": {"[ज़िला]": "district", "[जेल का नाम]": "jail", "[अदालत]": "court"},
}


def fill_details(draft: str, details: Dict[str, str], code: str = "en") -> str:
    """Put the case numbers and places the volunteer typed into the draft's blanks."""
    d = {k: (details.get(k) or "").strip() for k in DETAIL_FIELDS}
    case_no = d["cnr"] or d["fir"]
    if code == "hi":
        pairs = {"[अदालत, CNR]": f"{d['court'] or '[अदालत]'}, {'CNR ' + d['cnr'] if d['cnr'] else '[CNR]'}",
                 "[FIR, थाना]": f"{d['fir'] or '[FIR]'}, {d['police_station'] or '[थाना]'}",
                 "[केस / FIR नंबर]": case_no or "[केस / FIR नंबर]",
                 "[अदालत, केस / FIR नंबर]": f"{d['court'] or '[अदालत]'}, {case_no or '[केस / FIR नंबर]'}"}
    else:
        pairs = {"[court, CNR]": f"{d['court'] or '[court]'}, {'CNR ' + d['cnr'] if d['cnr'] else '[CNR]'}",
                 "[FIR, police station]": f"{d['fir'] or '[FIR]'}, {d['police_station'] or '[police station]'}",
                 "[case / FIR number]": case_no or "[case / FIR number]",
                 "[court, case / FIR number]": f"{d['court'] or '[court]'}, {case_no or '[case / FIR number]'}"}
    for blank, value in pairs.items():
        if any(d[k] for k in ("court", "cnr", "fir", "police_station")):
            draft = draft.replace(blank, value)
    for blank, key in DETAIL_BLANKS.get(code, {}).items():
        if d[key]:
            draft = draft.replace(blank, d[key])
    return draft
