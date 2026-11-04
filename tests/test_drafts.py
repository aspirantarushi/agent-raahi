from datetime import date

import pytest

import drafts
import section479
import store
from drafts import DRAFT_HEADER, TEMPLATES, UndertrialFacts


def practice_facts(**changes):
    """The practice case in CLAUDE.md."""
    values = dict(
        law_typed="IPC", section_typed="380",
        custody_began=date(2024, 3, 15), today=date(2026, 11, 2),
        never_convicted=True, other_cases_pending=False, more_than_one_section=False,
        question_answered=False, delay_days_by_accused=0,
        lawyer="Legal aid lawyer", offence_name="",
        offence_date=date(2024, 2, 15),  # case notes: "The offence was in February 2024"
    )
    values.update(changes)
    return UndertrialFacts(**values)


def practice_draft(**changes):
    facts = practice_facts(**changes)
    result = drafts.recalculate(facts)
    return facts, result, drafts.make_undertrial_draft(facts, result)


# ---------- the practice case draft ----------

def test_practice_case_draft():
    _, _, text = practice_draft()
    assert text.startswith(DRAFT_HEADER)
    assert "- Sections charged: IPC 380 (now BNS 305)\n" in text
    assert "- Maximum punishment for the offence: 7 years (84 months) (as per IPC 380)\n" in text
    assert "- Why this maximum: The offence happened before 1 July 2024, so the IPC maximum is used" in text
    assert "- Date custody began: 15 March 2024" in text
    assert "- Period in custody as on today: 31 months 18 days (as on 2 November 2026)" in text
    assert "- Previous convictions: none known" in text
    assert "- Other cases pending: none known" in text
    assert "- One-half of the maximum term: 15 September 2027 — not yet reached" in text
    assert ("- One-third of the maximum term (first-time offender only): "
            "15 July 2026 — reached") in text
    # He already has a legal aid lawyer: no DLSA application.
    assert "APPLICATION FOR FREE LEGAL SERVICES" not in text
    assert "automatic" not in text.lower() or "not automatic" in text.lower()


def test_unknown_blanks_stay_visible():
    _, _, text = practice_draft()
    for blank in ["[court, CNR]", "[FIR, police station]", "[jail name]", "[organisation or legal aid clinic]",
                  "[name of volunteer or caseworker]", "[contact]", "Date: [date]"]:
        assert blank in text


def test_template_copied_exactly_except_filled_blanks():
    facts, result, text = practice_draft()
    template = (TEMPLATES / "section479_note.md").read_text(encoding="utf-8")
    targets = [old for old, _ in drafts.section479_replacements(facts, result)]
    untouched = [t for t in template.splitlines() if not any(old in t for old in targets)]
    d_lines = iter(text.splitlines())
    for t in untouched:  # every untouched template line appears unchanged, in the same order
        assert any(d == t for d in d_lines), t


def test_no_lawyer_adds_dlsa_application():
    _, _, text = practice_draft(lawyer="None")
    assert text.startswith(DRAFT_HEADER)
    assert text.count(DRAFT_HEADER) == 2  # note and application, each marked
    assert "APPLICATION FOR FREE LEGAL SERVICES" in text
    assert "Yes — person in custody" in text
    # personal blanks stay empty for the person to fill by hand
    assert "1. Name of applicant: [to be filled by hand at the DLSA — not stored in the app]" in text
    assert "2. Permanent address: [to be filled by hand]" in text
    assert "3. Contact address, phone and email (if any): [to be filled by hand]" in text


@pytest.mark.parametrize("lawyer", ["Legal aid lawyer", "Private lawyer", "Don't know"])
def test_dlsa_application_only_when_no_lawyer(lawyer):
    _, _, text = practice_draft(lawyer=lawyer)
    assert "APPLICATION FOR FREE LEGAL SERVICES" not in text


def test_previous_conviction_and_lawyer_check_shown():
    _, _, text = practice_draft(never_convicted=False, more_than_one_section=True)
    assert "- Previous convictions: yes, details [___]" in text
    assert "first-time offender only): not applicable (previous conviction)" in text
    assert "and other sections [___]" in text
    assert "(to be checked by a lawyer)" in text


def test_no_draft_when_section_479_does_not_apply():
    facts = practice_facts(section_typed="395")  # dacoity: life possible
    result = drafts.recalculate(facts)
    with pytest.raises(ValueError):
        drafts.make_undertrial_draft(facts, result)


def test_fill_catches_template_changes():
    with pytest.raises(ValueError):
        drafts.fill("[date] and [date]", [("[date]", "1 May")])


def test_offence_picked_from_several_rows():
    facts = practice_facts(section_typed="307", offence_name="Attempt to murder (no hurt caused)")
    assert drafts.recalculate(facts).offence.max_months == 120


# ---------- personal details check ----------

@pytest.mark.parametrize("text", ["Call 9876543210", "+91 98765 43210".replace(" ", ""),
                                  "Aadhaar 1234 5678 9012"])
def test_personal_numbers_detected(text):
    assert drafts.personal_details_found(text)


@pytest.mark.parametrize("text", ["CNR DLCT010012342024", "FIR 123/2024", "15 September 2027"])
def test_case_numbers_allowed(text):
    assert not drafts.personal_details_found(text)


# ---------- approval flow ----------

def submit_practice(base, **changes):
    facts, _, text = practice_draft(**changes)
    return store.submit(text, facts, base=base)


def test_nothing_saved_in_drafts_before_approval(tmp_path):
    case_id = submit_practice(tmp_path)
    assert (tmp_path / "pending" / f"{case_id}.json").exists()
    assert not (tmp_path / "drafts").exists() or not any((tmp_path / "drafts").iterdir())
    assert not (tmp_path / "cases").exists() or not any((tmp_path / "cases").iterdir())
    assert [c["status"] for c in store.list_cases(tmp_path)] == ["waiting"]


def test_approve_saves_draft_and_case_file(tmp_path):
    case_id = submit_practice(tmp_path)
    store.approve(case_id, base=tmp_path, approved_on=date(2026, 11, 3))

    assert not (tmp_path / "pending" / f"{case_id}.json").exists()
    draft = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert draft.startswith(DRAFT_HEADER)

    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "- Date: 3 November 2026" in case
    assert "- Case type: Undertrial (Section 479 BNSS)" in case
    assert "- Follow-up date: 10 November 2026" in case
    for heading in ["## Facts known", "## Facts missing", "## Next steps"]:
        assert heading in case
    assert "15 July 2026 — reached" in case
    assert "Release is not automatic" in case
    assert [c["status"] for c in store.list_cases(tmp_path)] == ["approved"]


def test_edit_then_approve_keeps_draft_header(tmp_path):
    case_id = submit_practice(tmp_path)
    store.approve(case_id, edited_text="To the DLSA, edited by the supervisor.", base=tmp_path)
    draft = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert draft.startswith(DRAFT_HEADER)
    assert "edited by the supervisor" in draft


def test_edit_with_phone_number_is_refused(tmp_path):
    case_id = submit_practice(tmp_path)
    with pytest.raises(ValueError):
        store.approve(case_id, edited_text=DRAFT_HEADER + "\nCall 9876543210", base=tmp_path)
    assert not (tmp_path / "drafts").exists() or not any((tmp_path / "drafts").iterdir())


def test_reject_sends_back_with_reason(tmp_path):
    case_id = submit_practice(tmp_path)
    store.reject(case_id, "Please check the custody date.", base=tmp_path)
    [case] = store.list_cases(tmp_path)
    assert case["status"] == "sent back"
    assert case["reason"] == "Please check the custody date."
    assert store.list_pending(tmp_path) == []  # no longer waiting
    with pytest.raises(ValueError):
        store.approve(case_id, base=tmp_path)  # can't approve a sent-back draft
    assert not (tmp_path / "drafts").exists()


def test_reject_needs_a_reason(tmp_path):
    case_id = submit_practice(tmp_path)
    with pytest.raises(ValueError):
        store.reject(case_id, "   ", base=tmp_path)


def test_submit_refuses_draft_without_header(tmp_path):
    facts, _, _ = practice_draft()
    with pytest.raises(ValueError):
        store.submit("Not a draft", facts, base=tmp_path)


def test_bad_case_id_refused(tmp_path):
    with pytest.raises(ValueError):
        store.approve("../../etc/passwd", base=tmp_path)


def test_case_file_has_no_personal_details(tmp_path):
    case_id = submit_practice(tmp_path, lawyer="None")
    store.approve(case_id, base=tmp_path)
    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8")
    assert not drafts.personal_details_found(case)
    assert "No names or personal details" in case


# ---------- offence date decides the section wording ----------

@pytest.mark.parametrize("offence_date, expected", [
    (date(2024, 6, 30), "- Sections charged: IPC 325 (now BNS 117(2))\n"),
    (date(2024, 7, 1), "- Sections charged: BNS 117(2) (earlier IPC 325)\n"),
    (date(2025, 3, 1), "- Sections charged: BNS 117(2) (earlier IPC 325)\n"),
])
def test_section_wording_depends_on_offence_date(offence_date, expected):
    _, _, text = practice_draft(section_typed="325", offence_date=offence_date,
                                custody_began=date(2025, 3, 2))
    assert expected in text


def test_typing_the_bns_section_gives_the_same_wording():
    _, _, text = practice_draft(law_typed="BNS", section_typed="305", offence_date=date(2024, 2, 15))
    assert "- Sections charged: IPC 380 (now BNS 305)\n" in text


def test_new_bns_offence_wording():
    _, _, after = practice_draft(law_typed="BNS", section_typed="304(2)", offence_date=date(2025, 1, 1),
                                 custody_began=date(2025, 1, 2))
    assert "BNS 304(2) (new offence, no single IPC equivalent)" in after
    _, _, before = practice_draft(law_typed="BNS", section_typed="304(2)", offence_date=date(2024, 1, 1))
    assert "IPC [___] (now BNS 304(2), a new offence in the BNS)" in before


def test_dlsa_statement_and_case_file_use_same_wording(tmp_path):
    _, _, text = practice_draft(lawyer="None")
    assert "charged under IPC 380 (now BNS 305) (theft" in text
    case_id = submit_practice(tmp_path)
    store.approve(case_id, base=tmp_path)
    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "- Sections: IPC 380 (now BNS 305)" in case
    assert "- Offence date: 15 February 2024" in case


# ---------- ask_to_decide question in the note ----------

QUESTION = "Was the person a clerk or employee, carrier or warehouse-keeper, or a public servant, banker or agent?"


def lines_with(text, start):
    return [line for line in text.splitlines() if line.startswith(start)]


def test_unanswered_question_written_in_note_and_both_dates_flagged():
    _, _, text = practice_draft(section_typed="406")
    assert (f"- Question that decides the maximum term: {QUESTION} "
            "Answer: not answered — to be checked by a lawyer") in text
    [half] = lines_with(text, "- One-half of the maximum term:")
    [third] = lines_with(text, "- One-third of the maximum term")
    assert half.endswith("(to be checked by a lawyer)")
    assert third.endswith("(to be checked by a lawyer)")


def test_answered_and_confirmed_question():
    _, _, text = practice_draft(section_typed="406", answer="No, none of these",
                                question_answered=True)
    assert f"{QUESTION} Answer: No, none of these\n" in text
    assert "(to be checked by a lawyer)" not in text


def test_answer_not_confirmed_still_flagged():
    _, _, text = practice_draft(section_typed="406", answer="Not sure", question_answered=False)
    assert "Answer: Not sure (not confirmed as the right offence — to be checked by a lawyer)" in text
    [half] = lines_with(text, "- One-half of the maximum term:")
    assert half.endswith("(to be checked by a lawyer)")


def test_ticked_but_empty_answer_counts_as_unanswered():
    facts, result, text = practice_draft(section_typed="406", answer="  ", question_answered=True)
    assert facts.question_answered is False
    assert result.lawyer_check


def test_question_line_sits_in_case_details():
    _, _, text = practice_draft(section_typed="406")
    lines = text.splitlines()
    i = lines.index("- Other cases pending: none known")
    assert lines[i + 1].startswith("- Question that decides the maximum term:")
    assert lines[i + 3] == "Calculation (to be verified)"


def test_no_question_line_when_row_has_no_question():
    _, _, text = practice_draft()
    assert "Question that decides" not in text


def test_case_file_records_question_and_answer(tmp_path):
    case_id = submit_practice(tmp_path, section_typed="406", answer="No", question_answered=True)
    store.approve(case_id, base=tmp_path)
    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8")
    assert f"{QUESTION} Answer: No" in case
    assert "Answer to:" not in case  # not listed as missing


def test_old_saved_record_without_new_fields_still_loads():
    old = practice_facts().to_dict()
    del old["offence_date"], old["answer"]
    facts = UndertrialFacts.from_dict(old)
    assert facts.offence_date is None
    assert "[offence date not given: which law applies?]" in drafts.make_undertrial_draft(
        facts, drafts.recalculate(facts))


# ---------- fix and resend ----------

def test_fix_and_resend(tmp_path):
    case_id = submit_practice(tmp_path)
    store.reject(case_id, "Please add the court.", base=tmp_path)
    fixed = store.get_pending(case_id, base=tmp_path)["draft"].replace("[court, CNR]", "Saket Court, CNR DLST010000012024")
    store.resend(case_id, fixed, base=tmp_path)

    record = store.get_pending(case_id, base=tmp_path)
    assert record["status"] == "waiting" and record["reason"] == ""
    assert record["history"][0]["sent_back_reason"] == "Please add the court."
    assert [r["id"] for r in store.list_pending(tmp_path)] == [case_id]  # back with the supervisor

    store.approve(case_id, base=tmp_path)
    assert "Saket Court" in (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")


def test_resend_only_for_sent_back_drafts(tmp_path):
    case_id = submit_practice(tmp_path)
    with pytest.raises(ValueError):
        store.resend(case_id, DRAFT_HEADER + "\nfixed", base=tmp_path)


@pytest.mark.parametrize("bad_text", ["No header here", DRAFT_HEADER + "\nCall 9876543210"])
def test_resend_refuses_bad_drafts(tmp_path, bad_text):
    case_id = submit_practice(tmp_path)
    store.reject(case_id, "Fix it", base=tmp_path)
    with pytest.raises(ValueError):
        store.resend(case_id, bad_text, base=tmp_path)
    assert store.get_pending(case_id, base=tmp_path)["status"] == "sent back"


def test_case_numbers_never_look_like_aadhaar(tmp_path):
    for _ in range(300):
        case_id = store.new_case_id(tmp_path)
        assert store.ID_PATTERN.match(case_id)
        assert not drafts.personal_details_found(f"# Case {case_id}")


# ---------- which maximum, written in the note ----------

def test_note_says_which_maximum_and_why_for_old_ipc_384():
    _, _, text = practice_draft(section_typed="384", offence_date=date(2023, 5, 20),
                                custody_began=date(2023, 6, 1))
    assert "- Maximum punishment for the offence: 3 years (36 months) (as per IPC 384)\n" in text
    assert ("- Why this maximum: The offence happened before 1 July 2024, so the IPC maximum is used: "
            "Article 20(1) of the Constitution bars a heavier penalty than the law in force when the "
            "offence happened. (The BNS maximum, 84 months, is higher and does not apply.)") in text


def test_note_says_which_maximum_and_why_for_bns_308_2():
    _, _, text = practice_draft(law_typed="BNS", section_typed="308(2)", offence_date=date(2025, 1, 20),
                                custody_began=date(2025, 2, 1))
    assert "- Maximum punishment for the offence: 7 years (84 months) (as per BNS 308(2))\n" in text
    assert "- Why this maximum: The offence happened on or after 1 July 2024" in text


def test_note_flags_both_dates_when_ipc_maximum_blank():
    _, _, text = practice_draft(law_typed="BNS", section_typed="304(2)", offence_date=date(2024, 4, 1),
                                custody_began=date(2024, 5, 1))
    assert "our sentence table has no IPC maximum" in text
    [half] = lines_with(text, "- One-half of the maximum term:")
    assert half.endswith("(to be checked by a lawyer)")


def test_case_file_says_which_maximum(tmp_path):
    case_id = submit_practice(tmp_path, section_typed="384", offence_date=date(2023, 5, 20),
                              custody_began=date(2023, 6, 1))
    store.approve(case_id, base=tmp_path)
    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "- Maximum prison term: 3 years (36 months), as per IPC 384" in case
    assert "- Why this maximum: The offence happened before 1 July 2024" in case


# ---------- Source line for "Why this maximum" ----------

def old_maximum_source_line():
    src = section479.knowledge_source("Old offences use the old maximum")
    return f"Source: {src['source']} ({src['link']})"


def test_source_line_comes_from_knowledge_entry():
    line = old_maximum_source_line()
    assert line.startswith("Source: Constitution of India, Article 20(1)")
    assert "https://www.constitutionofindia.net/articles/article-20" in line


def test_note_shows_source_line_under_why_this_maximum():
    _, _, text = practice_draft(section_typed="384", offence_date=date(2023, 5, 20),
                                custody_began=date(2023, 6, 1))
    lines = text.splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("- Why this maximum:"))
    assert lines[i + 1] == "  " + old_maximum_source_line()


def test_practice_case_note_shows_source_line():
    _, _, text = practice_draft()  # IPC 380, offence February 2024
    assert "  " + old_maximum_source_line() + "\n" in text


def test_source_line_shown_when_ipc_maximum_blank():
    _, _, text = practice_draft(law_typed="BNS", section_typed="304(2)", offence_date=date(2024, 4, 1),
                                custody_began=date(2024, 5, 1))
    assert old_maximum_source_line() in text


def test_offence_after_july_2024_reason_and_source_line():
    _, _, text = practice_draft(law_typed="BNS", section_typed="308(2)", offence_date=date(2025, 1, 20),
                                custody_began=date(2025, 2, 1))
    lines = text.splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("- Why this maximum:"))
    assert lines[i] == ("- Why this maximum: The offence happened on or after 1 July 2024, so the BNS "
                        "maximum is used: only offences committed before 1 July 2024 use the old IPC maximum.")
    assert lines[i + 1] == "  " + old_maximum_source_line()
    assert "came into force" not in text


def test_case_file_shows_source_line(tmp_path):
    case_id = submit_practice(tmp_path, section_typed="384", offence_date=date(2023, 5, 20),
                              custody_began=date(2023, 6, 1))
    store.approve(case_id, base=tmp_path)
    case = (tmp_path / "cases" / f"{case_id}.md").read_text(encoding="utf-8").splitlines()
    i = next(n for n, l in enumerate(case) if l.startswith("- Why this maximum:"))
    assert case[i + 1] == "  " + old_maximum_source_line()
