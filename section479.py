"""Section 479 BNSS calculator.

Plain code, no AI. Reads knowledge/sentence_table.csv and works out the
one-third (personal bond) and one-half (bail) dates from the date custody began.

The rules come from CLAUDE.md and knowledge/undertrial_bail.md:
- If death or life imprisonment is possible, Section 479 does not apply.
- One-half of the maximum term from the date custody began = bail date.
- One-third = personal bond date, only if the person was never convicted.
- More than one case pending: Section 479 release is not available.
- More than one section charged, or an ask_to_decide question not answered:
  the dates are shown as "to be checked by a lawyer".
- Delay caused by the accused does not count, so it pushes the dates later.
Release is never automatic: the jail superintendent must apply and the court decides.
"""

import calendar
import csv
import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Tuple

import lang

HERE = Path(__file__).resolve().parent
SENTENCE_TABLE = HERE / "knowledge" / "sentence_table.csv"
BAIL_KNOWLEDGE = HERE / "knowledge" / "undertrial_bail.md"

LAWYER_CHECK = "to be checked by a lawyer"
OLD_MAXIMUM_ENTRY = "Old offences use the old maximum"  # heading in knowledge/undertrial_bail.md
NOT_AUTOMATIC = (
    "Release is not automatic. The jail superintendent must apply to the court "
    "(the person or their lawyer can also apply), and the court decides."
)


@dataclass
class Offence:
    """One row of knowledge/sentence_table.csv."""

    offence: str
    bns_section: str
    ipc_section: str
    max_prison: str  # a number of months, or "life" or "death"
    death_or_life_possible: bool
    section_479_applies: str  # "yes", "no" or "check"
    ask_to_decide: str
    notes: str
    source_url: str
    ipc_max_prison: str = ""  # IPC maximum (months, "life" or "death"); blank for offences new in the BNS

    @property
    def max_months(self) -> Optional[int]:
        """The BNS maximum in months (None if life or death)."""
        return int(self.max_prison) if self.max_prison.isdigit() else None


BNS_START = date(2024, 7, 1)  # the BNS replaced the IPC for offences from this date


@dataclass
class Maximum:
    """Which maximum prison term was used, and why."""

    value: str  # months as digits, or "life" / "death"
    law: str  # "IPC" or "BNS"
    section: str  # for example "IPC 384"
    reason: str
    lawyer_check: bool = False
    reason_code: Tuple[str, dict] = ("", {})  # the reason's key in i18n/*.json, for other languages
    source: Optional[dict] = None  # Source / Link / Checked lines from knowledge/ backing the reason

    @property
    def source_line(self) -> str:
        if not self.source:
            return ""
        line = "Source: " + self.source["source"]
        if self.source.get("link"):
            line += f" ({self.source['link']})"
        return line

    @property
    def months(self) -> Optional[int]:
        return int(self.value) if self.value.isdigit() else None


def month_law_date(month: Optional[str]) -> Optional[date]:
    """'2024-05' (the notes give the month and year, not the day) -> a date in that month, used ONLY to
    decide IPC or BNS. The month and year always decide: every day of June 2024 is before 1 July 2024
    (IPC), every day of July 2024 is on or after it (BNS). None when no month is known."""
    try:
        year, month_no = (int(x) for x in (month or "").split("-"))
        first = date(year, month_no, 1)
    except ValueError:
        return None
    return first


def choose_maximum(offence: Offence, offence_date: Optional[date]) -> Maximum:
    """Before 1 July 2024 the IPC maximum applies; from 1 July 2024 the BNS maximum.

    Reasons that rely on that rule carry the Source line of the knowledge entry
    "Old offences use the old maximum" (knowledge/undertrial_bail.md).
    """
    old_max_source = knowledge_source(OLD_MAXIMUM_ENTRY)
    bns = Maximum(offence.max_prison, "BNS", f"BNS {offence.bns_section}", "")
    ipc_known = offence.ipc_max_prison != "" and offence.ipc_section != "new"

    if offence_date is None:
        if ipc_known and offence.ipc_max_prison == offence.max_prison:
            bns.reason, bns.reason_code = _text("s479.max.no_date_same")
            return bns
        bns.reason, bns.reason_code = _text("s479.max.no_date_differs")
        bns.lawyer_check = True
        bns.source = old_max_source
        return bns

    if offence_date >= BNS_START:
        bns.reason, bns.reason_code = _text("s479.max.after_july")
        bns.source = old_max_source
        return bns

    if not ipc_known:
        bns.reason, bns.reason_code = _text("s479.max.before_no_ipc")
        bns.lawyer_check = True
        bns.source = old_max_source
        return bns

    params = {}
    if offence.ipc_max_prison != offence.max_prison:
        params["bns_months"] = offence.max_prison
    reason = lang.t("s479.max.before_ipc") + (
        lang.t("s479.max.bns_higher", months=offence.max_prison) if params else "")
    return Maximum(offence.ipc_max_prison, "IPC", f"IPC {offence.ipc_section}", reason, reason_code=("s479.max.before_ipc", params),
                   source=old_max_source)


@dataclass
class MilestoneDate:
    name: str  # "One-third (personal bond)" or "One-half (bail)"
    months: Fraction
    when: Optional[date]  # None when this date does not apply
    reached: Optional[bool]
    note: str = ""
    key: str = ""        # "s479.third" or "s479.half"
    note_key: str = ""   # i18n key of the note, if any


class InputError(ValueError):
    """A problem with the facts entered; .key is its i18n key."""

    def __init__(self, key: str):
        super().__init__(lang.t(key))
        self.key = key


def _text(key: str, **params):
    """(English text, (key, params)) for a reason."""
    return lang.t(key, **params), (key, params)


@dataclass
class Result:
    offence: Offence
    maximum: Maximum
    applies: bool  # False = Section 479 release is not available
    lawyer_check: bool  # True = show dates as "to be checked by a lawyer"
    reasons: List[str] = field(default_factory=list)
    reason_codes: List[Tuple[str, dict]] = field(default_factory=list)  # same reasons, as i18n keys
    one_third: Optional[MilestoneDate] = None
    one_half: Optional[MilestoneDate] = None

    def say(self, key: str, **params) -> None:
        """Add a reason (English text, plus its key for other languages)."""
        self.reasons.append(lang.t(key, **params))
        self.reason_codes.append((key, params))


# ---------- reading the sentence table ----------

def load_offences(path: Path = SENTENCE_TABLE) -> List[Offence]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Offence(
                offence=row["offence"].strip(),
                bns_section=row["bns_section"].strip(),
                ipc_section=row["ipc_section"].strip(),
                max_prison=row["max_prison_months"].strip().lower(),
                death_or_life_possible=row["death_or_life_possible"].strip().lower() == "yes",
                section_479_applies=row["section_479_applies"].strip().lower(),
                ask_to_decide=row["ask_to_decide"].strip(),
                notes=row["notes"].strip(),
                source_url=row["source_url"].strip(),
                ipc_max_prison=(row.get("ipc_max_prison_months") or "").strip().lower(),
            )
            for row in csv.DictReader(f)
        ]


def _clean(section: str) -> str:
    """'IPC 380', ' 380 ', 'Sec. 380' -> '380'; lower case, no spaces."""
    s = section.strip().lower()
    s = re.sub(r"^(ipc|bns|section|sec\.?|s\.?)\s*", "", s)
    return re.sub(r"\s+", "", s)


def _base(section: str) -> str:
    """The section number without sub-section or part: '117(2)' -> '117', '506 (first part)' -> '506'."""
    return re.split(r"[\s(]", section.strip().lower(), maxsplit=1)[0]


def find_offences(law: str, section: str, offences: Optional[List[Offence]] = None) -> List[Offence]:
    """Find rows for an IPC or BNS section. May return several rows (the user then picks one).

    An exact match (for example BNS '117(2)') wins. Otherwise every row with the same
    section number is returned (for example BNS '117' gives 117(2) and 117(3)).
    """
    if offences is None:
        offences = load_offences()
    law = law.strip().upper()
    if law not in ("IPC", "BNS"):
        raise ValueError("law must be 'IPC' or 'BNS'")
    wanted = _clean(section)
    if not wanted:
        return []

    def column(o: Offence) -> str:
        return o.ipc_section if law == "IPC" else o.bns_section

    exact = [o for o in offences if _clean(column(o)) == wanted and column(o) != "new"]
    if exact:
        return exact
    return [o for o in offences if _base(column(o)) == _base(wanted) and column(o) != "new"]


# ---------- date arithmetic ----------

def add_months(start: date, months: int) -> date:
    """Calendar months: 15 March 2024 + 28 months = 15 July 2026.
    If the day doesn't exist (31 Jan + 1 month) use the last day of that month."""
    total = start.month - 1 + months
    year, month = start.year + total // 12, total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_fraction_of_months(start: date, months: Fraction) -> date:
    """Whole months on the calendar; any part month counted as 30 days, rounded up
    (so the date is never earlier than it should be)."""
    whole = math.floor(months)
    part = months - whole
    result = add_months(start, whole)
    if part:
        result += timedelta(days=math.ceil(part * 30))
    return result


# ---------- the calculator ----------

def calculate(
    offence: Offence,
    custody_began: date,
    today: date,
    never_convicted: bool,
    other_cases_pending: bool,
    more_than_one_section: bool,
    question_answered: bool = False,
    delay_days_by_accused: int = 0,
    offence_date: Optional[date] = None,
    offence_month: Optional[str] = None,
) -> Result:
    """Work out the Section 479 dates for one offence.

    offence_month: "2024-05" when the notes give the month and year but not the day; it decides IPC or
    BNS, as offence_date would.

    question_answered: True once the row's ask_to_decide question has been answered
    and this row is confirmed as the right one. Ignored for rows with no question.
    """
    if delay_days_by_accused < 0:
        raise InputError("s479.error.delay_negative")
    if custody_began > today:
        raise InputError("s479.error.custody_after_today")
    if offence_date is not None and offence_date > custody_began:
        raise InputError("s479.error.offence_after_custody")

    maximum = choose_maximum(offence, offence_date or month_law_date(offence_month))
    result = Result(offence=offence, maximum=maximum, applies=True, lawyer_check=False)

    # Rules that rule Section 479 out completely.
    if offence.death_or_life_possible or maximum.months is None:
        result.applies = False
        result.say("s479.reason.death_or_life")
    if offence.section_479_applies == "no" and not offence.death_or_life_possible:
        result.applies = False
        result.say("s479.reason.table_no")
    if other_cases_pending:
        result.applies = False
        result.say("s479.reason.other_cases")
    if not result.applies:
        return result

    # Rules that mean the dates must be checked by a lawyer.
    if more_than_one_section:
        result.lawyer_check = True
        result.say("s479.reason.many_sections")
    if offence.ask_to_decide and not question_answered:
        result.lawyer_check = True
        result.say("s479.reason.question", question=offence.ask_to_decide)
    if offence.section_479_applies == "check":
        result.lawyer_check = True
        result.say("s479.reason.table_check", notes=(": " + offence.notes) if offence.notes else "")

    if maximum.lawyer_check:
        result.lawyer_check = True
        result.reasons.append(maximum.reason)
        result.reason_codes.append(maximum.reason_code)

    max_months = Fraction(maximum.months)
    delay = timedelta(days=delay_days_by_accused)

    def milestone(key: str, share: Fraction) -> MilestoneDate:
        months = max_months * share
        when = add_fraction_of_months(custody_began, months) + delay
        note, note_key = "", ""
        if months.denominator != 1:
            result.lawyer_check = True
            note, note_key = lang.t("s479.note.part_month"), "s479.note.part_month"
        return MilestoneDate(name=lang.t(key), months=months, when=when, reached=today >= when, note=note,
                             key=key, note_key=note_key)

    if never_convicted:
        result.one_third = milestone("s479.third", Fraction(1, 3))
    else:
        result.one_third = MilestoneDate(
            name=lang.t("s479.third"), months=max_months / 3, when=None, reached=None,
            note=lang.t("s479.note.convicted"), key="s479.third", note_key="s479.note.convicted")
    result.one_half = milestone("s479.half", Fraction(1, 2))
    if delay_days_by_accused:
        result.say("s479.reason.delay", days=delay_days_by_accused)
    return result


def texts(result: Result, code: str) -> List[str]:
    """The result's reasons in a language."""
    return [lang.t(k, code, **p) if k else r for (k, p), r in zip(result.reason_codes, result.reasons)]


def maximum_reason(m: Maximum, code: str) -> str:
    key, params = m.reason_code
    if not key:
        return m.reason
    text = lang.t(key, code)
    if params.get("bns_months"):
        text += lang.t("s479.max.bns_higher", code, months=params["bns_months"])
    return text


# ---------- source lines from knowledge/ ----------

def knowledge_source(heading: str, path: Path = BAIL_KNOWLEDGE) -> dict:
    """Return the Source, Link and Checked lines under a '### heading' in a knowledge file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    found = {}
    inside = False
    for line in lines:
        if line.startswith("### "):
            if inside:
                break
            inside = line[4:].strip() == heading
            continue
        if inside:
            for key in ("Source", "Link", "Checked"):
                if line.startswith(key + ":"):
                    found[key.lower()] = line[len(key) + 1:].strip()
    if not found:
        raise KeyError(f"No entry '{heading}' with a Source line in {path.name}")
    return found


def format_months(months: Fraction) -> str:
    if months.denominator == 1:
        return f"{months.numerator} months"
    return f"{float(months):.1f} months"
