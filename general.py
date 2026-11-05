"""General intake: a structured summary for ANY kind of case. Plain code, no AI.

The AI (llm.read_general_notes) only describes the story. This file:
- keeps only yes/no, state and income answers whose exact words are in the notes,
- removes any law, Act or section reference from the AI's text (legal points come only
  from knowledge/),
- shows "Call 112 now" / "Call 1930 now" by the rules in CLAUDE.md,
- matches each issue to a knowledge entry (with its Source line), or says it is not covered,
- lists documents, checks free legal aid eligibility, and writes next steps,
- builds the summary draft and the case file.
Never predicts outcomes or chances (see "What this tool will never do").
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import drafts
import intake
import knowledge
import lang
import privacy
import section479

HERE = Path(__file__).resolve().parent
INCOME_LIMITS = HERE / "knowledge" / "income_limits.csv"

CASE_TYPE = "General"
CASE_TYPE_LABEL = "Any case (general intake)"
NOT_COVERED = "not covered by our verified files yet; ask NALSA's free helpline 15100"
TO_DISCUSS = "to discuss with a lawyer"
CALL_112 = "Call 112 now."
CALL_1930 = "Call 1930 now."
RULES_USED = "free legal aid eligibility was checked by rule-based code from our verified files"
OFTEN_HELP = "Documents that often help (a lawyer will confirm)"
# For problems our files don't cover: a plain list by type of problem, no law named.
PROBLEM_DOCUMENTS = [
    ("money or wages", ["wage", "salary", "salaries", "pay", "paid", "employer", "contractor", "job", "worker",
                        "work", "loan", "money", "dues", "pension"],
     ["Appointment letter or ID card", "Pay slips", "Bank statements", "Attendance records",
      "Messages with the employer"]),
    ("family or home", ["husband", "wife", "marriage", "married", "divorce", "maintenance", "dowry", "domestic",
                        "in-laws", "children", "child", "family"],
     ["Marriage proof", "Children's birth certificates", "Any medical records", "Messages",
      "Notices received"]),
    ("land or house", ["land", "house", "property", "plot", "rent", "tenant", "landlord", "evict", "eviction",
                       "neighbour", "boundary"],
     ["Ownership or rent papers", "Tax receipts", "Notices received"]),
]
POLICE_OR_COURT_WORDS = ["police", "fir", "arrest", "arrested", "court", "hearing", "chargesheet", "jail", "summons"]
POLICE_OR_COURT_DOCUMENTS = ["FIR copy", "Court orders", "Notices received"]
ALWAYS_DOCUMENTS = ["ID proof", "Income proof (for free legal aid)"]
YES_NO_FACTS = ["danger_now", "in_custody", "money_lost_online", "money_lost_in_last_few_days", "called_1930",
                "woman", "under_18", "sc_st", "disability", "essential_service_cut", "unofficial_payment_demand"]
ISSUE_CATEGORIES = {"arrest_or_custody", "online_or_financial_fraud", "electricity_or_water", "wages_or_work",
                    "ration_or_welfare", "other"}
GENERIC_PERSON = {"the person seeking help", "person seeking help", "the person", "unknown", "not stated",
                  "the person needing help", "व्यक्ति", "मदद चाहने वाला व्यक्ति"}

# Which knowledge entries cover which kind of issue.
ISSUE_KNOWLEDGE = {
    "arrest_or_custody": [
        ("undertrial_bail.md", "Rights on arrest"),
        ("undertrial_bail.md", "Free legal aid starts at the first court appearance"),
        ("undertrial_bail.md", "Who to approach for an undertrial"),
    ],
    "online_or_financial_fraud": [
        ("cyber_fraud.md", "Call 1930 at once: the first hours matter most"),
        ("cyber_fraud.md", "Stop further loss straight away"),
        ("cyber_fraud.md", "Evidence to keep"),
    ],
}
# Documents to collect, from the knowledge entry that covers the issue.
ISSUE_DOCUMENTS = {
    "arrest_or_custody": ("legal_aid_eligibility.md", "What to carry"),
    "online_or_financial_fraud": ("cyber_fraud.md", "Evidence to keep"),
}

# ---------- removing law references the AI was told not to write ----------

_ACTS = r"IPC|I\.P\.C\.?|BNS|BNSS|BSA|CrPC|Cr\.?P\.?C\.?|CPC|C\.P\.C\.?|IEA|POCSO|PWDV|NDPS|DV Act|IT Act|SC/ST Act"
LEGAL_REF = re.compile(
    r"(?i)\b(?:under\s+)?(?:sections?|secs?\.?|u/s\.?|s\.|articles?|art\.|rules?|regulations?|clauses?)"
    r"\s*\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*(?:\s*(?:,|and|/|&)\s*\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*)*"
    rf"(?:\s*(?:of|,)?\s*(?:the\s+)?(?:{_ACTS}))?"
    rf"|\b\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*\s*(?:{_ACTS})\b"
    rf"|\b(?:{_ACTS})\b(?:\s*(?:section|sec\.?|s\.)?\s*\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*)?"
    r"|\b(?:[A-Z][\w'’-]*\s+){1,7}Act\b(?:,?\s*\d{4})?"
    r"|\b(?:Act|Code|Sanhita)\s*,?\s*(?:of\s+)?\d{4}\b"
    r"|\b(?:the\s+)?Code\s+(?:on|of)\s+(?:[A-Z][\w'’-]*\s*)+(?:,?\s*\d{4})?"
    # Hindi and Hinglish: "धारा 498A", "अनुच्छेद 21", "dhara 420", "... अधिनियम, 1936", "... संहिता"
    r"|(?:धारा|धाराओं|अनुच्छेद|नियम|विनियम|dhara|dafa|दफ़ा|दफा)\s*\d+[A-Za-z]?(?:\s*\(\s*\w+\s*\))*"
    r"|(?:[\u0900-\u097F]+\s+){0,6}(?:अधिनियम|संहिता|क़ानून\s+\d{4})(?:,?\s*\d{4})?"
    r"|\b(?:[A-Z][\w'’-]*\s+){1,6}(?:Code|Sanhita)\b,?\s*\d{4}"
)
REMOVED = "[law reference removed: ask a lawyer]"


def remove_legal_refs(text: str) -> str:
    return LEGAL_REF.sub(REMOVED, text)


def legal_refs(text: str) -> List[str]:
    """Law or section references in a text (used by the tests and the safety check)."""
    return [m.group(0) for m in LEGAL_REF.finditer(text)]


def clean(text, limit: int = 300) -> str:
    """Make AI text safe to show and save: personal numbers and law references removed."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", text).strip()[:limit]
    return remove_legal_refs(privacy.redact(text)[0])


# ---------- checking the AI's answer ----------

@dataclass
class GeneralReading:
    person: str = "the person seeking help"
    what_happened: List[str] = field(default_factory=list)
    timeline: List[Tuple[str, str]] = field(default_factory=list)
    coming_dates: List[Tuple[str, str]] = field(default_factory=list)
    facts: Dict[str, object] = field(default_factory=dict)       # yes/no facts, state, annual_income
    evidence: Dict[str, str] = field(default_factory=dict)
    sections: List[section479.Offence] = field(default_factory=list)  # from the sentence table only
    sections_as_written: List[str] = field(default_factory=list)
    issues: List[Tuple[str, str]] = field(default_factory=list)  # (category, plain-words name)
    documents_held: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    outcome: str = ""                                            # what the person wants, from the notes
    dropped: List[str] = field(default_factory=list)
    unconfirmed_yes: List[str] = field(default_factory=list)  # "yes" answers whose words weren't found


def _quoted(item, notes: str) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(item, dict):
        return None, None
    value, quote = item.get("value"), item.get("quote")
    if isinstance(quote, str) and intake._in_notes(quote, notes):
        return value, quote
    return value, None


_MULTIPLIERS = {"हज़ार": 1000, "हजार": 1000, "hazar": 1000, "hazaar": 1000, "hajar": 1000, "thousand": 1000,
                "k": 1000, "लाख": 100000, "lakh": 100000, "lac": 100000, "lakhs": 100000}


def _digits_in(quote: str) -> List[int]:
    """Amounts written in the quote: "10,000", "१०,०००", "10 हज़ार", "1.5 lakh" (each also as the bare number)."""
    quote = privacy.comparable(quote)
    words = "|".join(sorted({privacy.comparable(w) for w in _MULTIPLIERS}, key=len, reverse=True))
    amounts = []
    for number, word in re.findall(rf"(\d[\d,]*(?:\.\d+)?)\s*({words})?(?![a-z])", quote):
        value = float(number.replace(",", ""))
        amounts.append(int(value))
        if word:
            amounts.append(int(round(value * {privacy.comparable(k): v for k, v in _MULTIPLIERS.items()}[word])))
    return amounts


HINDI_STATE_NAMES = {
    "Andhra Pradesh": ["आंध्र प्रदेश"], "Assam": ["असम"], "Bihar": ["बिहार"], "Chhattisgarh": ["छत्तीसगढ़"],
    "Goa": ["गोवा"], "Gujarat": ["गुजरात"], "Haryana": ["हरियाणा"], "Himachal Pradesh": ["हिमाचल प्रदेश", "हिमाचल"],
    "Jammu and Kashmir": ["जम्मू और कश्मीर", "जम्मू-कश्मीर"], "Jharkhand": ["झारखंड", "झारखण्ड"],
    "Karnataka": ["कर्नाटक"], "Kerala": ["केरल"], "Madhya Pradesh": ["मध्य प्रदेश"], "Maharashtra": ["महाराष्ट्र"],
    "Odisha": ["ओडिशा", "उड़ीसा"], "Punjab": ["पंजाब"], "Rajasthan": ["राजस्थान"], "Tamil Nadu": ["तमिलनाडु"],
    "Telangana": ["तेलंगाना"], "Tripura": ["त्रिपुरा"], "Uttar Pradesh": ["उत्तर प्रदेश", "यूपी"],
    "Uttarakhand": ["उत्तराखंड", "उत्तराखण्ड"], "West Bengal": ["पश्चिम बंगाल", "बंगाल"], "Delhi": ["दिल्ली"],
    "Chandigarh": ["चंडीगढ़"], "Ladakh": ["लद्दाख"], "Puducherry": ["पुडुचेरी"],
}


def _state_in(state: str, quote: str) -> bool:
    q = privacy.comparable(quote)
    return state.casefold() in q or any(privacy.comparable(n) in q for n in HINDI_STATE_NAMES.get(state, []))


def state_names() -> List[str]:
    with open(INCOME_LIMITS, newline="", encoding="utf-8") as f:
        return [r["state_or_ut"] for r in csv.DictReader(f) if not r["state_or_ut"].startswith("Supreme Court")]


def check_general_answer(raw: dict, notes: str, code: str = "en") -> GeneralReading:
    r = GeneralReading()
    if not isinstance(raw, dict):
        return r
    person = clean(raw.get("person_needing_help"), 120)
    r.person = "" if not person or person.casefold().strip(" .") in GENERIC_PERSON else person
    r.what_happened = [c for c in (clean(s) for s in (raw.get("what_happened") or [])[:6]) if c]
    for t in (raw.get("timeline") or [])[:10]:
        if isinstance(t, dict) and clean(t.get("what")):
            r.timeline.append((clean(t.get("when"), 60) or "date not given", clean(t.get("what"))))
    for t in (raw.get("coming_dates") or [])[:5]:
        if isinstance(t, dict) and intake._in_notes(t.get("quote"), notes):
            r.coming_dates.append((clean(t.get("when"), 60), clean(t.get("what"))))

    for key in YES_NO_FACTS:
        value, quote = _quoted(raw.get(key), notes)
        if value in ("yes", "no") and quote:
            r.facts[key] = value == "yes"
            r.evidence[key] = quote
        elif value in ("yes", "no"):
            r.dropped.append(key)
            if value == "yes":
                r.unconfirmed_yes.append(key)

    value, quote = _quoted(raw.get("state"), notes)
    if value and quote:
        value_text = str(value).strip()
        match = [s for s in state_names()
                 if (s.casefold() == value_text.casefold() or value_text in HINDI_STATE_NAMES.get(s, []))
                 and _state_in(s, quote)]
        if match:
            r.facts["state"] = match[0]
            r.evidence["state"] = quote
        else:
            r.dropped.append("state")

    income = raw.get("income") if isinstance(raw.get("income"), dict) else {}
    amount, per, quote = income.get("amount"), income.get("per"), income.get("quote")
    if isinstance(amount, (int, float)) and amount >= 0 and per in ("month", "year") \
            and intake._in_notes(quote, notes) and int(amount) in _digits_in(quote):
        r.facts["annual_income"] = int(amount) * (12 if per == "month" else 1)
        r.evidence["annual_income"] = quote
    elif amount is not None:
        r.dropped.append("income")

    # Sections charged: kept only if written in the notes AND found in the sentence table.
    for s in (raw.get("sections_charged") or [])[:5]:
        if not isinstance(s, dict):
            continue
        law, sec, quote = str(s.get("law", "")).upper(), str(s.get("section", "")).strip(), s.get("quote")
        if law in ("IPC", "BNS") and sec and intake._in_notes(quote, notes) \
                and re.sub(r"\s+", "", sec).casefold() in re.sub(r"\s+", "", quote).casefold():
            rows = section479.find_offences(law, sec)
            if rows:
                r.sections_as_written.append(f"{law} {sec}")
                r.sections.extend(o for o in rows if o not in r.sections)

    for i in (raw.get("issues") or [])[:5]:
        if isinstance(i, dict) and clean(i.get("name"), 80):
            category = i.get("category") if i.get("category") in ISSUE_CATEGORIES else "other"
            r.issues.append((category, clean(i.get("name"), 80)))
    if r.facts.get("in_custody") and not any(c == "arrest_or_custody" for c, _ in r.issues):
        r.issues.insert(0, ("arrest_or_custody", "someone is in custody"))
    if r.facts.get("money_lost_online") and not any(c == "online_or_financial_fraud" for c, _ in r.issues):
        r.issues.append(("online_or_financial_fraud", "money lost online"))

    r.documents_held = [c for c in (clean(d, 100) for d in (raw.get("documents_held") or [])[:10]) if c]
    r.questions = [c for c in (clean(q, 200) for q in (raw.get("questions_to_ask") or [])[:5])
                   if c and not privacy.personal_details_found(c)]
    value, quote = _quoted(raw.get("outcome_wanted"), notes)
    if value and quote:
        r.outcome = clean(value, 200)
    r.questions = follow_up_questions(r, code)
    return r


# Words that show a question is about a fact; if the fact is already known, the question is dropped.
FACT_WORDS = {
    "state": ["which state", "what state", "राज्य"],
    "annual_income": ["income", "earn", "salary", "आमदनी", "आय", "कमाई"],
    "woman": ["woman", "female", "gender", "महिला"],
    "under_18": ["how old", "age", "under 18", "उम्र"],
    "in_custody": ["in custody", "in jail", "हिरासत", "जेल में"],
    "sc_st": ["caste", "tribe", "sc/st", "जाति"],
    "disability": ["disab", "दिव्यांग"],
}
OUTCOME_WORDS = ["want", "hope", "outcome", "expect", "wish", "चाह", "परिणाम", "नतीजा", "नतीजे", "उम्मीद", "अपेक्षा",
                 "chahte", "chahti", "chahta", "chahiye"]
RELATIVE_WHEN = re.compile(r"today|yesterday|ago|last (week|month|night)|this (week|month|morning)|आज|कल|पहले|पिछले",
                           re.I)


def follow_up_questions(r: GeneralReading, code: str = "en") -> List[str]:
    """The AI's questions, checked by plain code: nothing the story already answers; then what the
    person wants (if the story doesn't say) and the year of any date written without one."""
    def t(key, **params):
        return lang.t(key, code, **params)

    def has(question: str, words) -> bool:  # whole words only ("age" is not in "wages")
        return any(re.search(rf"(?<!\w){re.escape(w)}", question.casefold()) for w in words)

    questions = [q for q in r.questions
                 if not any(fact in r.facts and has(q, words) for fact, words in FACT_WORDS.items())]
    if not r.person and not any(has(q, ["who needs", "who is the person", "किसे मदद"]) for q in questions):
        questions.append(t("q.person"))
    if not r.outcome and not any(has(q, OUTCOME_WORDS) for q in questions):
        questions.append(t("q.outcome"))
    for when, what in (r.timeline + r.coming_dates):
        if len([q for q in questions if q.startswith(t("q.year_start"))]) >= 2:
            break
        if when and not re.search(r"\b(19|20)\d{2}\b", privacy.normalise_digits(when)) and not RELATIVE_WHEN.search(when) \
                and when != "date not given":
            questions.append(t("q.year", when=when, what=what))
    return questions[:7]


# ---------- urgency (rules in CLAUDE.md) ----------

PRECAUTION_FACTS = ("danger_now", "money_lost_online", "money_lost_in_last_few_days")


def urgent_actions(facts: Dict[str, object], unconfirmed_yes=()) -> List[str]:
    """'Call 112 now.' if anyone is in danger. 'Call 1930 now.' if money was lost online in the last
    few days (or when is not known) and 1930 has not been called.

    Safety first: a "yes" from the AI whose words couldn't be found in the notes (unconfirmed_yes)
    still counts here, as a precaution. A false alarm is better than a missed one."""
    facts = dict(facts)
    for key in unconfirmed_yes:
        if key in PRECAUTION_FACTS and key not in facts:
            facts[key] = True
    actions = []
    if facts.get("danger_now") is True:
        actions.append(CALL_112)
    if (facts.get("money_lost_online") is True and facts.get("money_lost_in_last_few_days") is not False
            and facts.get("called_1930") is not True):
        actions.append(CALL_1930)
    return actions


# ---------- issues and knowledge ----------

def issue_guidance(category: str) -> List[knowledge.Entry]:
    return [knowledge.get(f, h) for f, h in ISSUE_KNOWLEDGE.get(category, [])]


def _words(texts: List[str]) -> List[str]:
    return re.findall(r"[a-z][a-z-]+", " ".join(texts).casefold())


_DOC_STOP = ("copy", "copies", "any", "the", "and", "all", "has", "proof", "number", "numbers", "for", "free",
             "legal", "aid", "received", "with", "given", "one", "was", "if", "latest", "last", "three", "two")


def _doc_words(text: str) -> List[str]:
    return [w.rstrip("s") for w in re.findall(r"[A-Za-z]{3,}", text.casefold()) if w not in _DOC_STOP]


def _not_held(items: List[str], held: List[str]) -> List[str]:
    held_words = " ".join(held).casefold()

    def has(item: str) -> bool:
        keys = [w for w in re.findall(r"[A-Za-z]{3,}", item.casefold())
                if w not in ("copy", "copies", "any", "the", "and", "all", "has", "proof", "number", "numbers",
                             "for", "free", "legal", "aid", "received", "with")]
        if bool(keys) and all(k in held_words for k in keys[:2]):
            return True
        item_words = set(_doc_words(item))  # "latest bill" covers "Latest electricity bill"
        return any(h and (h <= item_words or len(h & item_words) >= 2) for h in (set(_doc_words(x)) for x in held))

    return [i for i in items if not has(i)]


def document_lists(categories: List[str], held: List[str], story: List[str]) -> List[Tuple[str, List[str], str]]:
    """Documents still to collect, as (label, items, source line or "").

    Issues covered by our files: the list from that knowledge entry, with its Source line.
    Other issues: a plain list by type of problem (no law named), FIR and court papers only if the
    story mentions police, an arrest or a court case, and always ID proof and income proof.
    'story' is the saved summary text (the pasted notes are never kept)."""
    lists = []
    for cat in dict.fromkeys(categories):
        if cat in ISSUE_DOCUMENTS:
            entry = knowledge.get(*ISSUE_DOCUMENTS[cat])
            items = [l.lstrip("- ").strip() for l in entry.body.splitlines() if l.strip().startswith("- ")]
            lists.append(("Still to collect", _not_held(items, held), entry.source_line))
    if "other" in categories or not lists:
        words = set(_words(story))
        items: List[str] = []
        for _, keys, docs in PROBLEM_DOCUMENTS:  # "wage" also matches "wages", "work" matches "worked"
            if any(w.startswith(k) for w in words for k in keys):
                items += docs
        if words & set(POLICE_OR_COURT_WORDS):
            items += POLICE_OR_COURT_DOCUMENTS
        if not items:
            items = ["Any papers, receipts or messages about the problem", "Notices received"]
        items += ALWAYS_DOCUMENTS
        lists.append((OFTEN_HELP, _not_held(list(dict.fromkeys(items)), held), ""))
    return lists


# ---------- free legal aid eligibility (plain code) ----------

ELIGIBILITY_ENTRY = ("legal_aid_eligibility.md", "Who qualifies for free legal aid")
WORTH_PURSUING_ENTRY = ("legal_aid_eligibility.md", "The person must also have a case worth pursuing")
GROUPS = [
    ("in_custody", "a person in custody"),
    ("woman", "a woman"),
    ("under_18", "a child (under 18)"),
    ("sc_st", "a member of a Scheduled Caste or Scheduled Tribe"),
    ("disability", "a person with a disability"),
]
ELIGIBILITY_QUESTIONS = {
    "in_custody": "Is the person needing help in jail or police custody now?",
    "woman": "Is the person needing help a woman?",
    "under_18": "Is the person needing help under 18?",
    "sc_st": "Is the person needing help from a Scheduled Caste or Scheduled Tribe?",
    "disability": "Does the person needing help have a disability?",
    "state": "Which state or union territory does the person live in?",
    "annual_income": "What is the family's income? (per month or per year)",
}


@dataclass
class Eligibility:
    status: str  # "eligible", "not eligible on income alone", "not decided yet"
    reason: str
    missing: List[str]
    notes: List[str]
    sources: List[str]
    reason_key: str = ""
    params: Dict[str, object] = field(default_factory=dict)


def income_limit(state: str) -> Tuple[Optional[int], str, str]:
    with open(INCOME_LIMITS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["state_or_ut"].casefold() == state.casefold():
                return int(r["annual_income_limit_inr"]), r["notes"], r["source_url"]
    return None, "", ""


INTERNAL_NOTE = re.compile(r"(^|;\s*)(confirmed|checked|verified|seen|todo|note to self)\b[^;]*", re.I)


def public_note(note: str) -> str:
    """A state's note from income_limits.csv without our own working notes ("Confirmed on BSLSA site")."""
    parts = [p.strip() for p in (note or "").split(";")]
    return "; ".join(p for p in parts if p and not INTERNAL_NOTE.match(p))


def check_eligibility(facts: Dict[str, object]) -> Eligibility:
    """Section 12 groups first (they qualify whatever the income), then the state income limit.
    'missing' lists only the facts still needed to decide, in the order to ask them."""
    who = knowledge.get(*ELIGIBILITY_ENTRY)
    sources = [who.source_line]
    worth = knowledge.get(*WORTH_PURSUING_ENTRY)
    notes = ["The DLSA decides. It must also be satisfied that the person has a case worth pursuing. "
             + worth.source_line]

    state, income = facts.get("state"), facts.get("annual_income")
    limit = None
    if state:
        limit, note, url = income_limit(str(state))
        note = public_note(note)
        if note:  # state rules (e.g. Bihar's extra groups) and limits flagged for checking
            notes.append(f"{state}: {note}")

    groups = [label for key, label in GROUPS if facts.get(key) is True]
    if groups:
        group_key = next(key for key, _ in GROUPS if facts.get(key) is True)
        return Eligibility("eligible", f"Qualifies for free legal aid whatever the income, as {groups[0]}.",
                           [], notes, sources, "elig.group", {"group": group_key})

    unknown_groups = [key for key, _ in GROUPS if facts.get(key) is None]
    if state:
        if limit is not None:
            sources.append(f"Source: NALSA state income limits ({url})")
        if limit is not None and income is not None:
            if int(income) < limit:
                return Eligibility("eligible", f"Qualifies on income: about ₹{int(income):,} a year is below "
                                   f"{state}'s limit of ₹{limit:,}.", [], notes, sources, "elig.income_below",
                                   {"income": int(income), "limit": limit, "state": state})
            if not unknown_groups:
                return Eligibility("not eligible on income alone",
                                   f"About ₹{int(income):,} a year is not below {state}'s limit of "
                                   f"₹{limit:,}, and none of the groups above applies. Some states add "
                                   "more groups: ask the DLSA or NALSA's free helpline 15100.",
                                   [], notes, sources, "elig.income_above",
                                   {"income": int(income), "limit": limit, "state": state})
    missing = unknown_groups + [k for k in ("state", "annual_income") if facts.get(k) is None]
    return Eligibility("not decided yet", "Not decided yet: a few facts are still needed.", missing, notes, sources,
                       "elig.undecided")


# ---------- next steps ----------

def next_steps(facts: Dict[str, object], categories: List[str], eligibility: Eligibility,
               docs_missing: List[str]) -> Tuple[List[str], knowledge.Entry]:
    """docs_missing: every document still to collect, from document_lists."""
    when = knowledge.get("helplines.md", "When to use which")
    steps = []
    if facts.get("danger_now") is True:
        steps.append("Someone is in danger: call 112 now.")
    if CALL_1930 in urgent_actions(facts, facts.get("_precautions", ())):
        steps.append("Money was lost online: call 1930 now, or report on cybercrime.gov.in.")
    if "arrest_or_custody" in categories:
        steps.append("Someone is in custody: open the Section 479 check, and contact the jail legal aid "
                     "clinic or the District Legal Services Authority (DLSA).")
    if "online_or_financial_fraud" in categories:
        steps.append("Online fraud: tell the bank in writing. (The cyber fraud module is coming next.)")
    if eligibility.status == "eligible":
        steps.append("Help the person apply to the DLSA for a free legal aid lawyer, or call 15100.")
    elif eligibility.status == "not decided yet":
        steps.append("Finish the free legal aid check (see the facts still needed).")
    if any(c == "other" for c in categories):
        steps.append("For problems our files don't cover yet: NALSA's free helpline 15100, or Tele-Law 14454 "
                     "for advice before any case is filed.")
    if docs_missing:
        steps.append("Collect the documents still missing.")
    steps.append("A supervisor checks this summary before anyone relies on it.")
    return steps, when


# ---------- possible names (a warning for the volunteer) ----------

_NOT_NAMES = {
    "the", "a", "an", "he", "she", "they", "his", "her", "their", "it", "we", "i", "my", "our", "this", "that",
    "speaker", "practice", "case", "today", "yesterday", "date", "fir", "upi", "otp", "pin", "sms", "atm",
    "ipc", "bns", "bnss", "crpc", "dlsa", "nalsa", "slsa", "rs", "inr", "no", "yes", "not", "police", "court",
    "bank", "jail", "district", "high", "supreme", "india", "indian", "government", "aadhaar", "pan",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mr", "mrs", "ms", "dr", "shri", "smt",
    "agent", "raahi",  # the app's own name, "Agent Raahi"
}


def possible_names(summary: str, notes: str) -> List[str]:
    """Capitalised words from the middle of sentences in the notes that also appear in the summary.
    A rough check: names can't be detected reliably, so the volunteer must also confirm."""
    states = {w.casefold() for s in state_names() for w in s.split()}
    found = []
    for sentence in re.split(r"(?<=[.!?:])\s+|\n", notes):
        words = re.findall(r"[A-Za-z][A-Za-z'’-]+", sentence)
        for w in words[1:]:
            if w[0].isupper() and len(w) > 2 and w.casefold() not in _NOT_NAMES and w.casefold() not in states \
                    and re.search(rf"\b{re.escape(w)}\b", summary) and w not in found:
                found.append(w)
    return found


# ---------- the summary draft ----------

@dataclass
class GeneralFacts:
    """What is saved for a general case: the checked summary, no notes, no names."""

    CASE_TYPE = CASE_TYPE
    person: str
    what_happened: List[str]
    timeline: List[Tuple[str, str]]
    coming_dates: List[Tuple[str, str]]
    issues: List[Tuple[str, str]]
    sections: List[str]                       # "IPC 380 = BNS 305: Theft ..." from the sentence table
    documents_held: List[str]
    answers: List[Tuple[str, str]]            # questions answered by the volunteer
    still_to_ask: List[str]
    facts: Dict[str, object]                  # yes/no facts, state, annual_income
    today: str
    precautions: List[str] = field(default_factory=list)  # unconfirmed "yes" answers used only for safety
    # For issues our files don't cover: approved research and saved research knowledge, with sources
    # (research.items_for_summary). Never AI text the supervisor has not approved.
    research: List[dict] = field(default_factory=list)
    outcome: str = ""  # what the person wants, from the notes (or answered as a question)
    evidence: Dict[str, str] = field(default_factory=dict)  # quotes kept for the lawyer (e.g. a payment demand)
    research_state: str = "none"  # "none" (our files cover it), "waiting", "failed", "approved"

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d.update(self.facts)  # eligibility and urgency facts at the top level (for the audit record)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GeneralFacts":
        keys = ["person", "what_happened", "timeline", "coming_dates", "issues", "sections", "documents_held",
                "answers", "still_to_ask", "facts", "today"]
        return cls(**{k: d[k] for k in keys}, precautions=d.get("precautions", []), research=d.get("research", []),
                   outcome=d.get("outcome", ""), evidence=d.get("evidence", {}),
                   research_state=d.get("research_state", "none"))


def build_facts(reading: GeneralReading, answers: List[Tuple[str, str]], still_to_ask: List[str],
                facts: Dict[str, object], today: date) -> GeneralFacts:
    sections = [f"IPC {o.ipc_section} = BNS {o.bns_section}: {o.offence}" for o in reading.sections]
    return GeneralFacts(
        person=reading.person, what_happened=reading.what_happened, timeline=reading.timeline,
        coming_dates=reading.coming_dates, issues=reading.issues, sections=sections,
        documents_held=reading.documents_held,
        answers=[(clean(q, 200), clean(a, 300)) for q, a in answers],
        still_to_ask=still_to_ask, facts=dict(facts), today=today.isoformat(),
        precautions=[k for k in reading.unconfirmed_yes if k in PRECAUTION_FACTS],
        outcome=reading.outcome,
        evidence={k: v for k, v in reading.evidence.items() if k == "unofficial_payment_demand"},
    )


def _yes_no(v) -> str:
    return "yes" if v is True else "no" if v is False else "not known"


def case_next_steps(g: "GeneralFacts") -> List[str]:
    """The summary's own next steps (used for the case's timeline after approval)."""
    categories = [c for c, _ in g.issues]
    eligibility = check_eligibility(g.facts)
    story = g.what_happened + [n for _, n in g.issues] + g.documents_held
    docs = [i for _, items, _ in document_lists(categories or ["other"], g.documents_held, story) for i in items]
    steps, _ = next_steps({**g.facts, "_precautions": g.precautions}, categories, eligibility, docs)
    return steps


def research_for(g: "GeneralFacts", name: str) -> List[dict]:
    return [i for i in g.research if i.get("issue") == name]


def uncovered_issues(g: "GeneralFacts") -> List[str]:
    """Issues the summary marks "not covered by our verified files" (no entry, no approved research)."""
    issues = g.issues or [("other", "the problem described")]
    return [name for category, name in issues if not ISSUE_KNOWLEDGE.get(category) and not research_for(g, name)]


def _research_lines(items: List[dict], hi: bool = False) -> List[str]:
    out = []
    for i in items:
        if i["origin"] == "knowledge":
            head = (_hi("sum.research_knowledge", heading=i["heading"], date=i["approved_on"]) if hi else
                    f"From approved research saved in our files, “{i['heading']}” (lawyer checked {i['approved_on']}):")
        else:
            head = (_hi("sum.research_case", heading=i["heading"], date=i["approved_on"]) if hi else
                    f"{i['heading']} (AI research, approved by the supervisor on {i['approved_on']}):")
        out.append(f"   {head}")
        out += [f"   {line}" for line in i["text"].splitlines() if line.strip()]
        out.append(f"   {i['source_line']}")
    if items and hi:
        out.append("   " + _hi("sum.research_english"))
    return out


def summary_body(g: GeneralFacts) -> str:
    """The summary text (without the DRAFT header and the AI disclosure)."""
    facts = g.facts
    categories = [c for c, _ in g.issues]
    eligibility = check_eligibility(facts)
    story = g.what_happened + [f"{w} {what}" for w, what in g.timeline] \
        + [f"{w} {what}" for w, what in g.coming_dates] + [n for _, n in g.issues] + g.documents_held \
        + [f"{q} {a}" for q, a in g.answers] + (["jail"] if facts.get("in_custody") else [])
    doc_lists = document_lists(categories or ["other"], g.documents_held, story)
    docs_missing = [i for _, items, _ in doc_lists for i in items]
    steps, steps_entry = next_steps({**facts, "_precautions": g.precautions}, categories, eligibility, docs_missing)
    out = ["CASE SUMMARY — any case (general intake)",
           f"Date: {drafts.show_date(date.fromisoformat(g.today))}",
           "Prepared from the volunteer's notes. People are described by their role only.",
           f"Person needing help: {g.person or 'Not stated (ask who needs the help)'}", ""]

    out += _glance_lines(g, "en")
    urgent = urgent_actions(facts, g.precautions)
    flags = []
    if facts.get("in_custody") is True:
        flags.append("Someone is in custody now.")
    if facts.get("essential_service_cut") is True:  # the same rule as "At a glance"
        flags.append(lang.t("cw.urgent_service", "en", what=lang.t(
            "cw.service.water" if _is_water(g) else "cw.service.electricity", "en")))
    flags += [f"Coming up: {w} — {what}" for w, what in g.coming_dates]
    out.append("URGENT")
    out += [f"- {a}" for a in urgent + flags] or ["- Nothing urgent found in the notes."]
    out.append("")

    out.append("What happened")
    out += [f"- {s}" for s in g.what_happened] or ["- (not clear from the notes)"]
    if g.outcome:
        out += ["", "What the person wants", f"- {g.outcome}"]
    if g.timeline:
        out += ["", "Timeline"] + [f"- {w}: {what}" for w, what in g.timeline]
    if g.sections:
        out += ["", "Sections written in the notes (as found in our sentence table)"]
        out += [f"- {s}" for s in g.sections]
    out.append("")

    out.append("Possible legal issues (each to discuss with a lawyer)")
    for n, (category, name) in enumerate(g.issues or [("other", "the problem described")], 1):
        out.append(f"{n}. {name[0].upper() + name[1:]} — {TO_DISCUSS}.")
        entries = issue_guidance(category)
        researched = research_for(g, name)
        if not entries and not researched:
            out.append(f"   {NOT_COVERED[0].upper() + NOT_COVERED[1:]}.")
        out += _research_lines(researched)
        for e in entries:
            out.append(f"   From our verified files, “{e.heading}”:")
            out += [f"   {line}" for line in e.excerpt(4).splitlines()]
            out.append(f"   {e.source_line}")
    out.append("")

    out.append("Documents")
    out.append("- The person has: " + ("; ".join(g.documents_held) if g.documents_held else "none mentioned"))
    out += _document_lines(g, doc_lists, "en")
    out.append("")

    out.append("Free legal aid")
    out.append(f"- {eligibility.reason}")
    if eligibility.missing:
        out.append("- Still needed: " + "; ".join(ELIGIBILITY_QUESTIONS[m] for m in eligibility.missing))
    out += [f"- {n}" for n in eligibility.notes]
    out += [f"  {s}" for s in eligibility.sources]
    out.append(f"- Facts used: in custody {_yes_no(facts.get('in_custody'))}; woman {_yes_no(facts.get('woman'))}; "
               f"under 18 {_yes_no(facts.get('under_18'))}; SC/ST {_yes_no(facts.get('sc_st'))}; "
               f"disability {_yes_no(facts.get('disability'))}; state {facts.get('state') or 'not known'}; "
               "yearly income " + (f"about ₹{int(facts['annual_income']):,}"
                                   if facts.get("annual_income") is not None else "not known"))
    out.append("")

    if g.answers:
        out.append("Answers from the volunteer")
        out += [f"- {q} — {a}" for q, a in g.answers]
        out.append("")
    if g.still_to_ask:
        out.append("Questions still to ask")
        out += [f"- {q}" for q in g.still_to_ask]
        out.append("")

    out += _lawyer_lines(g, "en")
    out.append("Next steps")
    out += _step_lines(g, eligibility, "en")
    out.append("")
    out.append("This summary does not predict the outcome of the case.")
    return "\n".join(out)


# ---------- the summary in Hindi ----------

def _hi(key: str, **params) -> str:
    return lang.t(key, "hi", **params)


def _hi_known(prefix: str, english: str) -> str:
    """A fixed English phrase (next step, document) in Hindi, if hi.json has it; else the English."""
    return lang.strings("hi").get(prefix + english, english)


def _money(n: int) -> str:
    return f"\u20b9{n:,}"


def eligibility_text(e: Eligibility, code: str) -> str:
    if code == "en" or not e.reason_key:
        return e.reason
    p = dict(e.params)
    if "group" in p:
        p["group"] = lang.t(f"group.{p['group']}", code)
    for k in ("income", "limit"):
        if k in p:
            p[k] = _money(int(p[k]))
    return lang.t(e.reason_key, code, **p)


def _yes_no_hi(v) -> str:
    return _hi("yes") if v is True else _hi("no") if v is False else _hi("sum.not_known")


def summary_body_hi(g: "GeneralFacts") -> str:
    """The summary in everyday Hindi. Legal text comes from knowledge_hi/ (English if missing), each
    with its "translation checked" label; Source lines stay in English."""
    facts = g.facts
    categories = [c for c, _ in g.issues]
    eligibility = check_eligibility(facts)
    story = g.what_happened + [f"{w} {what}" for w, what in g.timeline] \
        + [f"{w} {what}" for w, what in g.coming_dates] + [n for _, n in g.issues] + g.documents_held \
        + [f"{q} {a}" for q, a in g.answers] + (["jail"] if facts.get("in_custody") else [])
    doc_lists = document_lists(categories or ["other"], g.documents_held, story)
    docs_missing = [i for _, items, _ in doc_lists for i in items]
    steps, steps_entry = next_steps({**facts, "_precautions": g.precautions}, categories, eligibility, docs_missing)
    out = [_hi("sum.title"), _hi("sum.date", date=lang.show_date(date.fromisoformat(g.today), "hi")),
           _hi("sum.prepared"), _hi("sum.person", person=g.person or _hi("cw.person_not_stated")), ""]
    out += _glance_lines(g, "hi")

    urgent = [_hi("safety.call112") if a == CALL_112 else _hi("safety.call1930")
              for a in urgent_actions(facts, g.precautions)]
    flags = [_hi("sum.in_custody")] if facts.get("in_custody") is True else []
    if facts.get("essential_service_cut") is True:
        flags.append(lang.t("cw.urgent_service", "hi", what=lang.t(
            "cw.service.water" if _is_water(g) else "cw.service.electricity", "hi")))
    flags += [_hi("sum.coming_up", when=w, what=what) for w, what in g.coming_dates]
    out.append(_hi("sum.urgent"))
    out += [f"- {a}" for a in urgent + flags] or [f"- {_hi('sum.nothing_urgent')}"]
    out.append("")

    out.append(_hi("sum.what_happened"))
    out += [f"- {x}" for x in g.what_happened] or [f"- {_hi('sum.not_clear')}"]
    if g.outcome:
        out += ["", _hi("sum.outcome"), f"- {g.outcome}"]
    if g.timeline:
        out += ["", _hi("sum.timeline")] + [f"- {w}: {what}" for w, what in g.timeline]
    if g.sections:
        out += ["", _hi("sum.sections")] + [f"- {x}" for x in g.sections]
    out.append("")

    out.append(_hi("sum.issues"))
    for n, (category, name) in enumerate(g.issues or [("other", _hi("sum.problem_described"))], 1):
        out.append(f"{n}. {name} \u2014 {_hi('sum.to_discuss')}.")
        entries = [knowledge.get(f, h, "hi") for f, h in ISSUE_KNOWLEDGE.get(category, [])]
        researched = research_for(g, name)
        if not entries and not researched:
            out.append(f"   {_hi('sum.not_covered')}")
        out += _research_lines(researched, hi=True)
        for e in entries:
            out.append("   " + _hi("sum.from_files", heading=e.heading))
            out += [f"   {line}" for line in e.excerpt(4).splitlines()]
            if e.lang == "hi" and not e.translation_checked:
                out.append("   " + _hi("sum.translation_not_checked"))
            out.append(f"   {e.source_line}")
    out.append("")

    out.append(_hi("sum.documents"))
    out.append(_hi("sum.has") + ("; ".join(g.documents_held) if g.documents_held else _hi("sum.none_mentioned")))
    out += _document_lines(g, doc_lists, "hi", categories)
    out.append("")

    out.append(_hi("sum.legal_aid"))
    out.append(f"- {eligibility_text(eligibility, 'hi')}")
    if eligibility.missing:
        out.append(_hi("sum.still_needed") + "; ".join(_hi(f"elig.q.{m}") for m in eligibility.missing))
    worth = knowledge.get(*WORTH_PURSUING_ENTRY)
    out.append(f"- {_hi('elig.dlsa_decides')} {worth.source_line}")
    out += [f"- {n}" for n in eligibility.notes[1:]]  # state notes from income_limits.csv (in English)
    out += [f"  {x}" for x in eligibility.sources]
    income = facts.get("annual_income")
    out.append(_hi("sum.facts_used", custody=_yes_no_hi(facts.get("in_custody")), woman=_yes_no_hi(facts.get("woman")),
                   under18=_yes_no_hi(facts.get("under_18")), scst=_yes_no_hi(facts.get("sc_st")),
                   disability=_yes_no_hi(facts.get("disability")), state=facts.get("state") or _hi("sum.not_known"),
                   income=_hi("sum.about", amount=_money(int(income))) if income is not None else _hi("sum.not_known")))
    out.append("")

    if g.answers:
        out.append(_hi("sum.answers"))
        out += [f"- {q} \u2014 {a}" for q, a in g.answers]
        out.append("")
    if g.still_to_ask:
        out.append(_hi("sum.still_to_ask"))
        out += [f"- {_hi_known('elig.q_en:', q)}" for q in g.still_to_ask]
        out.append("")

    out += _lawyer_lines(g, "hi")
    out.append(_hi("sum.next_steps"))
    out += _step_lines(g, eligibility, "hi")
    out.append("")
    out.append(_hi("sum.no_prediction"))
    return "\n".join(out)


def _is_water(g: "GeneralFacts") -> bool:
    import casework
    return casework.problem_type(g) == "water"


def _approved_points(g: "GeneralFacts") -> List[dict]:
    """Approved research points shown with this case (saved knowledge entries count as approved routes)."""
    out = []
    for i in g.research:
        kind = i.get("kind") or "route"
        src = i.get("source_line", "")
        out.append({"kind": kind, "text": i["text"], "approved_on": i.get("approved_on", ""),
                    "sources": [], "source_line": src})
    return out


def _glance_lines(g: "GeneralFacts", code: str) -> List[str]:
    import casework
    today = date.fromisoformat(g.today)
    label = (lambda k: lang.t(k, code))
    problem = "; ".join(n for _, n in g.issues) or label("cw.not_stated")
    lasting = casework.duration(g, today, code) or label("cw.not_known_yet")
    u = casework.urgency(g, today, code)
    return [label("cw.glance").upper() if code == "en" else label("cw.glance"),
            f"- {label('cw.g_problem')}: {problem}",
            f"- {label('cw.g_wants')}: {g.outcome or label('cw.not_stated')}",
            f"- {label('cw.g_how_long')}: {lasting}",
            f"- {label('cw.g_urgency')}: {'; '.join(u.reasons)}", ""]


def _document_lines(g: "GeneralFacts", doc_lists, code: str, categories=None) -> List[str]:
    import casework
    items, origin = casework.documents_needed(g, _approved_points(g), code)
    label = lang.t("cw.docs_needed", code)
    out = [f"- {label}: " + ("; ".join(items) if items else lang.t("cw.nothing_more", code))]
    if origin == "files":
        for _, _, source_line in doc_lists[:1]:
            if source_line:
                out.append(f"  ({source_line})")
    elif origin == "plain":
        out.append("  (" + lang.t("cw.docs_plain_note", code) + ")")
    return out


def _lawyer_lines(g: "GeneralFacts", code: str) -> List[str]:
    import casework
    flags = casework.lawyer_flags(g, code)
    return ([lang.t("cw.for_lawyer", code)] + [f"- {f}" for f in flags] + [""]) if flags else []


def _step_lines(g: "GeneralFacts", eligibility, code: str) -> List[str]:
    import casework
    steps = casework.next_steps(g, eligibility, _approved_points(g), g.research_state, date.fromisoformat(g.today),
                                code)
    out = []
    for i, s in enumerate(steps, 1):
        when = ""
        if s.due:
            when = " — " + lang.t("cw.by_date" if not s.suggested else "cw.by_date_suggested", code,
                                  date=lang.show_date(s.due, code))
        out.append(f"{i}. {s.text}{when}")
        if s.source:
            out.append(f"   ({s.source})")
    return out


def _hindi_document(item: str, categories: List[str]) -> str:
    """A document name in Hindi: from the Hindi knowledge entry (same order as the English list), or hi.json."""
    for cat in categories:
        if cat in ISSUE_DOCUMENTS:
            en_entry = knowledge.get(*ISSUE_DOCUMENTS[cat])
            hi_entry = knowledge.get(*ISSUE_DOCUMENTS[cat], "hi")
            en_items = [l.lstrip("- ").strip() for l in en_entry.body.splitlines() if l.strip().startswith("- ")]
            hi_items = [l.lstrip("- ").strip() for l in hi_entry.body.splitlines() if l.strip().startswith("- ")]
            if item in en_items and len(hi_items) == len(en_items):
                return hi_items[en_items.index(item)]
    return _hi_known("doc:", item)


def make_summary_draft(g: GeneralFacts, ai_model: Optional[str], code: str = "en") -> str:
    if code == "hi":
        text = drafts.DRAFT_HEADER + "\n" + _hi("draft.header") + "\n\n" + summary_body_hi(g)
        return drafts.add_disclosure(text, ai_model, rules=RULES_USED, code="hi")
    text = drafts.DRAFT_HEADER + "\n\n" + summary_body(g)
    return drafts.add_disclosure(text, ai_model, rules=RULES_USED)


def make_case_file(case_id: str, facts: dict, approved_on: date) -> str:
    g = GeneralFacts.from_dict(facts)
    eligibility = check_eligibility(g.facts)
    follow_up = approved_on + timedelta(days=7)
    lines = [f"# Case {case_id}", "",
             f"- Date: {drafts.show_date(approved_on)}",
             f"- Case type: {CASE_TYPE_LABEL}",
             "- Status: approved by supervisor",
             f"- Follow-up date: {drafts.show_date(follow_up)}", "",
             "## Summary", summary_body(g), "",
             "## Free legal aid", f"- {eligibility.status}: {eligibility.reason}", "",
             "No names or personal details are stored in this file."]
    return "\n".join(lines) + "\n"
