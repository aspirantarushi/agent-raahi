"""Final fixes A (13 November 2026): one test per bug from Arushi's full-flow test. Fake data only."""

import json
import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import casework
import drafts
import general
import lang
import ledger
import llm
import readiness
import research
import section479
import store
import tracker
from test_new_case_fixes import facts as make_facts

ROOT = Path(__file__).resolve().parent.parent


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


# ---------- 1. "Going on for" never uses the person's age ----------

@pytest.mark.parametrize("line, period", [
    ("Ek 62 saal ki vidhwa aurat ka bijli connection kata.", None),
    ("A 62-year-old widowed woman says the power was cut.", None),
    ("The woman, aged 45 years, was not paid.", None),
    ("उम्र 60 साल, पेंशन बंद हो गई।", None),
    ("Malik ne teen mahine se paisa nahi diya.", (3, "month")),
    ("The worker was not paid for three months.", (3, "month")),
])
def test_an_age_is_not_a_period(line, period):
    assert casework.stated_period(make_facts(what_happened=[line], issues=[])) == period


# ---------- 2. answers reach the summary: what each question fills ----------

def test_each_question_records_what_its_answer_fills():
    assert general.fills("What outcome do you want from this case?") == "outcome"
    assert general.fills("Do you have a copy of the electricity connection agreement or account number?") == "reference"
    assert general.fills("When did the employer stop paying?") == "date"
    raw = {"questions_to_ask": ["What outcome does the person want from this case?"]}
    reading = general.check_general_answer(raw, "Practice notes.")
    assert reading.question_fills["What outcome does the person want from this case?"] == "outcome"


def test_answers_fill_the_outcome_and_the_consumer_number():
    g = make_facts(outcome="", facts={"state": "Bihar"}, answers=[
        ("What outcome do you want from this case?", "Full payment of unpaid wages for August and September 2026"),
        ("Do you have a copy of the electricity connection agreement or account number?", "Yes")])
    g = general.apply_answers(g)
    assert g.outcome == "Full payment of unpaid wages for August and September 2026"
    assert g.facts["has_reference_number"] is True
    items = readiness.case_items(g, general.check_eligibility(g.facts), "electricity", [])
    assert next(i for i in items if i.key == "case_reference").status == readiness.PRESENT
    assert next(i for i in items if i.key == "case_outcome").status == readiness.PRESENT


# ---------- 3. the notes' own words never become the plain-words version ----------

def test_untranslated_wants_are_not_used_and_the_quote_stays_for_the_ledger():
    notes = "Bijli kaat di gayi. Woh chahti hai ki bijli turant wapas jode aur galat bill theek ho."
    raw = {"outcome_wanted": {"value": "bijli turant wapas jode aur galat bill theek ho",
                              "quote": "bijli turant wapas jode aur galat bill theek ho"}}
    reading = general.check_general_answer(raw, notes)
    assert reading.outcome == ""                                     # never in an English draft
    assert reading.evidence["outcome"] == "bijli turant wapas jode aur galat bill theek ho"
    assert lang.t("q.outcome") in reading.questions                  # so it is asked in plain words
    good = general.check_general_answer({"outcome_wanted": {"value": "The electricity reconnected",
                                                            "quote": "bijli turant wapas jode"}}, notes)
    assert good.outcome == "The electricity reconnected"
    g = make_facts(outcome="The electricity reconnected", evidence={"outcome": "bijli turant wapas jode"})
    [entry] = [e for e in ledger.general(g, {}, general.check_eligibility(g.facts)) if e.fact == "ledger.outcome"]
    assert entry.value == "The electricity reconnected" and "bijli turant wapas jode" in entry.source_line


def test_the_payment_demand_quote_has_its_english_meaning_in_an_english_draft():
    g = make_facts(facts={"state": "Bihar", "unofficial_payment_demand": True},
                   evidence={"unofficial_payment_demand": "2000 rupaye kharcha-pani do",
                             "unofficial_payment_demand_en": "Rs 2,000 to reconnect the electricity"})
    [flag] = [f for f in casework.lawyer_flags(g, "en") if "unofficial payment" in f]
    assert "“2000 rupaye kharcha-pani do” (Rs 2,000 to reconnect the electricity)" in flag


# ---------- 4. re-reading an edited story replaces, it doesn't merge ----------

def test_re_read_replaces_the_facts_and_keeps_only_answers_that_still_apply(tmp_path):
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    tracker.add_summary(case_id, ["The worker was not paid wages for August and September 2026."], [], [], "Volunteer A",
                        base=tmp_path)
    reading = general.GeneralReading(what_happened=[
        "Wages for August, September, and October 2026 were not paid by the contractor.",
        "Wages for August, September and October 2026 were not paid by the contractor."], outcome="all the wages paid")
    kept = general.answers_still_apply([("What outcome do you want?", "His wages"),
                                        ("Were other workers also not paid?", "Yes")], reading)
    assert kept == [("Were other workers also not paid?", "Yes")]   # the new story says what he wants
    tracker.replace_summary(case_id, reading.what_happened, [], [], kept, "Volunteer A", base=tmp_path)
    record = tracker.load(case_id, base=tmp_path)
    assert record["summary"] == ["Wages for August, September, and October 2026 were not paid by the contractor."]
    assert general.dedupe_timeline([("1 October 2026", "Electricity connection cut"),
                                    ("1 October 2026", "Electricity connection cut by the department"),
                                    ("5 October 2026", "Bill paid")]) == \
        [("1 October 2026", "Electricity connection cut by the department"), ("5 October 2026", "Bill paid")]


def test_story_changed_notice(monkeypatch):
    from test_general import MODEL, WAGES, WAGES_ANSWER
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: llm.NotesReading(WAGES_ANSWER, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(WAGES).run()
    at.button(key="g-read").click().run()
    assert not any("The story changed" in w.value for w in at.warning)
    at.text_area(key="g_notes").set_value(WAGES + " Wages for October 2026 are also unpaid.").run()
    ok(at)
    assert any(w.value == "The story changed: press Read the story again." for w in at.warning)


# ---------- 5. questions ----------

def test_question_rules():
    assert general.person_not_you("Do you have any written contract?") == "Does the person have any written contract?"
    assert general.answered_by_notes("Does the person have a written contract?", "There is no written contract.")
    assert not general.answered_by_notes("Does the worker have messages from the contractor?", "No written contract.")
    raw = {"questions_to_ask": ["Do you want the lineman's demand of 2,000 rupees to be waived?",
                                "When was the electricity cut?", "Q3?", "Q4?", "Q5?", "Q6?", "Q7?"],
           "why_asked": ["x", "To assess the strength of evidence for a claim"]}
    r = general.check_general_answer(raw, "The lineman asked for Rs 2,000.")
    assert not any("waived" in q for q in r.questions)
    assert len([q for q in r.questions if q in raw["questions_to_ask"]]) <= 5
    assert not any("strength" in w for w in r.question_reasons.values())
    prompt = llm.GENERAL_PROMPT
    assert "never \"you\"" in prompt and "strength of evidence" in prompt and "waived" in prompt


def test_dont_know_answers_say_so_in_the_checklist(monkeypatch):
    from test_testing_fixes import wages
    from test_general import WAGES_ANSWER, MODEL
    raw = dict(WAGES_ANSWER, questions_to_ask=["Were other workers also not paid?"])
    at = wages(monkeypatch, lambda notes, output_lang="en", **k: llm.NotesReading(raw, notes, {}, MODEL))
    ok(at)
    import html as h
    import re
    why = h.unescape(" ".join(m.value for m in at.markdown if 'class="tick-why"' in m.value))
    assert re.search(r"\d+ questions? marked Don't know: ask at the next visit, or tick if done", why)
    assert "not found yet" not in why.split("marked Don't know")[0][-40:]


# ---------- 6. the complaint letter ----------

POINT = {"kind": "time_limit", "text": "The licensee must serve a written notice fifteen clear days before any "
         "disconnection.", "sources": [{"title": "Bihar Electricity Supply Code, 2007", "url": "https://berc.co.in/code"}],
         "approved_on": "2026-11-12", "approved_by": "Supervisor"}
ROUTE = {"kind": "route", "text": "Write first to the Assistant Engineer of the sub-division.",
         "sources": [{"title": "SBPDCL complaints", "url": "https://sbpdcl.co.in/c"}], "approved_on": "2026-11-12",
         "approved_by": "Supervisor"}


def electricity():
    return make_facts(person="a widow aged 62", outcome="the electricity reconnected and the wrong bill corrected",
                      what_happened=["She has paid every bill on time.", "The electricity connection was cut on 1 October 2026.",
                                     "She wants the electricity reconnected and the bill corrected."],
                      timeline=[("1 October 2026", "Electricity connection cut by the department")],
                      issues=[("electricity_or_water", "electricity connection cut")],
                      documents_held=["paid bill receipts", "consumer number is on her bills (not written here)"],
                      facts={"state": "Bihar", "woman": True, "has_reference_number": True})


def test_letter_is_neutral_third_person_without_repeats_with_rules():
    letter = casework.complaint_letter(electricity(), [dict(POINT, unchecked=True), dict(ROUTE, unchecked=True)],
                                       "electricity connection cut", "gemini-3.5-flash-lite")
    assert letter.startswith(drafts.DRAFT_HEADER)
    assert "This complaint is made by [Name of the person], of [Address]. The facts are:" in letter
    assert "I, [Name of the person]" not in letter and "write to complain about electricity" not in letter
    assert "The person requests: the electricity reconnected and the wrong bill corrected" in letter
    assert "- 1 October 2026: Electricity connection cut" not in letter     # a fact already gives that date
    assert "She wants the electricity reconnected" not in letter            # the request, not a fact
    assert "Documents enclosed: paid bill receipts" in letter and "not written here" not in letter
    assert "Rules that apply:" in letter and "fifteen clear days before any disconnection (Bihar Electricity " \
        "Supply Code, 2007) [to be checked by the supervisor]" in letter
    assert "points kept by the volunteer (each needs the supervisor's approval)" in letter
    assert "Where to send it" not in letter                                  # it would only repeat the route point
    assert "Google Gemini" in letter                                         # the disclosure, plain name
    approved = casework.complaint_letter(electricity(), [POINT, ROUTE], "electricity connection cut", None)
    assert "these points approved by the supervisor:" in approved
    assert "approved by Supervisor on 12 November 2026" in approved and "[to be checked by the supervisor]" not in approved
    none = casework.complaint_letter(electricity(), [], "electricity connection cut", None)
    assert "Rules that apply" not in none and "Where to send it:" in none


# ---------- 7. research ----------

def test_research_drops_the_ai_letter_and_merges_duplicate_points():
    links = [{"url": f"https://bsphcl.co.in/{i}", "title": "t"} for i in range(5)]
    points = [{"kind": "route", "text": "If the officer is unreachable, use the online complaint portals.", "sources": links},
              {"kind": "route", "text": "File complaints at the local office, call centre, or through online grievance portals.",
               "sources": list(reversed(links))},
              {"kind": "time_limit", "text": "Fifteen days' notice.", "sources": links[:1]}]
    merged = research.merge_duplicates([dict(p) for p in points])
    assert len(merged) == 2 and merged[0]["text"].startswith("File complaints at the local office")


def test_summary_and_ledger_say_research_is_waiting():
    g = make_facts(issues=[("electricity_or_water", "electricity connection cut")], research_state="waiting",
                   research_pending=6)
    body = general.summary_body(g)
    assert "Research from official websites: 6 points, listed with the complaint letter, each for the supervisor to " \
           "approve." in body
    assert "Not covered by our verified files yet" not in body and "Research is shown below" not in body
    issue = [e for e in ledger.general(g, {}, general.check_eligibility(g.facts)) if e.fact == "ledger.issue"][0]
    assert issue.source == ledger.RESEARCH and not ledger.unresolved([issue])


# ---------- 8. free legal aid accuracy ----------

def test_section_12_groups_and_documents():
    full = ("Women, children, people in custody, SC/ST members, people with disabilities, industrial workers, and "
            "victims of trafficking or disasters qualify whatever their income.")
    learner = (ROOT / "learner" / "legal_aid.md").read_text(encoding="utf-8")
    assert full + " Others qualify if their income is below their state's limit" in learner
    assert "   Why: " + full in learner
    assert "- " + full in (ROOT / "templates" / "dlsa_application.md").read_text(encoding="utf-8")
    docs, _ = casework.documents_needed(make_facts(facts={"state": "Punjab", "woman": True}), [])
    assert "Self-declaration for free legal aid (no income proof needed: qualifies as a woman)" in docs
    assert not any(d.startswith("Income proof") for d in docs)
    from test_drafts import practice_facts
    facts = practice_facts(lawyer="None")
    result = section479.calculate(facts.to_section479_input()) if hasattr(facts, "to_section479_input") else None
    if result is not None:
        text = drafts.make_undertrial_draft(facts, result)
        assert "bank letters" not in text and "custody warrant" in text


# ---------- 9. supervisor safety and clarity ----------

def test_own_research_locks_every_decision(monkeypatch, tmp_path):
    from test_supervisor_review import supervisor_screen, waiting_case
    case_id, _ = waiting_case(by="Volunteer B")
    monkeypatch.setattr(research, "for_case", lambda cid, base=None: [
        {"id": f"{cid}.r1", "case_id": cid, "status": research.WAITING, "asked_by": "volunteer a", "asked_at": "2026-11-12T10:00",
         "sources_found": 1, "sources_official": 1, "dropped": [], "state": "Bihar", "issue": "x",
         "points": [{"id": "p1", "kind": "route", "text": "Write to the AE.", "sources": [], "status": research.WAITING,
                     "warnings": []}]}])
    at = supervisor_screen(monkeypatch, name=" Volunteer A ")
    assert at.error[0].value == "You sent this draft, so another supervisor must approve it."
    assert at.radio(key=f"rsd-{case_id}.r1-p1").disabled and at.button(key=f"rss-{case_id}.r1-p1").disabled


def test_sent_with_a_reason_and_plain_audit_words():
    items = [readiness.Item("case_documents", readiness.MISSING, readiness.NOT_TICKED)]
    block = readiness.gaps_block(items, reason="practice run: not known")
    assert block.startswith("Sent with 1 item not ticked:") and "NOT READY" not in block
    assert "Sent anyway because: practice run: not known" in block
    assert audit.who_did({"by": "Supervisor", "role": "supervisor"}) == "Supervisor"
    assert lang.t("sup.Edit then Approve") == "Edit then approve"
    assert llm.display_model("groq:openai/gpt-oss-120b") == "Groq (gpt-oss-120b)"
    assert llm.display_model("gemini-3.5-flash-lite") == "Google Gemini"


def test_history_panel_and_agent_card_are_plain(monkeypatch):
    from test_supervisor_review import supervisor_screen, waiting_case
    case_id, _ = waiting_case(by="Volunteer B")
    record = audit.read_record(case_id)
    record.update(model="groq:openai/gpt-oss-120b", ai_read_at="2026-11-12T22:27:05",
                  ai_extracted={"woman": True, "under_18": False}, ai_answers_not_accepted=["called_1930", "in_custody"],
                  entered_by_volunteer=["today"], case_type="General")
    import storage
    storage.write_json("audit", case_id, record)
    audit.add_event(case_id, "approved", "Supervisor", role="supervisor")
    at = supervisor_screen(monkeypatch, name="SK")
    text = " ".join(c.value for c in at.caption)
    assert "Groq (gpt-oss-120b)" in text and "12 November 2026, 22:27" in text
    assert "A woman: yes" in text and "woman = True" not in text
    assert "Left blank (the AI was not sure)" in text and "called_1930" not in text and "today" not in text


def test_save_to_verified_files_is_marked_not_lawyer_checked(tmp_path):
    from test_research import bihar_research, fake_ai  # noqa: F401
    assert lang.t("rs.k_save") == "Save to our verified files"
    assert lang.t("rs.k_lawyer_first").startswith("Only after a lawyer has checked it")


# ---------- 10. volunteer flow ----------

def test_gaya_is_a_district_not_a_name():
    notes = "Ek 62 saal ki vidhwa aurat, Gaya zile ki rehne wali. Bijli kaat di gayi."
    assert general.possible_names("The woman lives in Gaya district.", notes, "Bihar") == []
    assert general.names_in_story("A farmer from a village in Gaya district, Bihar.", "Bihar") == []
    assert general.possible_names("Ramesh did not pay.", "The worker said Ramesh did not pay.", "Bihar") == ["Ramesh"]


def test_privacy_notes_name_groq_as_the_backup():
    for key in ("ui.general.names_warning", "ui.notes.warning"):
        assert "(Google Gemini, or Groq as a backup)" in lang.t(key)
        assert "Groq" in lang.t(key, "hi")
    assert "Groq as a backup" in (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'ui.step_heading("description", t("cw.drafts"))' in source


def test_update_the_letter_and_drafts_after_a_change(monkeypatch):
    from test_testing_fixes import wages
    from volunteer import make_drafts
    at = wages(monkeypatch)
    make_drafts(at, letter=False)
    at.checkbox(key="tick-case_documents").check().run()          # a change after the drafts were made
    ok(at)
    reds = " ".join(m.value for m in at.markdown if 'class="why-off red"' in m.value)
    assert "Something changed after the drafts were made." in reds and "Make the drafts" not in reds
    at.button(key="update-drafts").click().run()
    ok(at)
    assert at.session_state["shown_drafts"]


# ---------- 11. case tracker ----------

def test_next_step_follows_the_status_and_due_is_saved_on_send(tmp_path):
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    facts = make_facts()
    store.submit("DRAFT — to be checked by a lawyer\n\nx", facts, case_id=case_id, by="Volunteer A", base=tmp_path)
    tracker.confirm_facts(case_id, facts.facts, "Volunteer A", base=tmp_path)
    row = next(r for r in tracker.rows(base=tmp_path) if r["id"] == case_id)
    assert row["next_step"] == tracker.NEXT_REVIEW and row["due"] == (date.today() + timedelta(days=7)).isoformat()
    store.approve(case_id, base=tmp_path, by="Supervisor")
    row = next(r for r in tracker.rows(base=tmp_path) if r["id"] == case_id)
    assert row["next_step"] == "Hand over the approved letter and application, then record the submission"
    assert row["last_by"] == "Volunteer A"
    tracker.close_case(case_id, "resolved", "", "Supervisor", base=tmp_path)
    row = next(r for r in tracker.rows(base=tmp_path) if r["id"] == case_id)
    assert row["next_step"] == "" and row["last_by"] == "Volunteer A"


def test_sent_back_next_step_and_labels():
    assert tracker.NEXT_FIX == "Volunteer to fix and resend"
    assert lang.t("tr.close") == "Hide case file"
    schema = llm.GENERAL_SCHEMA["properties"]
    facts = [k for k, v in schema.items() if v is llm._YES_NO or k == "state"] + ["annual_income", "has_reference_number"]
    for code in ("en", "hi"):
        strings = json.load(open(ROOT / "i18n" / f"{code}.json", encoding="utf-8"))
        missing = [k for k in facts if f"tfact.{k}" not in strings]
        assert not missing, (code, missing)


def test_supervisor_step_is_ticked_once_approved():
    g = make_facts()
    steps = casework.next_steps(g, general.check_eligibility(g.facts), [], "none", date(2026, 11, 6),
                                case_approved=True)
    assert next(s for s in steps if s.text == lang.t("cw.step_supervisor")).done


def test_a_fact_is_dropped_only_when_the_dated_line_says_it_all():
    g = make_facts(outcome="the electricity reconnected",
                   what_happened=["The electricity department cut off the electricity connection.",
                                  "The electricity department cut off the electricity connection despite bills being "
                                  "paid on time."],
                   timeline=[("1 October 2026", "The electricity connection was cut off.")])
    lines = casework.letter_facts(g)
    # the date goes into the fact that tells the same event; the separate date line is dropped
    # the shorter line says nothing the longer one doesn't: once, with its date and nothing lost
    assert any(line.startswith("- On 1 October 2026, the electricity department cut off") and
               "despite bills being paid on time" in line for line in lines)
    assert not any(line.startswith("- 1 October 2026:") for line in lines)


# ---------- Case tracker sign-in: its own side panel ----------

@pytest.mark.parametrize("code", ["en", "hi"])
def test_tracker_sign_in_says_what_the_tracker_is_for(monkeypatch, code):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    for screen, mine, other in (("My cases", "t", "v"), ("New case", "v", "t")):
        at = AppTest.from_file("../app.py", default_timeout=30)
        at.session_state["screen"] = screen
        at.session_state["ui_lang"] = code
        at.run()
        ok(at)
        assert at.title[0].value == lang.t("gate.title", code)                      # title and form unchanged
        assert any(i.key == "gate-pass" for i in at.text_input)
        [side] = [m.value for m in at.markdown if 'class="signin-side"' in m.value]
        for n in (1, 2, 3):
            assert lang.t(f"signin.{mine}{n}", code).replace("'", "&#x27;") in side, (screen, n)
            assert lang.t(f"signin.{other}{n}", code).replace("'", "&#x27;") not in side, (screen, n)


# ---------- Final fixes A2 ----------

def a2_case(**kw):
    base = dict(person="a 62-year-old widow", outcome="the electricity reconnected",
                what_happened=["The electricity department disconnected the electricity connection in Gaya district, "
                               "Bihar, over an alleged pending amount of Rs 14,000.",
                               "A lineman is demanding Rs 2,000 for reconnection."],
                timeline=[("1 October 2026", "The electricity connection was disconnected by the electricity department.")],
                issues=[("electricity_or_water", "electricity connection cut")], documents_held=["bill receipts"],
                answers=[("Did the person receive any official notice before the electricity was disconnected?",
                          "No written notice was given before the cut"),
                         ("Did the person pay the bill?", "Yes"), ("Were others cut off too?", "Don't know")],
                facts={"state": "Bihar", "woman": True})
    base.update(kw)
    return make_facts(**base)


def test_a2_prompt_keeps_numbers_and_the_app_keeps_them():
    assert "keep every amount of money, count, age, place" in llm.GENERAL_PROMPT
    assert "never\n  as \"the person needing help\"" in llm.GENERAL_PROMPT or "never as \"the person needing help\"" in \
        " ".join(llm.GENERAL_PROMPT.split())
    raw = {"what_happened": ["The electricity department disconnected the connection over Rs 14,000 in Gaya district, Bihar.",
                             "A lineman is demanding Rs 2,000 for reconnection."]}
    reading = general.check_general_answer(raw, "Practice notes.")
    text = " ".join(reading.what_happened)
    assert "Rs 14,000" in text and "Rs 2,000" in text and "Gaya district, Bihar" in text


def test_a2_answers_reach_the_letter_and_the_dlsa_statement():
    g = a2_case()
    facts = casework.letter_facts(g)
    assert "- No written notice was given before the cut (as told by the person)." in facts
    assert not any("Yes (as told" in f or "Don't know" in f for f in facts)
    dlsa = casework.dlsa_application(g, general.check_eligibility(g.facts), "electricity connection cut", None)
    assert "No written notice was given before the cut (as told by the person)." in dlsa
    assert "The person needing help" not in dlsa
    assert "[not needed: qualifies as a woman]" in dlsa


def test_a2_the_date_goes_into_the_fact_everywhere():
    g = a2_case()
    facts = casework.letter_facts(g)
    assert facts[0].startswith("- On 1 October 2026, the electricity department disconnected")
    assert not any(f.startswith("- 1 October 2026:") for f in facts)
    body = general.summary_body(g)
    assert "On 1 October 2026, the electricity department disconnected" in body
    assert "- 1 October 2026: The electricity connection was disconnected" not in body
    letter = casework.complaint_letter(g, [], "electricity connection cut", None)
    assert "The facts are:" in letter
    import document
    import re as _re
    assert "The facts are:" in _re.sub(r"<[^>]+>", "", document.to_html(letter))   # the colon stays on the page


def test_a2_case_file_documents_match_the_intake():
    record = {"case_type": "General", "summary": ["The electricity was cut although she paid every bill."],
              "issues": [["electricity_or_water", "electricity connection cut"]], "documents_held": [],
              "facts": {"woman": {"value": True}, "state": {"value": "Bihar"}}}
    docs = casework.case_file_documents(record)
    assert "Latest electricity bill" in docs
    assert not any(d in docs for d in ("Pay slips", "Bank statements showing earlier payments"))
    assert "Self-declaration for free legal aid (no income proof needed: qualifies as a woman)" in docs
    assert not any(d.startswith("Income proof") for d in docs)
    assert casework.approved_text({"approved_on": "2026-11-13", "approved_by": "Supervisor"}) == \
        "approved by Supervisor on 13 November 2026"


def test_a2_source_labels():
    labels = research.source_labels([
        {"title": "Contact Us", "url": "https://nbpdcl.co.in/frmContactUs.aspx"},
        {"title": "Online Complaint", "url": "https://www.sbpdcl.co.in/ComplaintFormLatest.aspx"},
        {"title": "Contact Us", "url": "https://sbpdcl.co.in/contact.aspx"},
        {"title": "Contact Us", "url": "https://nbpdcl.co.in/frmContactUs.aspx/"}])   # the same page again
    assert [l for l, _ in labels] == ["Contact Us (nbpdcl.co.in)", "Online Complaint (sbpdcl.co.in)",
                                      "Contact Us (sbpdcl.co.in)"]
    assert research.display_title("The Bihar Gazette-CGRF-and-EO-Regulations.pdf)") == \
        "The Bihar Gazette CGRF and EO Regulations"


def test_a2_small_ones(tmp_path):
    g = a2_case(research_state="waiting", research_pending=7)
    body = general.summary_body(g)
    steps = body.split(lang.t("sum.next_steps"))[1]
    assert "Check the research points and the draft letter." in steps and "Research from official websites" not in steps
    letter = casework.complaint_letter(g, [dict(POINT, unchecked=True)], "electricity connection cut", None)
    assert "legal points were found on official websites with AI assistance and approved one by one by the supervisor" \
        in letter
    assert lang.t("intake.done_card_due", case_id="U-1", due="20 November 2026") == \
        "Intake finished. Case U-1 is with the supervisor (due 20 November 2026)."
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    store.submit("DRAFT — to be checked by a lawyer\n\nx", g, case_id=case_id, by="Volunteer A", base=tmp_path)
    store.approve(case_id, base=tmp_path, by="Supervisor")
    row = next(r for r in tracker.rows(base=tmp_path) if r["id"] == case_id)
    assert row["due"] == (date.today() + timedelta(days=7)).isoformat()   # approved: due in 7 days
    case_file = general.make_case_file(case_id, g.to_dict(), date.today())
    assert "✓ " + lang.t("cw.step_supervisor") in case_file


def test_a2_request_is_the_request_and_case_file_lists_papers():
    g = a2_case(outcome="The widow wants the electricity reconnected immediately and the incorrect bill corrected.")
    letter = casework.complaint_letter(g, [], "electricity connection cut", None)
    assert "The person requests: the electricity reconnected immediately and the incorrect bill corrected." in letter
    record = {"case_type": "General", "summary": ["The electricity was cut."], "documents_held": ["bill receipts"],
              "issues": [["electricity_or_water", "electricity connection cut"]],
              "facts": {"woman": {"value": True}, "state": {"value": "Bihar"}},
              "research_points": [{"kind": "documents", "text": "Details needed include name and address.",
                                   "sources": [], "approved_on": "2026-11-13"}]}
    docs = casework.case_file_documents(record)
    assert "Self-declaration for free legal aid (no income proof needed: qualifies as a woman)" in docs
    assert "Latest electricity bill" not in docs and "bill receipts" not in docs  # her bill receipts stand for it
