"""New case page fixes: the volunteer's tick-box checklist, "Going on for" matching the facts, and the
case card. Fake data only."""

from datetime import date

import casework
import general
import readiness


def facts(**kw):
    base = dict(person="the speaker's brother", what_happened=["The owner has not paid wages for three months."],
                timeline=[("30 September 2026", "Salary stopped being paid")], coming_dates=[],
                issues=[("employment_or_wages", "unpaid wages")], sections=[], documents_held=[], answers=[],
                still_to_ask=[], facts={"state": "Punjab"}, today="2026-11-06", outcome="his wages paid")
    base.update(kw)
    return general.GeneralFacts(**base)


def test_going_on_for_matches_the_facts():
    g = facts()
    assert casework.duration_text(g, date(2026, 11, 6)) == \
        "3 months, as the story says; 30 September 2026: salary stopped being paid"
    assert casework.duration_text(g, date(2026, 11, 6), "hi").startswith("3 महीने, कहानी के अनुसार")
    hinglish = facts(what_happened=["Malik ne teen mahine se salary nahi di."])
    assert casework.stated_period(hinglish) == (3, "month")
    ago = facts(what_happened=["The line was cut 5 weeks ago."], timeline=[("1 October 2026", "Connection cut")])
    assert casework.stated_period(ago) is None  # "5 weeks ago" is a date, not a period
    assert casework.duration_text(ago, date(2026, 11, 6)) == "about 5 weeks (since 1 October 2026: connection cut)"
    assert "3 months, as the story says" in general.summary_body(g)


def test_the_volunteer_decides_with_ticks():
    items = [readiness.Item("case_story", readiness.PRESENT), readiness.Item("case_documents", readiness.MISSING),
             readiness.Item("case_state", readiness.PRESENT)]
    final = readiness.with_ticks(items, {"case_story": True, "case_documents": True, "case_state": False})
    status = {i.key: (i.status, i.note) for i in final}
    assert status["case_documents"] == (readiness.PRESENT, "ticked by the volunteer")  # the volunteer knows best
    assert status["case_state"] == (readiness.UNCERTAIN, readiness.NOT_TICKED)          # unticked: a gap
    block = readiness.gaps_block(final, "en", reason="the state is confirmed at the next visit")
    assert "Sent with 1 item not ticked:" in block and "- State" in block  # sent on purpose, with a reason
    assert "Sent anyway because: the state is confirmed at the next visit" in block
    cannot = readiness.with_ticks([readiness.Item("case_documents", readiness.CANNOT, "office refused")],
                                  {"case_documents": False})
    assert cannot[0].status == readiness.CANNOT  # "Can't get this" (with a reason) is not a gap


def test_case_card_shows_the_code_large_and_no_finish_button():
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    panel = source.split("def current_case_panel")[1].split("\ndef ")[0]
    assert '<span class="code">' in panel and 'class="case-id"' in panel
    assert "intake-finish" not in panel  # "Finish intake" comes at the end of the flow, after sending


def test_a_date_the_ai_already_asks_about_is_not_asked_again():
    r = general.GeneralReading(person="x", what_happened=["Not paid."], timeline=[("30 September", "salary stopped")],
                               issues=[("employment_or_wages", "unpaid wages")], outcome="paid",
                               questions=["What is the full date of 30 September?"])
    qs = general.follow_up_questions(r)
    assert sum("30 September" in q for q in qs) == 1


def test_month_count_uses_the_average_month_length():
    # Found in the practice evaluation: 2 January 2025 to 9 November 2026 (676 days) showed "about 23 months"
    g = facts(what_happened=["He was arrested."], timeline=[("2 January 2025", "Arrested")])
    assert casework.duration(g, date(2026, 11, 9)) == "about 22 months"


def test_app_names_are_not_flagged_as_names():
    # Found in the practice evaluation: "WhatsApp" was flagged as a possible person's name
    notes = "The worker has some WhatsApp messages and a Paytm receipt from the contractor."
    assert general.possible_names("Has: WhatsApp messages; Paytm receipt", notes) == []
