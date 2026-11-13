"""Evidence ledger: where every fact in a case came from. Plain code.

Every fact carries one of:
- "told by the person (entered by volunteer)"
- "read from notes by AI, checked by volunteer"
- "calculated by rule-based code"
- "from a verified source" (with the knowledge entry's Source line)
A legal point without a verified source is "unresolved: ask a lawyer", never shown as a fact.
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import knowledge
import section479

TOLD, AI_CHECKED, CALCULATED, VERIFIED, UNRESOLVED = "told", "ai_checked", "calculated", "verified", "unresolved"
PRECAUTION = "precaution"  # an unconfirmed AI "yes" used only to show a safety warning
RESEARCH, RESEARCH_APPROVED = "research", "research_approved"  # official-website research: waiting / approved


@dataclass
class Entry:
    fact: str            # an i18n key for the fact's name, e.g. "fact.custody_began"
    value: str
    source: str          # TOLD / AI_CHECKED / CALCULATED / VERIFIED / UNRESOLVED / PRECAUTION
    source_line: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _show(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "" if value is None else str(value)


def _origin(fact: str, final, ai_values: Dict[str, object], ai_checked: bool) -> str:
    """AI_CHECKED if the AI read this value from the notes and the volunteer kept it after checking."""
    if ai_checked and fact in ai_values and _show(ai_values[fact]) == _show(final):
        return AI_CHECKED
    return TOLD


# ---------- Section 479 cases ----------

UNDERTRIAL_FACTS = [("custody_began", "custody_began"), ("offence_date", "offence_date"), ("law", "law_typed"),
                    ("section", "section_typed"), ("never_convicted", "never_convicted"),
                    ("other_cases_pending", "other_cases_pending"), ("more_than_one_section", "more_than_one_section"),
                    ("delay_days_by_accused", "delay_days_by_accused"), ("lawyer", "lawyer"), ("answer", "answer")]


def undertrial(facts, result: section479.Result, ai_values: Optional[Dict[str, object]] = None,
               ai_checked: bool = False) -> List[Entry]:
    ai_values = ai_values or {}
    d = facts.to_dict()
    entries = []
    for fact, field in UNDERTRIAL_FACTS:
        if field == "answer" and not result.offence.ask_to_decide:
            continue
        entries.append(Entry(f"fact.{fact}", _show(d.get(field)), _origin(fact, getattr(facts, field), ai_values, ai_checked)))

    o, m = result.offence, result.maximum
    entries.append(Entry("ledger.offence", f"{o.offence} (BNS {o.bns_section} / IPC {o.ipc_section})", VERIFIED,
                         f"Source: knowledge/sentence_table.csv ({o.source_url})"))
    entries.append(Entry("ledger.maximum", f"{m.value} months, as per {m.section}", VERIFIED,
                         m.source_line or f"Source: knowledge/sentence_table.csv ({o.source_url})"))
    rule = knowledge.get("undertrial_bail.md", "Section 479: release after a share of the maximum sentence")
    for ms in (result.one_third, result.one_half):
        if ms and ms.when:
            entries.append(Entry(ms.key or "ledger.milestone", ms.when.isoformat(), CALCULATED, rule.source_line))
    entries.append(Entry("ledger.release_not_automatic", "the jail superintendent applies; the court decides",
                         VERIFIED, knowledge.get("undertrial_bail.md", "Who applies under Section 479").source_line))
    if facts.more_than_one_section:
        entries.append(Entry("ledger.section479_2", "may bar release when more than one section is charged",
                             UNRESOLVED))
    if o.ask_to_decide and not (facts.answer.strip() and facts.question_answered):
        entries.append(Entry("ledger.deciding_question", o.ask_to_decide, UNRESOLVED))
    if result.lawyer_check and not facts.more_than_one_section and not o.ask_to_decide:
        entries.append(Entry("ledger.dates_to_check", "to be checked by a lawyer", UNRESOLVED))
    return entries


# ---------- Any-case summaries ----------

GENERAL_FACTS = ["danger_now", "in_custody", "money_lost_online", "money_lost_in_last_few_days", "called_1930",
                 "woman", "under_18", "sc_st", "disability", "state", "annual_income"]


def general(g, reading_facts: Dict[str, object], eligibility, ai_checked: bool = True) -> List[Entry]:
    """g: general.GeneralFacts; reading_facts: what the AI read and plain code accepted."""
    import general as gen  # local import: general imports nothing from here
    entries = []
    for fact in GENERAL_FACTS:
        if fact in g.facts:
            entries.append(Entry(f"ledger.f.{fact}", _show(g.facts[fact]),
                                 _origin(fact, g.facts[fact], reading_facts, ai_checked)))
    for fact in g.precautions:
        entries.append(Entry(f"ledger.f.{fact}", "yes (not confirmed by the notes' own words)", PRECAUTION))
    quote = (g.evidence or {}).get("outcome", "")
    if g.outcome or quote:  # the plain-words version, and the notes' exact words (only here)
        entries.append(Entry("ledger.outcome", g.outcome or "-", TOLD if not quote else AI_CHECKED,
                             f"“{quote}”" if quote else ""))
    for question, answer in g.answers:
        entries.append(Entry("ledger.answer", f"{question} — {answer}", TOLD))
    for action in gen.urgent_actions(g.facts, g.precautions):
        entries.append(Entry("ledger.urgent", action, CALCULATED, "Rule: CLAUDE.md safety rules"))
    entries.append(Entry("ledger.legal_aid", eligibility.reason, CALCULATED, "; ".join(eligibility.sources)))
    for category, name in g.issues:
        sources = [e.source_line for e in gen.issue_guidance(category)]
        if sources:
            entries.append(Entry("ledger.issue", name, VERIFIED, " | ".join(sources)))
        elif gen.research_for(g, name):  # the supervisor approved research points for it
            entries.append(Entry("ledger.issue", name, RESEARCH_APPROVED))
        elif g.research_state == "waiting" and getattr(g, "research_pending", 0):
            entries.append(Entry("ledger.issue", name, RESEARCH))
        else:
            entries.append(Entry("ledger.issue", name, UNRESOLVED))
    return entries


def unresolved(entries: List[Entry]) -> List[Entry]:
    return [e for e in entries if e.source == UNRESOLVED]
