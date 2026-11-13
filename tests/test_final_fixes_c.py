"""Final fixes C (13 November 2026): practice-run problems, phone layout, clearer steps, grammar. Fake data only."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import casework
import general
import lang
import llm
import tracker
from test_new_case_fixes import facts as make_facts

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


# ---------- 1. "in custody" only from the notes' own words; one "Urgent:" ----------

def test_custody_needs_jail_custody_or_arrest_in_the_notes():
    story6 = "Kisan ki bijli 2 November 2026 ko kaat di. Lineman ne 2,000 rupaye kharcha-pani maanga."
    r = general.check_general_answer({"in_custody": {"value": "yes", "quote": "bijli 2 November 2026 ko kaat di"}}, story6)
    assert "in_custody" not in r.facts and "in_custody" in r.dropped
    arrest = "Bhai ko police ne 5 August 2024 ko giraftar kiya."
    r = general.check_general_answer({"in_custody": {"value": "yes", "quote": "giraftar kiya"}}, arrest)
    assert r.facts["in_custody"] is True
    assert "lock-up now, and the quote must contain those words" in llm.GENERAL_PROMPT


def test_one_urgent_with_the_reasons_joined():
    g = make_facts(facts={"state": "Bihar", "in_custody": True, "essential_service_cut": True},
                   issues=[("electricity_or_water", "electricity cut off")])
    assert casework.urgency(g, date(2026, 11, 13)).reasons == [
        "Urgent: someone is in custody now; the electricity is cut off now. Act this week."]
    g = make_facts(facts={"state": "Bihar", "essential_service_cut": True}, issues=[("electricity_or_water", "cut")])
    assert casework.urgency(g, date(2026, 11, 13)).reasons == ["Urgent: the electricity is cut off now. Act this week."]


# ---------- 2. the same fact in other words: once ----------

def test_story_6_facts_are_said_once():
    lines = ["The electricity to the person's house was cut on 2 November 2026 despite timely payment of the "
             "October 2026 bill.", "The lineman demanded Rs 2,000 kharcha-pani to reconnect the electricity supply.",
             "The electricity to the house of the person seeking help was cut off.",
             "The bill for October 2026 was paid on time.",
             "A demand for an unofficial payment was made to restore the electricity."]
    assert tracker.dedupe_facts(lines) == lines[:2]   # the ones with the numbers and dates stay
    distinct = ["The worker was not paid for three months.", "He has photos of the attendance register."]
    assert tracker.dedupe_facts(distinct) == distinct
    assert "no two what_happened sentences may say the same thing" in llm.GENERAL_PROMPT


# ---------- 3 and 34. a reason under each left-out point; one reason for all ----------

def test_left_out_reasons_wording():
    assert [lang.t(f"rs.why_left.{c}") for c in ("not_about", "looks_wrong", "repeats", "other")] == \
        ["Not about this case", "Looks wrong", "Repeats another point", "Other"]
    assert lang.t("rs.button_reasons_missing", n=1) == "1 reason missing"
    assert lang.t("rs.left_out_all") == "Send anyway: one reason for all the points left out"
    assert "rs.left_out_needs_reason" not in lang.strings("en")          # never "(p2)"
    assert 'key="g_rs_all_reason"' in APP and "rsvs" in APP               # a box to type in, always


# ---------- 4, 30, 31. one document list, rows, short names ----------

def test_custody_documents_are_short_with_help_and_no_income_affidavit():
    g = make_facts(issues=[("arrest_or_custody", "arrested for extortion")], what_happened=["The brother was arrested."],
                   documents_held=[], facts={"state": "Bihar", "in_custody": True})
    docs = casework.document_checklist(g, [])
    assert docs == ["ID proof", "Self-declaration for free legal aid (no income proof needed: in custody)",
                    "Case papers (FIR, notices, court orders, chargesheet)"]
    assert all(len(d) <= 75 for d in docs)
    assert "affidavit" not in json.dumps(casework.DOC_HELP.get(docs[1], ""))  # never for a Section 12 group
    assert casework.DOC_HELP["Case papers (FIR, notices, court orders, chargesheet)"].startswith("All case papers")


def test_a_paper_from_the_story_merges_with_its_kind_and_names_are_capitalised():
    g = make_facts(issues=[("electricity_or_water", "electricity cut off")], what_happened=["The electricity was cut."],
                   documents_held=["october 2026 bill"], facts={"state": "Bihar"})
    docs = casework.document_checklist(g, [])
    assert docs[0] == "October 2026 bill"
    assert "Latest electricity bill" not in docs and "Receipts of bills paid" not in docs


def test_no_separate_documents_card_on_step_3(monkeypatch):
    from test_testing_fixes import wages
    at = wages(monkeypatch)
    ok(at)
    page = " ".join(m.value for m in at.markdown)
    assert "The person has" not in page and "Usually needed" not in page
    assert [r for r in at.radio if str(r.key).startswith("doc-st-")]          # rows, in the checklist


# ---------- 5, 29, 33. one required-mark rule; lines around the documents ----------

def test_required_marks_are_red_and_the_same_everywhere(monkeypatch):
    from test_testing_fixes import wages
    at = wages(monkeypatch)
    ticks = [c for c in at.checkbox if str(c.key).startswith("tick-")]
    assert ticks and all(c.label.endswith(" :red[\\*]") for c in ticks)
    assert at.checkbox(key="g_checked").label.endswith(" :red[\\*]")
    legends = [m.value for m in at.markdown if 'class="req-legend"' in m.value]
    assert len(legends) >= 2 and "needed before sending" in legends[0]       # checklist and Send box
    assert ".req-legend { color: var(--red)" in CSS
    assert "{REQUIRED}: {t('ready.status.'" in APP                            # the Section 479 checklist too
    assert 'class="doc-block-top"' in " ".join(m.value for m in at.markdown)
    assert ".doc-block-top { border-top" in CSS and "border-left: 1px solid var(--line)" in CSS


# ---------- 28. next steps: plain text, the date in bold, one note ----------

def test_next_steps_are_plain_with_one_dates_note():
    g = make_facts(facts={"state": "Bihar", "woman": True}, issues=[("electricity_or_water", "electricity cut off")])
    body = general.summary_body(g)
    steps = body.split(lang.t("sum.next_steps"))[1]
    assert " — by " in steps and "a suggested follow-up, not a legal deadline" not in steps
    assert steps.count("Dates are suggested follow-ups, not legal deadlines.") == 1


# ---------- 32. the Problem says what went wrong ----------

def test_a_one_or_two_word_topic_is_not_accepted():
    raw = {"what_happened": ["The electricity was cut off on 2 November 2026 although the October bill was paid."],
           "issues": [{"category": "electricity_or_water", "name": "electricity connection"}]}
    reading = general.check_general_answer(raw, "Practice notes.")
    assert reading.issues[0][1] != "electricity connection" and len(reading.issues[0][1].split()) > 2
    good = {"issues": [{"category": "electricity_or_water", "name": "electricity cut off despite a paid bill"}]}
    assert general.check_general_answer(good, "x").issues[0][1] == "electricity cut off despite a paid bill"
    assert "at least three words, not just the topic" in llm.GENERAL_PROMPT


# ---------- 13 to 20. grammar and wording ----------

def test_grammar_and_wording():
    assert lang.t("home.how1_p").endswith("Phone numbers, Aadhaar numbers and email addresses are removed first.")
    assert lang.t("home.how3_p").startswith("When the volunteer presses a button, the agent searches official websites")
    assert lang.t("tl.action.Undo (back to to do)") == "Undo (back to To do)"
    assert lang.t("ui.sup.problems_today", n=3, ok=2) == "Today the AI was busy 3 times; a retry or the backup answered 2."
    assert lang.t("cw.flag_payment", quote="The lineman asked for Rs 2,000 to reconnect.").startswith(
        "The story mentions a demand for an unofficial payment: “The lineman asked for Rs 2,000 to reconnect”.")
    assert lang.inr(150000) == "₹1,50,000" and lang.inr(12000000) == "₹1,20,00,000" and lang.inr(6000) == "₹6,000"
    elig = general.check_eligibility({"state": "Bihar", "annual_income": 120000})
    assert "₹1,20,000" in elig.reason and "₹1,50,000" in elig.reason
    assert lang.t("ready.case_person") == "Who needs help (their role)"
    woman = general.check_eligibility({"state": "Bihar", "woman": True})
    assert woman.reason == "Qualifies for free legal aid as a woman, whatever the income."
    for key in ("ui.general.story_placeholder", "home.story_placeholder", "rs.working", "ui.notes.placeholder"):
        assert lang.t(key).endswith("…") and " …" not in lang.t(key) and "..." not in lang.t(key)


def test_hindi_has_no_double_spaces_or_stray_english_words():
    hi = json.load(open(ROOT / "i18n" / "hi.json", encoding="utf-8"))
    for k, v in hi.items():
        if k.startswith(("doc:", "next:", "elig.q_en:")) or not isinstance(v, str):
            continue
        assert "(optional)" not in v and " session" not in v.casefold() and "checklist" not in v, k
        for a, b in ("()", "[]", "“”"):
            assert v.count(a) == v.count(b), k


# ---------- 22 to 27. Home, Learn, sign-in ----------

def test_home_hero_and_helplines():
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Home"
    at.run()
    page = " ".join(m.value for m in at.markdown)
    assert '<p class="sub">Agent Raahi turns a person' in page
    assert "Free and open source." not in page.split("<footer")[0]


def test_learn_guide_on_top_with_back_and_no_dangling_also():
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Learn"
    at.session_state["learn_guide"] = "legal_aid"
    at.run()
    ok(at)
    assert at.button(key="learn-back-top").label == "Back to all guides" and at.button(key="learn-back-end")
    srcs = [m.value for m in at.markdown if 'class="learn-src"' in m.value]
    assert srcs and not any(re.search(r"also</a>\s*</p>|· also</p>", s) for s in srcs)
    assert any("· also: <a" in s for s in srcs)
    at.button(key="learn-back-top").click().run()
    assert "learn_guide" not in at.session_state


def test_quiz_question_4_has_exactly_one_right_answer():
    import guides
    q = guides.content("undertrial").quiz[3]
    assert [t for _, t in q.options] == ["Theft in a dwelling house (BNS 305)", "Cheating (BNS 318(4))",
                                         "Murder (BNS 103(1))", "Extortion (BNS 308(2))"]
    assert q.answer == "c"


@pytest.mark.parametrize("name, shown", [("Agent Raahi Practice Clinic", True), ("GNLU LSC", False)])
def test_practice_hint_on_sign_in_only_for_a_practice_clinic(monkeypatch, name, shown):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    monkeypatch.setenv("CLINIC_NAME", name)
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    hint = lang.t("signin.practice_hint")
    assert (hint in [c.value for c in at.caption]) is shown


# ---------- 6 to 12. phone layout and clearer steps (styles) ----------

def test_layout_rules_are_in_the_stylesheet():
    assert "padding-bottom: 96px" in CSS                                   # clear of the host's badge
    assert ".st-key-next-action { justify-content: flex-start !important; padding-right: 88px" in CSS
    assert ".brand .word { display: none !important; }" in CSS and ".st-key-nav-start { display: block !important; }" in CSS
    assert '[data-testid="InputInstructions"] { display: none !important; }' in CSS
    assert "stNumberInputStepUp" in CSS and "flex-direction: column !important" in CSS
    assert ".stepper-phone { display: none !important; }" in CSS
    assert "--bg: #F3F0E9" in CSS and "--line: #D8D1C3" in CSS and "border-radius: 14px" in CSS
    assert lang.t("ui.lang.choose") == "Choose language"
    assert lang.t("ui.general.story_done") == "Step 1 · Tell the story — done (show or edit)"


def test_step_bands_show_number_name_and_state(monkeypatch):
    from test_testing_fixes import wages
    at = wages(monkeypatch)
    bands = [m.value for m in at.markdown if 'class="step-band' in m.value]
    assert any('step-band now' in b and "Draft and research" in b for b in bands)
    assert any('step-band' in b and "Send for review" in b for b in bands)


def test_going_on_for_starts_when_the_problem_began():
    g = make_facts(what_happened=["The electricity was cut."],
                   timeline=[("October 2026", "Electricity bill was paid"), ("2 November 2026", "The electricity was cut off")])
    assert casework.duration_text(g, date(2026, 11, 13)) == \
        "about 11 days (since 2 November 2026: the electricity was cut off)"
