"""Step 3, "Draft and research", with four practice cases (no AI, no internet):
1. electricity cut in Bihar (5 weeks, bills paid, an unofficial payment demanded)
2. ration card refused in Uttar Pradesh
3. unpaid wages in Maharashtra
4. the undertrial practice case (IPC 380), covered by our files.
Practice data only."""

import re
from datetime import date

import pytest

import casework
import general
import knowledge
import official
import readiness

TODAY = date(2026, 11, 5)
BIHAR_POINTS = [
    {"kind": "route", "text": "Write first to the Assistant Engineer of the electricity supply sub-division.",
     "sources": [{"title": "energy.bihar.gov.in", "url": "https://energy.bihar.gov.in/complaints"}],
     "approved_on": "2026-11-05"},
    {"kind": "route", "text": "If there is no reply, complain to the Consumer Grievance Redressal Forum.",
     "sources": [{"title": "berc.co.in", "url": "https://berc.co.in/consumer-corner/cgrf"}], "approved_on": "2026-11-05"},
    {"kind": "documents", "text": "The latest bill, payment receipts and any disconnection notice.",
     "sources": [{"title": "sbpdcl.co.in", "url": "https://www.sbpdcl.co.in/"}], "approved_on": "2026-11-05"},
]
UP_POINTS = [{"kind": "route", "text": "Apply to the District Supply Officer.",
              "sources": [{"title": "fcs.up.gov.in", "url": "https://fcs.up.gov.in/"}], "approved_on": "2026-11-05"}]


def case(**kw) -> general.GeneralFacts:
    base = dict(person="the person seeking help", what_happened=[], timeline=[], coming_dates=[], issues=[],
                sections=[], documents_held=[], answers=[], still_to_ask=[], facts={}, today=TODAY.isoformat())
    base.update(kw)
    return general.GeneralFacts(**base)


ELECTRICITY = case(
    person="a woman living with her two children",
    what_happened=["The electricity connection was cut although every bill was paid.",
                   "The lineman asked for an extra payment to restore the line."],
    timeline=[("1 October 2026", "connection cut"), ("15 October", "first visit to the electricity office")],
    issues=[("electricity_or_water", "electricity connection cut")], documents_held=["latest bill", "payment receipts"],
    facts={"state": "Bihar", "woman": True, "essential_service_cut": True, "unofficial_payment_demand": True,
           "annual_income": 72000},
    outcome="the connection restored and no extra payment",
    evidence={"unofficial_payment_demand": "only if she paid \"kharcha-pani\" of Rs 2,000"})
RATION = case(person="a widow", what_happened=["Her ration card application was refused without a reason."],
              timeline=[("June 2026", "applied for a ration card")], issues=[("ration_or_welfare", "ration card refused")],
              facts={"state": "Uttar Pradesh", "woman": True}, outcome="a ration card")
WAGES = case(person="a construction worker", what_happened=["He was not paid wages from June to August 2026."],
             timeline=[("June to August 2026", "worked without pay")], issues=[("wages_or_work", "unpaid wages")],
             documents_held=["photos of the attendance register"], facts={"state": "Maharashtra", "annual_income": 120000,
                                                                          "woman": False, "in_custody": False})
UNDERTRIAL = case(person="the speaker's brother, an undertrial prisoner",
                  what_happened=["The brother was arrested on 15 March 2024 and is charged under IPC 380."],
                  timeline=[("15 March 2024", "arrested")], issues=[("arrest_or_custody", "arrest and bail")],
                  facts={"in_custody": True, "state": "Bihar"}, outcome="to get him out of jail")


# ---------- 1. electricity cut, Bihar ----------

def test_electricity_at_a_glance_urgency_and_duration():
    assert casework.problem_type(ELECTRICITY) == "electricity"
    u = casework.urgency(ELECTRICITY, TODAY)
    assert u.level == "urgent" and "electricity is cut off now" in " ".join(u.reasons)
    assert casework.duration(ELECTRICITY, TODAY) == "about 5 weeks"
    assert casework.missing_years(ELECTRICITY) == [("15 October", "first visit to the electricity office")]


def test_electricity_documents_fit_the_problem():
    docs, origin = casework.documents_needed(ELECTRICITY, [])
    assert origin == "plain" and "Disconnection notice, if one was given" in docs
    assert not any("Pay slips" in d or "FIR" in d for d in docs)
    assert "Latest electricity bill" not in docs  # she has it ("latest bill")
    approved, origin = casework.documents_needed(ELECTRICITY, BIHAR_POINTS)
    assert origin == "research" and approved == ["The latest bill, payment receipts and any disconnection notice."]


def test_unofficial_payment_is_flagged_for_the_lawyer_with_the_quote():
    [flag] = casework.lawyer_flags(ELECTRICITY)
    assert "unofficial payment" in flag and "kharcha-pani" in flag and "no judgement" in flag
    assert casework.lawyer_flags(RATION) == []


def test_electricity_next_steps_follow_the_approved_route_with_dates():
    e = general.check_eligibility(ELECTRICITY.facts)
    steps = casework.next_steps(ELECTRICITY, e, BIHAR_POINTS, "approved", TODAY)
    texts = [s.text for s in steps]
    assert texts[0] == BIHAR_POINTS[0]["text"] and steps[0].due == date(2026, 11, 8) and steps[0].suggested
    assert texts[1] == BIHAR_POINTS[1]["text"]
    assert "energy.bihar.gov.in" in steps[0].source
    assert any("DLSA" in x for x in texts) and texts.index(BIHAR_POINTS[0]["text"]) < [
        i for i, x in enumerate(texts) if "DLSA" in x][0]  # specific steps before general help
    waiting = [s.text for s in casework.next_steps(ELECTRICITY, e, [], "waiting", TODAY)]
    assert any("the supervisor checks every point" in x for x in waiting)


def test_electricity_checklist_has_no_custody_and_records_only_yes_no_for_the_number():
    e = general.check_eligibility(ELECTRICITY.facts)
    items = readiness.case_items(ELECTRICITY, e, "electricity", casework.missing_years(ELECTRICITY))
    keys = [i.key for i in items]
    assert "case_reference" in keys and "case_custody" not in keys and "case_danger" not in keys
    assert {i.key: i.status for i in items}["case_dates"] == readiness.MISSING
    assert readiness.FIXES["case_reference"] == "yesno"  # the consumer number itself is never typed


# ---------- letters: only facts of the case and approved points ----------

def allowed_claims(points):
    return {c.casefold() for p in points for c in casework.legal_claims(p["text"])}


@pytest.mark.parametrize("g, points, issue", [
    (ELECTRICITY, BIHAR_POINTS, "electricity connection cut"),
    (RATION, UP_POINTS, "ration card refused"),
])
@pytest.mark.parametrize("code", ["en", "hi"])
def test_letters_use_only_case_facts_and_approved_points(g, points, issue, code):
    letter = casework.complaint_letter(g, points, issue, "gemini-test", code)
    assert letter.startswith("DRAFT — to be checked by a lawyer")
    body, volunteer_part = re.split(r"\n---\n", letter, maxsplit=1)
    # The letter's body: no legal claims, sections or deadlines at all
    assert casework.legal_claims(body) == [], casework.legal_claims(body)
    # Facts in the body come from the case
    for line in g.what_happened:
        assert line in body
    # Anything legal in the whole letter is in an approved point
    assert {c.casefold() for c in casework.legal_claims(letter)} <= allowed_claims(points) | {
        c.casefold() for c in casework.legal_claims(volunteer_part.split("How this draft was prepared")[-1])}
    for p in points:
        if p["kind"] != "letter":
            assert p["text"] in volunteer_part
    # Blanks stay blank: no names, addresses or numbers
    blank = "[Name of the person]" if code == "en" else "[व्यक्ति का नाम]"
    assert blank in body
    if casework.problem_type(g) == "electricity":
        assert ("[Consumer number]" if code == "en" else "[उपभोक्ता संख्या]") in body


def test_a_point_not_approved_never_reaches_the_letter():
    letter = casework.complaint_letter(ELECTRICITY, BIHAR_POINTS[:1], "electricity connection cut", None)
    assert "Consumer Grievance Redressal Forum" not in letter


def test_hindi_letter_is_in_hindi_with_the_draft_line():
    letter = casework.complaint_letter(ELECTRICITY, BIHAR_POINTS, "बिजली का कनेक्शन कटा", None, "hi")
    assert letter.startswith("DRAFT — to be checked by a lawyer\nड्राफ़्ट — वकील से जाँच करवाना ज़रूरी है")
    assert "सेवा में" in letter and "व्यक्ति का अनुरोध है" in letter and "यह ड्राफ़्ट कैसे बना" in letter


def test_dlsa_application_filled_from_the_case_in_both_languages():
    e = general.check_eligibility(ELECTRICITY.facts)
    en = casework.dlsa_application(ELECTRICITY, e, "electricity connection cut", None)
    assert "Yes — a woman" in en and "about ₹6,000" in en and "The applicant wants: the connection restored" in en
    assert "[to be filled by hand at the DLSA — not stored in the app]" in en
    hi = casework.dlsa_application(ELECTRICITY, e, "बिजली का कनेक्शन कटा", None, "hi")
    assert "हाँ — महिला" in hi and "लगभग ₹6,000" in hi


# ---------- 2. ration card, Uttar Pradesh ----------

def test_ration_card_case():
    assert casework.problem_type(RATION) == "ration"
    docs, _ = casework.documents_needed(RATION, [])
    assert "Ration card application receipt" in docs and not any("bill" in d.casefold() for d in docs)
    assert casework.urgency(RATION, TODAY).level == "normal"
    assert casework.duration(RATION, TODAY) == "about 5 months"
    letter = casework.complaint_letter(RATION, UP_POINTS, "ration card refused", None)
    assert "District Supply Officer" in letter and "[Application number]" in letter


# ---------- 3. unpaid wages, Maharashtra ----------

def test_wages_case():
    assert casework.problem_type(WAGES) == "wages"
    docs, _ = casework.documents_needed(WAGES, [])
    assert "Pay slips" in docs and not any("electricity" in d.casefold() for d in docs)
    assert casework.duration(WAGES, TODAY) == "about 5 months"
    e = general.check_eligibility(WAGES.facts)
    keys = [i.key for i in readiness.case_items(WAGES, e, "wages", [])]
    assert "case_custody" not in keys and "case_reference" not in keys
    steps = [s.text for s in casework.next_steps(WAGES, e, [], "failed", TODAY)]
    assert any("15100" in x for x in steps)


# ---------- 4. undertrial (covered by our files: no research) ----------

def test_undertrial_case_uses_our_files():
    assert casework.problem_type(UNDERTRIAL) == "custody"
    u = casework.urgency(UNDERTRIAL, TODAY)
    assert u.level == "urgent" and "custody" in " ".join(u.reasons)
    assert general.uncovered_issues(UNDERTRIAL) == []  # no research needed
    e = general.check_eligibility(UNDERTRIAL.facts)
    steps = casework.next_steps(UNDERTRIAL, e, [], "none", TODAY)
    assert "Section 479" in steps[0].text and "undertrial_bail" not in steps[0].source
    assert knowledge.get("undertrial_bail.md", "Who to approach for an undertrial").source in steps[0].source
    keys = [i.key for i in readiness.case_items(UNDERTRIAL, e, "custody", [])]
    assert "case_custody" in keys and "case_reference" not in keys


# ---------- the summary: person, internal notes, sources ----------

def test_summary_says_not_stated_instead_of_a_placeholder_person():
    g = case(person="", what_happened=["x"], issues=[("other", "a problem")], facts={"state": "Bihar"})
    assert "Person needing help: Not stated (ask who needs the help)" in general.summary_body(g)
    raw = {"person_needing_help": "the person seeking help"}
    assert general.check_general_answer(raw, "notes").person == ""


def test_no_internal_notes_and_every_source_official_or_marked():
    g = ELECTRICITY
    g.research = [{"issue": "electricity connection cut", "origin": "research", "kind": "route",
                   "heading": "Route", "text": BIHAR_POINTS[0]["text"],
                   "source_line": "Source: energy.bihar.gov.in (https://energy.bihar.gov.in/complaints)",
                   "approved_on": "2026-11-05"}]
    text = general.summary_body(g) + casework.complaint_letter(g, BIHAR_POINTS, "electricity connection cut", None)
    assert "Confirmed on" not in text
    for line in text.splitlines():
        for url in re.findall(r"https?://[^\s)]+", line):
            assert official.allowed_link(url) or official.SECONDARY in line, line


def test_summary_has_the_new_sections():
    text = general.summary_body(ELECTRICITY)
    for heading in ("For the clinic file (not to be given out)", "At a glance", "- Problem: electricity connection cut",
                    "- Going on for: about 5 weeks", "Urgent: the electricity is cut off now", "What happened",
                    "What the person wants", "Timeline", "Documents", "Free legal aid", "Questions for the lawyer",
                    "Next steps"):
        assert heading in text, heading


def test_urgent_section_agrees_with_at_a_glance():
    text = general.summary_body(ELECTRICITY)
    urgent = text.split("Urgency: ")[1].split("\n")[0]       # said once, at a glance
    assert "electricity is cut off now" in urgent and "Nothing urgent" not in text and "URGENT\n" not in text
    assert "बिजली का कनेक्शन अभी कटा हुआ है" in general.summary_body_hi(ELECTRICITY)


def test_letter_card_keeps_lines_as_written():
    import ui
    page = ui.letter_html("DRAFT — to be checked by a lawyer\n\n- one fact\n- another <b>")
    assert "\n" not in page and "- one fact<br>- another &lt;b&gt;" in page


def test_knowledge_links_are_official_except_the_three_kept_as_secondary():
    knowledge._entries.cache_clear()
    secondary = sorted(e.heading for f in ("legal_aid_eligibility.md", "undertrial_bail.md", "cyber_fraud.md",
                                           "helplines.md")
                       for e in knowledge.entries(f) if not e.official)
    assert secondary == ['"Digital arrest" calls are always fraud', "Bail granted but still in jail",
                         "Getting held money back usually needs a court order"]
    assert "casemine" not in (knowledge.HERE / "templates" / "dlsa_application.md").read_text(encoding="utf-8")
    assert "?locale=hi" not in knowledge.all_text()
