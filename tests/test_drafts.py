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
    assert "- Sections charged: BNS 305 / IPC 380" in text
    assert "- Maximum punishment for the offence: 7 years (84 months) (as per BNS 305)" in text
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
    t_lines, d_lines = template.splitlines(), text.splitlines()
    assert len(t_lines) == len(d_lines)
    for t, d in zip(t_lines, d_lines):
        if not any(old in t for old in targets):
            assert t == d


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
