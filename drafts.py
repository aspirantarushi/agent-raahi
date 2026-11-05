"""Fill draft templates and build case files. Plain code, no AI.

Rules (CLAUDE.md):
- Copy the template exactly and replace only [square-bracket] blanks we know.
  Every other blank stays visible.
- Every draft starts with "DRAFT — to be checked by a lawyer".
- Name, phone, Aadhaar and address blanks stay empty for the person to fill by hand.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import lang
import privacy
import section479
from section479 import Result, add_months

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
TEMPLATES_HI = HERE / "templates_hi"
DRAFT_HEADER = "DRAFT — to be checked by a lawyer"

LAWYER_OPTIONS = ["Legal aid lawyer", "Private lawyer", "None", "Don't know"]


@dataclass
class UndertrialFacts:
    """Facts entered on the New case screen. No names or personal details."""

    law_typed: str  # "IPC" or "BNS"
    section_typed: str
    custody_began: date
    today: date
    never_convicted: bool
    other_cases_pending: bool
    more_than_one_section: bool
    question_answered: bool
    delay_days_by_accused: int
    lawyer: str  # one of LAWYER_OPTIONS
    offence_name: str = ""  # the sentence-table row picked, when a section has several
    offence_date: Optional[date] = None
    answer: str = ""  # answer to the row's ask_to_decide question, if any

    def __post_init__(self):
        # The question counts as answered only when an answer is written down.
        if not self.answer.strip():
            self.question_answered = False

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["custody_began"] = self.custody_began.isoformat()
        d["today"] = self.today.isoformat()
        d["offence_date"] = self.offence_date.isoformat() if self.offence_date else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "UndertrialFacts":
        d = dict(d)
        d["custody_began"] = date.fromisoformat(d["custody_began"])
        d["today"] = date.fromisoformat(d["today"])
        if d.get("offence_date"):
            d["offence_date"] = date.fromisoformat(d["offence_date"])
        return cls(**d)


# ---------- small helpers ----------

def show_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def describe_term(months: int) -> str:
    if months % 12 == 0:
        years = months // 12
        return f"{years} year{'s' if years != 1 else ''} ({months} months)"
    return f"{months} month{'s' if months != 1 else ''}"


def time_in_custody(start: date, today: date) -> Tuple[int, int]:
    """Whole calendar months and leftover days from start to today."""
    months = (today.year - start.year) * 12 + (today.month - start.month)
    while months > 0 and add_months(start, months) > today:
        months -= 1
    days = (today - add_months(start, months)).days
    return months, days


def fill(template: str, replacements: List[Tuple[str, str]]) -> str:
    """Replace each exact piece of template text once.

    Each 'old' piece must appear exactly once, so a change to the template is caught
    instead of silently filling the wrong blank. Everything else is copied exactly.
    """
    text = template
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise ValueError(f"Template text {old!r} found {count} times (expected once).")
        text = text.replace(old, new)
    return text


def remaining_blanks(text: str) -> List[str]:
    """The [square-bracket] blanks still visible in a draft, outermost only."""
    blanks, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                blanks.append(text[start:i + 1])
    return blanks


BNS_START = date(2024, 7, 1)  # the BNS replaced the IPC for offences from this date


def describe_sections(offence: section479.Offence, offence_date: Optional[date]) -> str:
    """Before 1 July 2024: 'IPC 325 (now BNS 117(2))'. From 1 July 2024: 'BNS 117(2) (earlier IPC 325)'."""
    bns, ipc = offence.bns_section, offence.ipc_section
    if offence_date is None:
        return f"BNS {bns} / IPC {ipc} [offence date not given: which law applies?]"
    if ipc == "new":  # an offence that did not exist as such in the IPC
        if offence_date < BNS_START:
            return f"IPC [___] (now BNS {bns}, a new offence in the BNS)"
        return f"BNS {bns} (new offence, no single IPC equivalent)"
    if offence_date < BNS_START:
        return f"IPC {ipc} (now BNS {bns})"
    return f"BNS {bns} (earlier IPC {ipc})"


def question_line(facts: "UndertrialFacts", offence: section479.Offence) -> str:
    """Case-details line for the row's ask_to_decide question, or '' if it has none."""
    if not offence.ask_to_decide:
        return ""
    answer = facts.answer.strip()
    if not answer:
        answer = "not answered — to be checked by a lawyer"
    elif not facts.question_answered:
        answer += " (not confirmed as the right offence — to be checked by a lawyer)"
    return f"- Question that decides the maximum term: {offence.ask_to_decide} Answer: {answer}"


def _status(m) -> str:
    return "reached" if m.reached else "not yet reached"


# ---------- Section 479 note ----------

def section479_replacements(facts: UndertrialFacts, result: Result) -> List[Tuple[str, str]]:
    o = result.offence
    m = result.maximum
    check = " (to be checked by a lawyer)" if result.lawyer_check else ""

    sections = describe_sections(o, facts.offence_date)
    if facts.more_than_one_section:
        sections += ", and other sections [___]"

    months, days = time_in_custody(facts.custody_began, facts.today)

    if result.one_third and result.one_third.when:
        third = f"{show_date(result.one_third.when)} — {_status(result.one_third)}{check}"
    else:
        third = "not applicable (previous conviction)"
    half = f"{show_date(result.one_half.when)} — {_status(result.one_half)}{check}"

    return [
        ("- Sections charged: [BNS ___ / IPC ___]", f"- Sections charged: {sections}"),
        ("- Maximum punishment for the offence: [___ years] (as per [section])",
         f"- Maximum punishment for the offence: {describe_term(m.months)} (as per {m.section})\n"
         f"- Why this maximum: {m.reason}"
         + (f"\n  {m.source_line}" if m.source_line else "")),
        ("- Date custody began: [date]", f"- Date custody began: {show_date(facts.custody_began)}"),
        ("- Period in custody as on today: [___ months ___ days]",
         f"- Period in custody as on today: {months} months {days} days (as on {show_date(facts.today)})"),
        ("- Previous convictions: [none known / ___]",
         "- Previous convictions: " + ("none known" if facts.never_convicted else "yes, details [___]")),
        ("- Other cases pending: [none known / ___]",
         "- Other cases pending: " + ("yes, details [___]" if facts.other_cases_pending else "none known")
         + ("\n" + question_line(facts, o) if o.ask_to_decide else "")),
        ("- One-half of the maximum term: [date] [reached / not yet reached]",
         f"- One-half of the maximum term: {half}"),
        ("- One-third of the maximum term (first-time offender only): [date] [reached / not yet reached]",
         f"- One-third of the maximum term (first-time offender only): {third}"),
    ]


# ---------- DLSA application (added when the person has no lawyer) ----------

def dlsa_replacements(facts: UndertrialFacts, result: Result) -> List[Tuple[str, str]]:
    o = result.offence
    statement = (
        f"   The applicant is an undertrial prisoner, in custody since {show_date(facts.custody_began)}, "
        f"charged under {describe_sections(o, facts.offence_date)} ({o.offence.lower()}). "
        "The applicant has no lawyer and needs one to apply for release under Section 479 BNSS. "
        "Court and case or FIR number: [court, case / FIR number]."
    )
    return [
        ("[Yes — specify: woman / child / SC / ST / person with disability / person in custody / "
         "industrial workman / victim of trafficking or disaster] [No]",
         "Yes — person in custody"),
        ("[e.g. a lawyer to apply for release under Section 479 BNSS / a lawyer to apply for release "
         "of frozen money / legal advice]",
         "a lawyer to apply for release under Section 479 BNSS"),
        ("   [Two to five sentences: what happened, when, which court or police station, case or FIR "
         "number, what the applicant needs now.]",
         statement),
    ]


# ---------- AI disclosure (draft SC "Regulations for Use of AI in Courts, 2026", Reg. 43(3), 43(6)) ----------

DISCLOSURE_START = "How this draft was prepared:"
RULES_DATES = "dates were calculated by rule-based code from the statute"
APPROVAL_BLANK = "approved by the supervisor on [date]."


RULE_KEYS = {RULES_DATES: "disclosure.rules_dates",
             "free legal aid eligibility was checked by rule-based code from our verified files":
                 "disclosure.rules_eligibility"}
DISCLOSURE_STARTS = [DISCLOSURE_START, "\u092f\u0939 \u0921\u094d\u0930\u093e\u092b\u093c\u094d\u091f \u0915\u0948\u0938\u0947 \u092c\u0928\u093e:"]


def disclosure_block(ai_model: Optional[str], approved_on: Optional[date] = None,
                     rules: str = RULES_DATES, code: str = "en") -> str:
    """The block added at the end of every draft. Names the AI model only if AI was used."""
    if code != "en":
        how = (lang.t("disclosure.ai", code, model=ai_model) if ai_model else lang.t("disclosure.no_ai", code))
        approved = lang.show_date(approved_on, code) if approved_on else lang.t("disclosure.date_blank", code)
        block = (f"{lang.t('disclosure.start', code)} {how}; {lang.t(RULE_KEYS.get(rules, 'disclosure.rules_dates'), code)}; "
                 f"{lang.t('disclosure.approved', code, date=approved)}")
        return block + (" " + lang.t("disclosure.court", code) if ai_model else "")
    if ai_model:
        how = f"facts were read from case notes with AI assistance ({ai_model}) and checked by a volunteer"
    else:
        how = "facts were entered by a volunteer"
    approved = show_date(approved_on) if approved_on else "[date]"
    block = (f"{DISCLOSURE_START} {how}; {rules}; "
             f"the draft was reviewed and approved by the supervisor on {approved}.")
    if ai_model:
        block += " If this is filed in any court, AI assistance must be declared as the court requires."
    return block


def add_disclosure(text: str, ai_model: Optional[str], approved_on: Optional[date] = None,
                   rules: str = RULES_DATES, code: str = "en") -> str:
    return (text.rstrip("\n") + "\n\n---\n\n" + lang.t("disclosure.prepared_with", code) + "\n"
            + disclosure_block(ai_model, approved_on, rules, code) + "\n")


def fill_approval_date(text: str, approved_on: date, ai_model: Optional[str], rules: str = RULES_DATES,
                       code: str = "en") -> str:
    """At approval: fill the date in the disclosure block, or add the block if it was removed."""
    blanks = [(APPROVAL_BLANK, f"approved by the supervisor on {show_date(approved_on)}.")]
    hi_blank = lang.t("disclosure.approved", "hi", date=lang.t("disclosure.date_blank", "hi"))
    blanks.append((hi_blank, lang.t("disclosure.approved", "hi", date=lang.show_date(approved_on, "hi"))))
    if any(blank in text for blank, _ in blanks):  # every draft in a packet gets the approval date
        for blank, filled in blanks:
            text = text.replace(blank, filled)
        return text
    if not any(start in text for start in DISCLOSURE_STARTS):
        return add_disclosure(text, ai_model, approved_on, rules, code)
    return text


# ---------- Hindi drafts (templates_hi/) ----------

def _hi_template(name: str) -> Tuple[str, bool]:
    """A Hindi template without its marker line, and whether its translation was checked."""
    lines = (TEMPLATES_HI / name).read_text(encoding="utf-8").splitlines()
    checked = lines[0].strip().lower() == "<!-- hindi translation checked: yes -->"
    return "\n".join(lines[1:]) + "\n", checked


def _hi_line(template: str, prefix: str) -> str:
    """The one template line that starts with this prefix (the line holds the blank to fill)."""
    found = [l for l in template.splitlines() if l.startswith(prefix)]
    if len(found) != 1:
        raise ValueError(f"Hindi template line starting {prefix!r} found {len(found)} times (expected once).")
    return found[0]


def describe_term_in(months: int, code: str) -> str:
    if code == "en":
        return describe_term(months)
    if months % 12 == 0:
        years = months // 12
        return lang.t("draft.term_years" if years != 1 else "draft.term_year", code, years=years, months=months)
    return lang.t("draft.term_months" if months != 1 else "draft.term_month", code, months=months)


def describe_sections_in(offence: section479.Offence, offence_date: Optional[date], code: str) -> str:
    if code == "en":
        return describe_sections(offence, offence_date)
    bns, ipc = offence.bns_section, offence.ipc_section
    if offence_date is None:
        key = "sec.no_date"
    elif ipc == "new":
        key = "sec.new_before" if offence_date < BNS_START else "sec.new_after"
    else:
        key = "sec.before" if offence_date < BNS_START else "sec.after"
    return lang.t(key, code, bns=bns, ipc=ipc)


def hindi_note(facts: "UndertrialFacts", result: Result) -> Tuple[str, bool]:
    code = "hi"
    template, checked = _hi_template("section479_note.md")
    o, m = result.offence, result.maximum
    t = lambda key, **p: lang.t(key, code, **p)
    check = t("draft.check_suffix") if result.lawyer_check else ""
    status = lambda ms: t("draft.reached") if ms.reached else t("draft.not_reached")
    sections = describe_sections_in(o, facts.offence_date, code)
    if facts.more_than_one_section:
        sections += t("draft.other_sections")
    months, days = time_in_custody(facts.custody_began, facts.today)
    if result.one_third and result.one_third.when:
        third = f"{lang.show_date(result.one_third.when, code)} \u2014 {status(result.one_third)}{check}"
    else:
        third = t("draft.not_applicable_convicted")
    half = f"{lang.show_date(result.one_half.when, code)} \u2014 {status(result.one_half)}{check}"
    question = ""
    if o.ask_to_decide:
        answer = facts.answer.strip()
        if not answer:
            answer = t("draft.not_answered")
        elif not facts.question_answered:
            answer += t("draft.not_confirmed")
        question = "\n" + t("draft.question_line", question=o.ask_to_decide, answer=answer)

    def line(label_key: str) -> Tuple[str, str]:
        full = _hi_line(template, t(label_key))
        return full, t(label_key)

    pairs = []
    for key, value in [
        ("draft.line.sections", sections),
        ("draft.line.maximum", t("draft.max_value", term=describe_term_in(m.months, code), section=m.section)
         + "\n" + t("draft.why_max", reason=section479.maximum_reason(m, code))
         + (f"\n  {m.source_line}" if m.source_line else "")),
        ("draft.line.custody", lang.show_date(facts.custody_began, code)),
        ("draft.line.period", t("draft.period", months=months, days=days, date=lang.show_date(facts.today, code))),
        ("draft.line.convictions", t("draft.none_known") if facts.never_convicted else t("draft.yes_details")),
        ("draft.line.other_cases", (t("draft.yes_details") if facts.other_cases_pending else t("draft.none_known"))
         + question),
        ("draft.line.half", half),
        ("draft.line.third", third),
    ]:
        full, prefix = line(key)
        pairs.append((full, prefix + value))
    return fill(template, pairs), checked


def hindi_dlsa(facts: "UndertrialFacts", result: Result) -> Tuple[str, bool]:
    code = "hi"
    template, checked = _hi_template("dlsa_application.md")
    t = lambda key, **p: lang.t(key, code, **p)
    o = result.offence
    statement = t("draft.dlsa_statement", date=lang.show_date(facts.custody_began, code),
                  sections=describe_sections_in(o, facts.offence_date, code), offence=o.offence.lower())
    return fill(template, [(t("draft.dlsa_groups_blank"), t("draft.dlsa_custody")),
                           (t("draft.dlsa_need_blank"), t("draft.dlsa_need")),
                           (t("draft.dlsa_statement_blank"), statement)]), checked


def translation_label(checked: bool) -> str:
    return lang.t("draft.translation_label", "hi", status=lang.t("yes" if checked else "no", "hi"),
                  status_en="yes" if checked else "no")


def make_undertrial_draft(facts: UndertrialFacts, result: Result, templates: Path = TEMPLATES,
                          ai_model: Optional[str] = None, code: str = "en") -> str:
    """ai_model: the AI model that read the case notes, or None if the facts were typed in.
    code: the draft's language ("en" or "hi"). A Hindi draft keeps the English DRAFT line first."""
    if code == "hi":
        if not result.applies:
            raise ValueError("Section 479 does not apply, so there is no Section 479 note to draft.")
        note, checked = hindi_note(facts, result)
        if facts.lawyer == "None":
            dlsa, dlsa_checked = hindi_dlsa(facts, result)
            note = note.rstrip("\n") + "\n\n---\n\n" + dlsa
            checked = checked and dlsa_checked
        first, second, rest = note.split("\n", 2)
        note = f"{first}\n{second}\n{translation_label(checked)}\n{rest}"
        return add_disclosure(note, ai_model, code="hi")
    if not result.applies:
        raise ValueError("Section 479 does not apply, so there is no Section 479 note to draft.")
    note = fill((templates / "section479_note.md").read_text(encoding="utf-8"),
                section479_replacements(facts, result))
    if facts.lawyer == "None":
        dlsa = fill((templates / "dlsa_application.md").read_text(encoding="utf-8"),
                    dlsa_replacements(facts, result))
        note = note.rstrip("\n") + "\n\n---\n\n" + dlsa
    if not note.startswith(DRAFT_HEADER):  # safety net; both templates already start with it
        note = DRAFT_HEADER + "\n\n" + note
    return add_disclosure(note, ai_model)


# ---------- case file ----------

def next_steps(facts: UndertrialFacts, result: Result) -> List[str]:
    steps = []
    if facts.lawyer == "None":
        steps.append("Help the person submit the DLSA application for a free legal aid lawyer. "
                     "A person in custody qualifies whatever their income.")
    elif facts.lawyer == "Don't know":
        steps.append("Find out whether the person has a lawyer (ask the family or the jail legal aid clinic).")
    else:
        steps.append(f"Share the Section 479 note with the person's lawyer ({facts.lawyer.lower()}).")

    reached = [m for m in (result.one_third, result.one_half) if m and m.when and m.reached]
    if reached:
        steps.append("Send the Section 479 note to the DLSA or jail legal aid clinic, and ask whether "
                     "the jail superintendent has applied to the court under Section 479(3).")
    upcoming = [m for m in (result.one_third, result.one_half) if m and m.when and not m.reached]
    for m in upcoming:
        steps.append(f"{m.name} date is {show_date(m.when)}: follow up as it gets close.")
    if result.lawyer_check:
        steps.append("Ask a lawyer to check the dates before anyone relies on them.")
    steps.append("Fill the remaining blanks in the draft (court, CNR, FIR, jail, organisation).")
    steps.append(section479.NOT_AUTOMATIC)
    return steps


def facts_missing(facts: UndertrialFacts, result: Result) -> List[str]:
    missing = [
        "Court and case number (CNR)",
        "FIR number and police station",
        "Jail and district",
        "Documents available (FIR copy, custody warrant, last court order)",
    ]
    if facts.more_than_one_section:
        missing.append("The other sections charged, and whether Section 479(2) bars release")
    if result.offence.ask_to_decide and not facts.question_answered:
        missing.append(f"Answer to: {result.offence.ask_to_decide}")
    if facts.offence_date is None:
        missing.append("Offence date (decides whether the IPC or the BNS applies)")
    if facts.lawyer == "Don't know":
        missing.append("Whether the person has a lawyer")
    return missing


def make_case_file(case_id: str, facts: UndertrialFacts, result: Result, approved_on: date) -> str:
    o = result.offence
    follow_up = approved_on + timedelta(days=7)
    lines = [
        f"# Case {case_id}",
        "",
        f"- Date: {show_date(approved_on)}",
        "- Case type: Undertrial (Section 479 BNSS)",
        "- Status: approved by supervisor",
        f"- Follow-up date: {show_date(follow_up)}",
        "",
        "## Facts known",
        f"- Offence: {o.offence}",
        f"- Sections: {describe_sections(o, facts.offence_date)}",
        "- Offence date: " + (show_date(facts.offence_date) if facts.offence_date else "not given"),
        f"- Maximum prison term: {describe_term(result.maximum.months)}, as per {result.maximum.section}",
        f"- Why this maximum: {result.maximum.reason}",
    ] + ([f"  {result.maximum.source_line}"] if result.maximum.source_line else []) + [
        f"- Date custody began: {show_date(facts.custody_began)}",
        f"- Dates worked out as on: {show_date(facts.today)}",
        f"- Never convicted: {'yes' if facts.never_convicted else 'no'}",
        f"- Other cases pending: {'yes' if facts.other_cases_pending else 'no'}",
        f"- More than one section charged: {'yes' if facts.more_than_one_section else 'no'}",
        f"- Delay caused by the accused: {facts.delay_days_by_accused} days",
        f"- Lawyer: {facts.lawyer}",
    ]
    if o.ask_to_decide:
        lines.append(question_line(facts, o))
    for m in (result.one_third, result.one_half):
        if m.when:
            lines.append(f"- {m.name}: {show_date(m.when)} — {_status(m)}")
        else:
            lines.append(f"- {m.name}: not available. {m.note}")
    if result.lawyer_check:
        lines.append("- These dates are to be checked by a lawyer.")
    lines += ["", "## Facts missing"] + [f"- {x}" for x in facts_missing(facts, result)]
    lines += ["", "## Next steps"] + [f"{i}. {s}" for i, s in enumerate(next_steps(facts, result), 1)]
    lines += ["", "No names or personal details are stored in this file."]
    return "\n".join(lines) + "\n"


# ---------- checks before saving ----------

def personal_details_found(text: str) -> List[str]:
    """Simple check for phone numbers, Aadhaar numbers or emails typed into a draft.
    Names can't be detected reliably, so the supervisor is also reminded not to add them."""
    return privacy.personal_details_found(text)


def recalculate(facts: UndertrialFacts) -> Result:
    """Rebuild the Section 479 result from saved facts (used when a draft is approved)."""
    matches = section479.find_offences(facts.law_typed, facts.section_typed)
    if facts.offence_name:
        matches = [o for o in matches if o.offence == facts.offence_name]
    if len(matches) != 1:
        raise ValueError("Could not find exactly one matching offence in the sentence table.")
    return section479.calculate(
        matches[0],
        custody_began=facts.custody_began,
        today=facts.today,
        never_convicted=facts.never_convicted,
        other_cases_pending=facts.other_cases_pending,
        more_than_one_section=facts.more_than_one_section,
        question_answered=facts.question_answered,
        delay_days_by_accused=facts.delay_days_by_accused,
        offence_date=facts.offence_date,
    )
