"""Checking what the AI read from case notes, and asking for missing facts.

Plain code, no AI. The AI's answer is only a suggestion: every value must come with
the exact words from the notes, and those words must really be in the notes and
really say that value. Anything that fails a check is dropped and asked for instead.

Missing facts are asked one at a time, in the order of knowledge/intake_undertrial.md.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import privacy
import section479

HERE = Path(__file__).resolve().parent
INTAKE_FILE = HERE / "knowledge" / "intake_undertrial.md"

LAWYER_VALUES = ["Legal aid lawyer", "Private lawyer", "None"]

# Form facts and the intake_undertrial.md question that asks for each, in that file's order.
FACT_QUESTIONS = [
    ("custody_began", 2),
    ("offence_date", 3),
    ("section", 4),
    ("never_convicted", 8),
    ("other_cases_pending", 9),
    ("answer", 10),  # the sentence table's ask_to_decide question, when the offence has one
    ("delay_days_by_accused", 11),
    ("lawyer", 12),
]

# Month names in English, Hindi (both common spellings) and Hinglish, by month number.
HINDI_MONTH_NAMES = [
    ["जनवरी"], ["फ़रवरी", "फरवरी"], ["मार्च"], ["अप्रैल", "अप्रेल"], ["मई"], ["जून"], ["जुलाई"], ["अगस्त"],
    ["सितंबर", "सितम्बर"], ["अक्टूबर", "अक्तूबर"], ["नवंबर", "नवम्बर"], ["दिसंबर", "दिसम्बर"]]
HINGLISH_MONTH_NAMES = [
    ["janvari", "janwari"], ["farvari", "farwari", "pharvari"], ["march", "maarch"], ["aprail", "april"],
    ["mai", "may"], ["jun", "joon"], ["julai", "july"], ["agast", "agust"], ["sitambar", "sitamber"],
    ["aktubar", "aktoobar"], ["navambar", "navamber"], ["disambar", "disamber"]]
LAW_WORDS = {"IPC": ["ipc", "आईपीसी", "आई.पी.सी", "भारतीय दंड संहिता", "dand sanhita"],
             "BNS": ["bns", "बीएनएस", "बी.एन.एस", "भारतीय न्याय संहिता", "nyay sanhita", "nyaya sanhita"]}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


@dataclass
class Reading:
    """What was taken from the notes: values that passed the checks, with their evidence."""

    values: Dict[str, object] = field(default_factory=dict)
    evidence: Dict[str, str] = field(default_factory=dict)
    dropped: List[str] = field(default_factory=list)  # AI answers that failed a check
    notes_say: Dict[str, str] = field(default_factory=dict)  # e.g. offence date "February 2024"


# ---------- intake questions from the knowledge file ----------

def intake_questions(path: Path = INTAKE_FILE) -> Dict[int, str]:
    """Question number -> question text, for example 2 -> 'On what date did custody begin ...?'"""
    questions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\d+)\.\s+(.*?)(?:\s+\[[^\]]*\])?\s*$", line)
        if m:
            questions[int(m.group(1))] = m.group(2)
    return questions


def question_order(path: Path = INTAKE_FILE) -> List[str]:
    """Form facts sorted by where their question appears in the intake file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    position = {}
    for i, line in enumerate(lines):
        m = re.match(r"^(\d+)\.\s", line)
        if m:
            position.setdefault(int(m.group(1)), i)
    return [fact for fact, number in sorted(FACT_QUESTIONS, key=lambda fq: position[fq[1]])]


# ---------- checking the AI's answer ----------

def _norm(text: str) -> str:
    return privacy.comparable(text)


def _in_notes(quote: Optional[str], notes: str) -> bool:
    return bool(quote) and _norm(quote) in _norm(notes)


def _date_supported(value: date, quote: str) -> bool:
    """The quote must show the day, the month and the year: no filling in a missing day."""
    q = _norm(quote)
    tokens = re.findall(r"[a-z]+|\d+", q)
    numbers = {int(t) for t in tokens if t.isdigit()}
    month_name = MONTHS[value.month - 1]
    has_month = value.month in numbers or any(
        t == month_name or (len(t) >= 3 and month_name.startswith(t)) for t in tokens if t.isalpha()
    ) or any(privacy.comparable(name) in q for name in HINDI_MONTH_NAMES[value.month - 1]) \
        or any(name in tokens for name in HINGLISH_MONTH_NAMES[value.month - 1])
    return value.year in numbers and value.day in numbers and has_month


def _field(raw: dict, name: str) -> (Optional[str], Optional[str]):
    item = raw.get(name) or {}
    if not isinstance(item, dict):
        return None, None
    value, quote = item.get("value"), item.get("quote")
    value = value.strip() if isinstance(value, str) and value.strip() else None
    quote = quote.strip() if isinstance(quote, str) and quote.strip() else None
    return value, quote


def check_ai_answer(raw: dict, notes: str) -> Reading:
    """Keep only answers whose exact words are in the notes and support the value."""
    r = Reading()

    def keep(fact, value, quote):
        r.values[fact] = value
        r.evidence[fact] = quote

    # Dates
    for fact, key in (("custody_began", "custody_began"), ("offence_date", "offence_date"),
                      ("today", "today_date")):
        value, quote = _field(raw, key)
        if value is None:
            if quote and _in_notes(quote, notes):
                r.notes_say[fact] = quote  # e.g. "in February 2024": shown, not used
            continue
        try:
            d = date.fromisoformat(value)
        except ValueError:
            r.dropped.append(f"{fact}: {value}")
            continue
        if _in_notes(quote, notes) and _date_supported(d, quote):
            keep(fact, d, quote)
        else:
            r.dropped.append(f"{fact}: {value}")
            if quote and _in_notes(quote, notes):
                r.notes_say[fact] = quote

    # Sections
    sections = []
    for item in raw.get("sections") or []:
        if not isinstance(item, dict):
            continue
        law = str(item.get("law", "")).strip().upper()
        section = str(item.get("section", "")).strip()
        quote = str(item.get("quote", "")).strip()
        cleaned = re.sub(r"\s+", "", privacy.normalise_digits(section)).casefold()
        if (law in ("IPC", "BNS") and section and _in_notes(quote, notes)
                and cleaned in re.sub(r"\s+", "", _norm(quote))
                and any(w in _norm(quote) for w in LAW_WORDS[law])):
            if (law, section) not in [(s[0], s[1]) for s in sections]:
                sections.append((law, section, quote))
        else:
            r.dropped.append(f"section: {law} {section}")
    if sections:
        law, section, quote = sections[0]
        keep("law", law, quote)
        keep("section", section, quote)
        keep("more_than_one_section", len(sections) > 1, "; ".join(s[2] for s in sections))
        if len(sections) > 1:
            r.values["all_sections"] = [f"{s[0]} {s[1]}" for s in sections]

    # Yes / no facts
    for fact, key, flip in (("never_convicted", "previously_convicted", True),
                            ("other_cases_pending", "other_cases_pending", False)):
        value, quote = _field(raw, key)
        if value is None:
            continue
        v = value.casefold()
        if v in ("yes", "no") and _in_notes(quote, notes):
            answer = v == "yes"
            keep(fact, (not answer) if flip else answer, quote)
        else:
            r.dropped.append(f"{key}: {value}")

    value, quote = _field(raw, "delay_by_accused")
    if value is not None:
        if value.casefold() == "no" and _in_notes(quote, notes):
            keep("delay_days_by_accused", 0, quote)
        elif value.casefold() == "yes" and _in_notes(quote, notes):
            r.notes_say["delay_days_by_accused"] = quote  # delay mentioned, but not how many days
        else:
            r.dropped.append(f"delay_by_accused: {value}")

    value, quote = _field(raw, "lawyer")
    if value is not None:
        if value in LAWYER_VALUES and _in_notes(quote, notes):
            keep("lawyer", value, quote)
        else:
            r.dropped.append(f"lawyer: {value}")

    return r


# ---------- what is still missing ----------

def offence_question(values: Dict[str, object]) -> Optional[str]:
    """The ask_to_decide question for the section found, when it matches exactly one row."""
    if not values.get("section"):
        return None
    rows = section479.find_offences(str(values.get("law", "IPC")), str(values["section"]))
    if len(rows) == 1 and rows[0].ask_to_decide:
        return rows[0].ask_to_decide
    return None


def missing_facts(values: Dict[str, object], skipped: Optional[set] = None) -> List[str]:
    """Facts still to ask for, in intake order. Skipped ones ("don't know") are not asked again."""
    skipped = skipped or set()
    missing = []
    for fact in question_order():
        if fact in skipped:
            continue
        if fact == "answer":
            if offence_question(values) and not values.get("answer"):
                missing.append(fact)
        elif values.get(fact) is None:
            missing.append(fact)
    return missing
