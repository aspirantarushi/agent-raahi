"""Safe abstention: find contradictions and missing key facts. Plain code.

If facts contradict each other, or a key fact is missing, the agent must not conclude. The screen
shows "Cannot conclude yet: [reason]" and what is needed; no dates, draft or summary are produced
until it is resolved.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set

import privacy

NEGATION = re.compile(r"\b(?:no|not|never|none|nobody|without|nahi|nahin|na)\b|नहीं|ना\b|कोई\s+\S+\s+नहीं", re.I)
ANOTHER_CASE = re.compile(r"another case|other case|one more case|second case|separate case|"
                          r"दूसरा केस|दूसरे केस|एक और केस|अन्य केस|doosra case|dusra case|ek aur case|aur ek case", re.I)
CONVICTION = re.compile(r"\bconvicted\b|\bconviction\b|\bsentenced\b|सज़ा हुई|सजा हुई|सज़ा काट|दोषी ठहराया|"
                        r"saza hui|saja hui", re.I)


@dataclass
class Problem:
    reason: str                    # i18n key: abstain.<reason>
    needed: str                    # i18n key: abstain.needed.<needed>
    params: Dict[str, str] = field(default_factory=dict)
    confirm_fact: Optional[str] = None  # an AI-versus-volunteer disagreement the volunteer can confirm


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+|\n", privacy.normalise_digits(text or "")) if s.strip()]


def mentioned_without_negation(text: str, pattern: re.Pattern) -> Optional[str]:
    """A sentence that mentions the pattern and does not deny it (so "No other cases are pending" doesn't count)."""
    for sentence in _sentences(text):
        if pattern.search(sentence) and not NEGATION.search(sentence):
            return sentence
    return None


def _show(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, date):
        return value.isoformat()
    return "" if value is None else str(value)


# ---------- Section 479 cases ----------

def undertrial_problems(form: Dict[str, object], ai_read: Optional[Dict[str, object]] = None, notes: str = "",
                        confirmed: Optional[Set[str]] = None, today: Optional[date] = None) -> List[Problem]:
    """form: custody_began, offence_date, today, never_convicted, other_cases_pending, law, section, ...
    ai_read: what the AI read from the notes (accepted by intake checks); confirmed: facts the volunteer
    confirmed after a disagreement."""
    problems: List[Problem] = []
    confirmed = confirmed or set()
    today = form.get("today") or today or date.today()
    custody, offence = form.get("custody_began"), form.get("offence_date")

    if custody is None:
        problems.append(Problem("missing_custody", "custody"))
    if custody and offence and offence > custody:
        problems.append(Problem("offence_after_custody", "dates", {"offence": offence.isoformat(),
                                                                  "custody": custody.isoformat()}))
    if custody and custody > today:
        problems.append(Problem("custody_future", "dates", {"custody": custody.isoformat(), "today": today.isoformat()}))
    if offence and offence > today:
        problems.append(Problem("offence_future", "dates"))

    for fact, value in (ai_read or {}).items():
        if fact in ("all_sections", "more_than_one_section") or fact not in form or fact in confirmed:
            continue
        if _show(value) != _show(form[fact]):
            problems.append(Problem("ai_vs_volunteer", "confirm",
                                    {"fact": fact, "ai": _show(value), "form": _show(form[fact])}, confirm_fact=fact))

    if form.get("other_cases_pending") is False:
        quote = mentioned_without_negation(notes, ANOTHER_CASE)
        if quote:
            problems.append(Problem("other_cases", "other_cases", {"quote": quote}))
    if form.get("never_convicted") is True:
        quote = mentioned_without_negation(notes, CONVICTION)
        if quote:
            problems.append(Problem("convictions", "convictions", {"quote": quote}))
    return problems


# ---------- Any-case summaries ----------

def general_problems(g, notes: str = "") -> List[Problem]:
    """g: general.GeneralFacts."""
    problems: List[Problem] = []
    if not g.what_happened and not g.issues:
        problems.append(Problem("general_unclear", "general"))
    return problems
