"""Step 3, "Draft and research": plain code that turns a checked case into something the volunteer can
act on. No AI here.

- problem_type: what kind of problem (custody, online fraud, electricity, water, wages, ration, family,
  land, other), from the issue categories and the words of the checked summary.
- urgency: fixed rules (danger, fresh online fraud, custody, an essential service cut off, a date soon).
- duration: how long it has been going on, from the first dated event (only full or month-year dates).
- documents: the list that fits the problem type (no pay slips for an electricity case), or the
  "documents usually needed" points the supervisor approved from research.
- lawyer_flags: things the lawyer should see (a demand for an unofficial payment), with the quote.
- next_steps: specific to the problem and the state, from our files or approved research points, with
  dates (suggested follow-ups are labelled as suggested); general help only after them.
- complaint_letter: from templates/complaint_letter.md, filled only with facts of the case and points
  the supervisor approved. No other legal claims, sections or deadlines.
- dlsa_application: templates/dlsa_application.md filled with facts of the case.
- bundle: all drafts for one supervisor review.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import drafts
import general
import lang
import privacy

HERE = Path(__file__).resolve().parent
TEMPLATES, TEMPLATES_HI = HERE / "templates", HERE / "templates_hi"
DOC_SEPARATOR = "\n\n" + "=" * 60 + "\n\n"
SUGGESTED_FIRST_DAYS, SUGGESTED_FOLLOW_UP_DAYS = 3, 7

# ---------- problem type ----------

TYPE_WORDS = [  # the first match wins: an electricity case that mentions "paid bills" is not a wages case
    ("electricity", ["electric", "bijli", "power cut", "power supply", "meter", "disconnect", "transformer",
                     "lineman", "बिजली"]),
    ("water", ["water supply", "water connection", "tap water", "pani ka", "पानी"]),
    ("ration", ["ration", "pds", "food grain", "rashan", "राशन"]),
    ("wages", ["wage", "salary", "salaries", "contractor", "employer", "mazdoori", "thekedar", "मज़दूरी", "मजदूरी",
               "वेतन"]),
    ("family", ["husband", "wife", "marriage", "divorce", "maintenance", "dowry", "domestic", "in-laws", "पति",
                "दहेज"]),
    ("land", ["land", "plot", "tenant", "landlord", "evict", "boundary", "ज़मीन", "जमीन"]),
]
CATEGORY_TYPES = {"arrest_or_custody": "custody", "online_or_financial_fraud": "fraud",
                  "electricity_or_water": "electricity", "wages_or_work": "wages", "ration_or_welfare": "ration"}
ESSENTIAL = ("electricity", "water")


def problem_type(g: "general.GeneralFacts") -> str:
    for category, _ in g.issues:
        if category in CATEGORY_TYPES:
            t = CATEGORY_TYPES[category]
            if t == "electricity" and _matches(g, dict(TYPE_WORDS)["water"]) and not _matches(g, dict(TYPE_WORDS)["electricity"]):
                return "water"
            return t
    for t, words in TYPE_WORDS:
        if _matches(g, words):
            return t
    return "other"


def _text(g) -> str:
    return " ".join(g.what_happened + [n for _, n in g.issues] + [f"{w} {x}" for w, x in g.timeline]).casefold()


def _matches(g, words) -> bool:
    text = _text(g)
    return any(re.search(rf"(?<!\w){re.escape(w)}", text) for w in words)


# ---------- dates: years and how long ----------

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
HINDI_MONTHS = {"जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
                "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12,
                "दिसम्बर": 12}


def parse_when(text: str, today: date) -> Optional[date]:
    """A date from a timeline entry: "15 March 2024", "March 2024", "June to August 2026" (the start),
    "2024-03-15", "5 weeks ago". None if there is no year (or it can't be read)."""
    t = privacy.normalise_digits((text or "").casefold())
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(\d+)\s*(day|days|week|weeks|month|months|year|years)\s*(ago|पहले)", t)
    if m:
        n, unit = int(m[1]), m[2]
        days = n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit.rstrip("s")]
        return today - timedelta(days=days)
    year = re.search(r"\b(19|20)\d{2}\b", t)
    if not year:
        return None
    words = re.findall(r"[a-z]+|[ऀ-ॿ]+", t)
    month = next((MONTHS.get(w) or HINDI_MONTHS.get(w) for w in words if (MONTHS.get(w) or HINDI_MONTHS.get(w))), 1)
    day = re.search(r"\b(\d{1,2})\b", t[:year.start()])
    try:
        return date(int(year[0]), month, int(day[1]) if day and int(day[1]) <= 31 else 1)
    except ValueError:
        return date(int(year[0]), month, 1)


def missing_years(g) -> List[Tuple[str, str]]:
    """Timeline entries whose date has no year (and isn't "5 days ago" style): [(when, what)]."""
    out = []
    for when, what in g.timeline + g.coming_dates:
        if when and when != "date not given" and parse_when(when, date.today()) is None \
                and not general.RELATIVE_WHEN.search(when):
            out.append((when, what))
    return out


def duration(g, today: date, code: str = "en") -> Optional[str]:
    """"about 5 weeks" from the first dated past event; None if no event has a year."""
    starts = [d for d in (parse_when(w, today) for w, _ in g.timeline) if d and d <= today]
    if not starts:
        return None
    days = (today - min(starts)).days
    if days < 14:
        n, unit = max(days, 1), "day"
    elif days < 90:
        n, unit = round(days / 7), "week"
    elif days < 730:
        n, unit = round(days / 30), "month"
    else:
        n, unit = round(days / 365), "year"
    return lang.t(f"cw.about_{unit}{'' if n == 1 else 's'}", code, n=n)


NUMBER_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "ek": 1, "do": 2, "teen": 3, "tin": 3,
                "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "saat": 7, "aath": 8, "nau": 9,
                "das": 10, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "सात": 7, "आठ": 8,
                "नौ": 9, "दस": 10}
UNITS = {"day": "day", "days": "day", "din": "day", "दिन": "day", "week": "week", "weeks": "week", "hafte": "week",
         "hafta": "week", "हफ़्ते": "week", "हफ्ते": "week", "हफ़्ता": "week", "सप्ताह": "week", "month": "month",
         "months": "month", "mahine": "month", "mahina": "month", "maheene": "month", "महीने": "month", "महीना": "month",
         "year": "year", "years": "year", "saal": "year", "साल": "year", "वर्ष": "year"}
STATED = re.compile(r"(?<![\w\u0900-\u097F])(\d{1,2}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) +
                    r")[\s-]+(" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")(?![\w\u0900-\u097F])", re.I)


def stated_period(g) -> Optional[Tuple[int, str]]:
    """A length of time the story itself states ("not paid for three months", "teen mahine se"):
    (3, "month"). None if the story states none. Relative dates ("5 weeks ago") are not periods."""
    for line in g.what_happened + [n for _, n in g.issues]:
        for m in STATED.finditer(privacy.normalise_digits(line)):
            after = line[m.end():m.end() + 6].casefold()
            if "ago" in after or "पहले" in after or "pehle" in after:
                continue
            word = m.group(1).casefold()
            n = int(word) if word.isdigit() else NUMBER_WORDS.get(word)
            if n:
                return n, UNITS[m.group(2).casefold()]
    return None


def duration_text(g, today: date, code: str = "en") -> Optional[str]:
    """"Going on for", matching the facts: the period the story states (if any) and the first dated
    event, for example "3 months, as the story says; salary stopped on 30 September 2026". Without a
    stated period: "about 5 weeks (since 1 October 2026: connection cut)". None if neither is known."""
    stated = stated_period(g)
    dated = sorted(((d, w, x) for w, x in g.timeline for d in [parse_when(w, today)] if d and d <= today),
                   key=lambda v: v[0])
    anchor = dated[0] if dated else None
    parts = []
    if stated:
        n, unit = stated
        parts.append(lang.t("cw.dur_stated", code, period=lang.t(f"cw.n_{unit}{'' if n == 1 else 's'}", code, n=n)))
    if anchor:
        _, when, what = anchor
        what = what[:1].lower() + what[1:] if code == "en" and what[:2] != what[:2].upper() else what
        if stated:
            parts.append(lang.t("cw.dur_event", code, what=what.rstrip("."), when=when))
        else:
            parts.append(lang.t("cw.dur_since", code, about=duration(g, today, code), what=what.rstrip("."), when=when))
    return "; ".join(parts) or None


# ---------- urgency (fixed rules) ----------

@dataclass
class Urgency:
    level: str          # "call" (112 / 1930), "urgent" (act this week), "normal"
    reasons: List[str]  # message keys with params, already in the language


def urgency(g, today: date, code: str = "en") -> Urgency:
    def t(key, **p):
        return lang.t(key, code, **p)
    f = g.facts
    calls = general.urgent_actions(f, g.precautions)
    reasons = [t("safety.call112") if a == general.CALL_112 else t("safety.call1930") for a in calls]
    level = "call" if calls else "normal"
    if f.get("in_custody") is True:
        reasons.append(t("cw.urgent_custody"))
    if f.get("essential_service_cut") is True:
        reasons.append(t("cw.urgent_service", what=t(f"cw.service.{problem_type(g) if problem_type(g) in ESSENTIAL else 'electricity'}")))
    for when, what in g.coming_dates:
        d = parse_when(when, today)
        if d and today <= d <= today + timedelta(days=14):
            reasons.append(t("cw.urgent_date", what=what, date=lang.show_date(d, code)))
    if level == "normal" and reasons:
        level = "urgent"
    if not reasons:
        reasons.append(t("cw.not_urgent"))
    return Urgency(level, reasons)


# ---------- documents that fit the problem ----------

DOCUMENTS_BY_TYPE = {
    "electricity": ["cw.doc.bill", "cw.doc.receipts", "cw.doc.notice", "cw.doc.complaint_numbers"],
    "water": ["cw.doc.water_bill", "cw.doc.receipts", "cw.doc.notice", "cw.doc.complaint_numbers"],
    "ration": ["cw.doc.ration_receipt", "cw.doc.refusal", "cw.doc.family_list"],
    "wages": ["cw.doc.appointment", "cw.doc.payslips", "cw.doc.attendance", "cw.doc.bank", "cw.doc.messages_employer"],
    "family": ["cw.doc.marriage", "cw.doc.birth", "cw.doc.medical", "cw.doc.messages", "cw.doc.notices"],
    "land": ["cw.doc.ownership", "cw.doc.tax", "cw.doc.notices"],
    "other": ["cw.doc.papers", "cw.doc.notices"],
}
HAS_REFERENCE_NUMBER = ("electricity", "water", "ration")  # the person may have a consumer / application number


def documents_needed(g, approved: List[dict], code: str = "en") -> Tuple[List[str], str]:
    """(documents usually needed, where the list comes from). Approved research points of kind
    "documents" first; otherwise our files (custody, fraud) or the plain list for the problem type."""
    points = [p for p in approved if p.get("kind") == "documents"]
    if points:
        return [p["text"] for p in points], "research"
    t = problem_type(g)
    if t in ("custody", "fraud"):
        cat = "arrest_or_custody" if t == "custody" else "online_or_financial_fraud"
        lists = general.document_lists([cat], g.documents_held, g.what_happened)
        return lists[0][1], "files"
    items = [lang.t(k, code) for k in DOCUMENTS_BY_TYPE.get(t, DOCUMENTS_BY_TYPE["other"])]
    words = set(re.findall(r"[a-z]+", _text(g)))
    if words & set(general.POLICE_OR_COURT_WORDS):  # FIR and court papers only if police or a court are mentioned
        items += [lang.t("cw.doc.fir", code), lang.t("cw.doc.court_orders", code)]
    items += [lang.t("cw.doc.id", code), lang.t("cw.doc.income", code)]
    return general._not_held(items, g.documents_held), "plain"


# ---------- for the lawyer ----------

def lawyer_flags(g, code: str = "en") -> List[str]:
    out = []
    if g.facts.get("unofficial_payment_demand") is True:
        quote = (g.evidence or {}).get("unofficial_payment_demand", "")
        out.append(lang.t("cw.flag_payment", code, quote=quote) if quote else lang.t("cw.flag_payment_noquote", code))
    return out


# ---------- next steps: specific first, with dates ----------

@dataclass
class Step:
    text: str
    due: Optional[date] = None
    suggested: bool = False   # a suggested follow-up date, not a legal deadline
    source: str = ""          # Source line (our files or an approved research point)


def next_steps(g, eligibility, approved: List[dict], research_state: str, today: date,
               code: str = "en") -> List[Step]:
    """research_state: "none" (covered by our files), "waiting", "failed", "approved"."""
    def t(key, **p):
        return lang.t(key, code, **p)
    steps: List[Step] = []
    if g.facts.get("danger_now") is True:
        steps.append(Step(t("safety.call112")))
    if general.CALL_1930 in general.urgent_actions(g.facts, g.precautions):
        steps.append(Step(t("safety.call1930")))
    kind = problem_type(g)
    if kind == "custody":
        e = general.knowledge.get("undertrial_bail.md", "Who to approach for an undertrial")
        steps.append(Step(t("cw.step_custody"), today, False, e.source_line))
    if kind == "fraud":
        e = general.knowledge.get("cyber_fraud.md", "Stop further loss straight away")
        steps.append(Step(t("cw.step_fraud"), today, False, e.source_line))
    routes = [p for p in approved if p.get("kind") in ("route", "how_to_file")]
    for n, p in enumerate(routes):
        due = today + timedelta(days=SUGGESTED_FIRST_DAYS) if n == 0 else None
        steps.append(Step(p["text"], due, n == 0, _source_line(p)))
    for p in [p for p in approved if p.get("kind") == "time_limit"]:
        steps.append(Step(p["text"], None, False, _source_line(p)))
    if kind not in ("custody", "fraud") and not routes:
        steps.append(Step(t("cw.step_waiting") if research_state == "waiting" else t("cw.step_research_failed")
                          if research_state == "failed" else t("cw.step_no_research")))
    if eligibility.status == "eligible":
        steps.append(Step(t("cw.step_dlsa"), today + timedelta(days=SUGGESTED_FOLLOW_UP_DAYS), True,
                          eligibility.sources[0] if eligibility.sources else ""))
    elif eligibility.status == "not decided yet":
        steps.append(Step(t("cw.step_eligibility")))
    docs, _ = documents_needed(g, approved, code)
    if docs:
        steps.append(Step(t("cw.step_documents"), today + timedelta(days=SUGGESTED_FOLLOW_UP_DAYS), True))
    steps.append(Step(t("cw.step_supervisor")))
    return steps


def _source_line(p: dict) -> str:
    if p.get("source_line"):
        return p["source_line"]
    return "Source: " + "; ".join(f"{s['title']} ({s['url']})" for s in p.get("sources", []))


# ---------- the letters (only facts of the case and approved points) ----------

def _template(name: str, code: str) -> str:
    if code == "hi":
        lines = (TEMPLATES_HI / name).read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[1:]) + "\n"  # without the "translation checked" marker
    return (TEMPLATES / name).read_text(encoding="utf-8")


LETTER_BLANKS = {
    "en": {"subject": "[subject]", "problem": "[problem]", "facts": "[facts]", "documents": "[documents]",
           "reference": "[reference number]", "request": "[request]", "route": "[route]", "basis": "[basis]"},
    "hi": {"subject": "[विषय]", "problem": "[समस्या]", "facts": "[तथ्य]", "documents": "[काग़ज़]",
           "reference": "[संदर्भ संख्या]", "request": "[अनुरोध]", "route": "[कहाँ भेजें]", "basis": "[आधार]"},
}


def complaint_letter(g, approved: List[dict], issue: str, ai_model: Optional[str], code: str = "en") -> str:
    """The complaint letter. Its body holds only facts of the case (what happened, dates, documents
    the person has, what they want); where to send it and the legal basis are only the research points
    given: the volunteer's ticked points (marked "AI research, not yet checked by a lawyer") until the
    supervisor decides, then only the supervisor's approved points. Blanks for name, address and numbers."""
    def t(key, **p):
        return lang.t(key, code, **p)
    b = LETTER_BLANKS[code]
    kind = problem_type(g)
    facts = [f"- {s}" for s in g.what_happened] + [f"- {w}: {x}" for w, x in g.timeline]
    routes = [p for p in approved if p.get("kind") in ("route", "how_to_file")]
    basis = [f"- {p['text']} ({_source_line(p)}; " + (t("cw.not_checked_yet") if p.get("unchecked") else
                                                     t("cw.approved_on", date=p.get("approved_on", ""))) + ")"
             for p in approved if p.get("kind") != "letter"]
    reference = t(f"cw.ref.{kind}") if kind in HAS_REFERENCE_NUMBER else ""
    held = t("cw.letter_documents", docs="; ".join(g.documents_held)) if g.documents_held else ""
    text = drafts.fill(_template("complaint_letter.md", code), [
        (b["subject"], t("cw.letter_subject", problem=issue)),
        (b["problem"], issue),
        (b["facts"], "\n".join(facts) or t("cw.letter_no_facts")),
        (b["documents"], held),
        (b["reference"], reference),
        (b["request"], g.outcome or t("cw.letter_request_blank")),
        (b["route"], routes[0]["text"] if routes else t("cw.letter_route_blank")),
        (b["basis"], "\n".join(basis) or t("cw.letter_no_basis")),
    ])
    text = re.sub(r"\n{3,}", "\n\n", text)
    return drafts.add_disclosure(text, ai_model, rules=general.RULES_USED, code=code)


def dlsa_application(g, eligibility, issue: str, ai_model: Optional[str], code: str = "en") -> str:
    """The free legal aid application (templates/dlsa_application.md), filled with facts of the case.
    Name, address and phone stay as blanks to fill by hand."""
    group = next((lang.t(f"group.{key}", code) for key, _ in general.GROUPS if g.facts.get(key) is True), None)
    income = g.facts.get("annual_income")
    statement = " ".join(g.what_happened)[:700]
    if code == "hi":
        rep = [("[हाँ — बताएँ: महिला / बच्चा / अनुसूचित जाति / अनुसूचित जनजाति / दिव्यांग व्यक्ति / हिरासत में व्यक्ति / "
                "औद्योगिक कामगार / मानव तस्करी या आपदा का शिकार] [नहीं]", f"हाँ — {group}" if group else
                "[हाँ — बताएँ] [नहीं]"),
               ("[₹ ___]", f"लगभग ₹{int(income) // 12:,}" if income is not None else "[पुष्टि होनी है]"),
               ("[जैसे धारा 479 BNSS के तहत रिहाई का आवेदन करने के लिए वकील / रोके गए पैसे छुड़ाने के लिए वकील / "
                "क़ानूनी सलाह]", f"क़ानूनी सलाह और मदद: {issue}"),
               ("[दो से पाँच वाक्य: क्या हुआ, कब, कौन सी अदालत या थाना, केस या FIR नंबर, आवेदक को अभी क्या चाहिए।]",
                statement or "[दो से पाँच वाक्य]"),
               ("[FIR की कॉपी / अदालत का आदेश / चार्जशीट / बैंक के पत्र / शिकायत की पावती / पहचान पत्र]",
                "; ".join(g.documents_held) or "[काग़ज़ों की सूची]")]
    else:
        rep = [("[Yes — specify: woman / child / SC / ST / person with disability / person in custody / industrial "
                "workman / victim of trafficking or disaster] [No]", f"Yes — {group}" if group else
                "[Yes — specify] [No]"),
               ("[₹ ___]", f"about ₹{int(income) // 12:,}" if income is not None else "[to be confirmed]"),
               ("[e.g. a lawyer to apply for release under Section 479 BNSS / a lawyer to apply for release of frozen "
                "money / legal advice]", f"legal advice and help with: {issue}"),
               ("[Two to five sentences: what happened, when, which court or police station, case or FIR number, "
                "what the applicant needs now.]", (statement + (f" The applicant wants: {g.outcome}." if g.outcome
                                                               else "")) or "[Two to five sentences]"),
               ("[FIR copy / court order / chargesheet / bank letters / complaint acknowledgement / identity proof]",
                "; ".join(g.documents_held) or "[list of documents]")]
    if code == "hi":
        return drafts.add_disclosure(drafts.fill(_template("dlsa_application.md", "hi"), rep), ai_model,
                                     rules=general.RULES_USED, code="hi")
    return drafts.add_disclosure(drafts.fill(_template("dlsa_application.md", "en"), rep), ai_model,
                                 rules=general.RULES_USED)


def bundle(documents: List[Tuple[str, str]]) -> str:
    """[(title, text)] -> one text for the supervisor's review (each document starts with the DRAFT line)."""
    return DOC_SEPARATOR.join(text.strip() + "\n" for _, text in documents)


def split_bundle(text: str) -> List[str]:
    return [part for part in text.split(DOC_SEPARATOR.strip()) if part.strip()]


# ---------- what may appear in a letter (used by the test) ----------

LEGAL_CLAIM = re.compile(r"\b(section|sec\.|article|act|rule|regulation|clause)\s*\d|\b(IPC|BNS|BNSS|CrPC)\b|"
                         r"\bwithin\s+\d+\s*(day|days|week|weeks|month|months)\b", re.I)


def legal_claims(text: str) -> List[str]:
    return [m.group(0) for m in LEGAL_CLAIM.finditer(text)]
