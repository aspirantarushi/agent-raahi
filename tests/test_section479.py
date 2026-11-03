from datetime import date
from fractions import Fraction

import pytest

from section479 import (
    LAWYER_CHECK,
    add_months,
    calculate,
    find_offences,
    knowledge_source,
    load_offences,
)


def one(law, section):
    rows = find_offences(law, section)
    assert len(rows) == 1, rows
    return rows[0]


# ---------- the practice case in CLAUDE.md ----------

def test_practice_case():
    offence = one("IPC", "380")
    assert offence.bns_section == "305"
    assert offence.max_months == 84

    r = calculate(
        offence,
        custody_began=date(2024, 3, 15),
        today=date(2026, 11, 2),
        never_convicted=True,
        other_cases_pending=False,
        more_than_one_section=False,
    )
    assert r.applies and not r.lawyer_check
    assert r.one_third.months == 28
    assert r.one_third.when == date(2026, 7, 15)
    assert r.one_third.reached is True
    assert r.one_half.months == 42
    assert r.one_half.when == date(2027, 9, 15)
    assert r.one_half.reached is False


def test_knowledge_file_example():
    # knowledge/undertrial_bail.md: custody 1 March 2025, BNS 305 -> one-third on 1 July 2027
    r = calculate(one("BNS", "305"), date(2025, 3, 1), date(2026, 11, 2), True, False, False)
    assert r.one_third.when == date(2027, 7, 1)


# ---------- looking up sections ----------

@pytest.mark.parametrize("typed", ["380", "IPC 380", " ipc380 ", "Section 380"])
def test_ipc_lookup_accepts_different_spellings(typed):
    assert one("IPC", typed).bns_section == "305"


def test_bns_exact_subsection():
    assert one("BNS", "117(2)").ipc_section == "325"


def test_bns_number_without_subsection_gives_all_rows():
    found = {o.bns_section for o in find_offences("BNS", "117")}
    assert found == {"117(2)", "117(3)"}


def test_ipc_section_with_two_rows():
    # IPC 307: attempt to murder, with and without hurt
    assert len(find_offences("IPC", "307")) == 2


def test_unknown_section_returns_nothing():
    assert find_offences("IPC", "9999") == []
    assert find_offences("IPC", "") == []


def test_new_bns_offences_not_matched_by_ipc_new():
    assert find_offences("IPC", "new") == []


def test_every_row_has_a_source():
    for o in load_offences():
        assert o.source_url.startswith("https://"), o.offence


# ---------- when Section 479 does not apply ----------

def test_life_offence_does_not_apply():
    r = calculate(one("IPC", "395"), date(2020, 1, 1), date(2026, 11, 2), True, False, False)
    assert not r.applies
    assert r.one_third is None and r.one_half is None


def test_death_offence_does_not_apply():
    r = calculate(one("IPC", "302"), date(2020, 1, 1), date(2026, 11, 2), True, False, False)
    assert not r.applies


def test_other_cases_pending_not_available():
    r = calculate(one("IPC", "380"), date(2024, 3, 15), date(2026, 11, 2), True, True, False)
    assert not r.applies
    assert any("more than one case" in reason.lower() for reason in r.reasons)


# ---------- when dates need a lawyer ----------

def test_more_than_one_section_needs_lawyer():
    r = calculate(one("IPC", "380"), date(2024, 3, 15), date(2026, 11, 2), True, False, True)
    assert r.applies and r.lawyer_check
    assert r.one_half.when == date(2027, 9, 15)  # dates still shown
    assert any(LAWYER_CHECK in reason for reason in r.reasons)


def test_unanswered_question_needs_lawyer():
    offence = one("IPC", "406")  # has an ask_to_decide question
    r = calculate(offence, date(2024, 1, 1), date(2026, 11, 2), True, False, False)
    assert r.lawyer_check


def test_answered_question_no_lawyer_flag():
    offence = one("IPC", "406")
    r = calculate(offence, date(2024, 1, 1), date(2026, 11, 2), True, False, False, question_answered=True)
    assert not r.lawyer_check


def test_row_flagged_check_needs_lawyer():
    offence = one("BNS", "106(2)")
    r = calculate(offence, date(2025, 1, 1), date(2026, 11, 2), True, False, False)
    assert r.lawyer_check


# ---------- convictions, delay and dates ----------

def test_convicted_before_gets_no_one_third_date():
    r = calculate(one("IPC", "380"), date(2024, 3, 15), date(2026, 11, 2), False, False, False)
    assert r.one_third.when is None
    assert r.one_half.when == date(2027, 9, 15)


def test_delay_by_accused_moves_dates_later():
    r = calculate(one("IPC", "380"), date(2024, 3, 15), date(2026, 11, 2), True, False, False,
                  delay_days_by_accused=10)
    assert r.one_third.when == date(2026, 7, 25)
    assert r.one_half.when == date(2027, 9, 25)


def test_reached_on_the_day_itself():
    r = calculate(one("IPC", "380"), date(2024, 3, 15), date(2026, 7, 15), True, False, False)
    assert r.one_third.reached is True


def test_part_month_is_rounded_later_and_flagged():
    # IPC 341: maximum 1 month. One-half = 0.5 month = 15 days.
    r = calculate(one("IPC", "341"), date(2026, 10, 1), date(2026, 11, 2), True, False, False)
    assert r.one_half.months == Fraction(1, 2)
    assert r.one_half.when == date(2026, 10, 16)
    assert r.lawyer_check


def test_month_end_is_clamped():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)
    assert add_months(date(2024, 11, 15), 14) == date(2026, 1, 15)


def test_custody_after_today_is_refused():
    with pytest.raises(ValueError):
        calculate(one("IPC", "380"), date(2027, 1, 1), date(2026, 11, 2), True, False, False)


# ---------- source lines ----------

def test_source_line_is_read_from_knowledge():
    src = knowledge_source("How to work out the Section 479 dates")
    assert "Section 479" in src["source"]
    assert src["link"].startswith("https://")
