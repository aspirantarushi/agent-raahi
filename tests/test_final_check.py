"""Prompt 8, final check: a rate of pay is never a period ("Rs 600 a day"), and a story that mentions jail or
arrest is never read as "not in custody". Fake practice data only."""

import casework
import general
from test_new_case_fixes import facts as make_facts


def period(line):
    return casework.stated_period(make_facts(what_happened=[line], issues=[]))


def test_a_rate_is_not_a_period():
    assert period("He earned Rs 600 a day at the construction site.") is None
    assert period("₹500 per month was promised.") is None
    assert period("Do sau rupaye din milte the.") is None
    assert period("A day later the contractor left.") is None             # "a day" alone is not a period
    assert period("They were not paid for a day.") == (1, "day")
    assert period("Teen mahine se paisa nahi mila.") == (3, "month")
    assert period("Pichhle ek saal se pension band hai.") == (1, "year")


def test_going_on_for_falls_back_to_the_first_dated_event():
    from datetime import date
    g = make_facts(what_happened=["The contractor paid Rs 600 a day until August 2026, then stopped paying."],
                   timeline=[("August 2026", "The contractor stopped paying wages")], issues=[])
    text = casework.duration_text(g, date(2026, 11, 14))
    assert "1 day" not in text and "August 2026" in text and "as the story says" not in text


def test_jail_in_the_story_is_never_read_as_not_in_custody():
    story = "Mera bhai 15 March 2024 se Patna jail mein hai. Uski koi zamanat nahi hui."
    r = general.check_general_answer({"in_custody": {"value": "no", "quote": "Uski koi zamanat nahi hui"}}, story)
    assert "in_custody" not in r.facts and "in_custody" in r.dropped    # unknown: the volunteer is asked
    hindi = "भाई को 15 मार्च 2024 को गिरफ़्तार किया गया था और वह जेल में है।"
    r = general.check_general_answer({"in_custody": {"value": "no", "quote": "भाई को 15 मार्च 2024 को गिरफ़्तार किया गया था"}}, hindi)
    assert "in_custody" not in r.facts
    # with no custody word in the story, "no" is kept as it is
    r = general.check_general_answer({"in_custody": {"value": "no", "quote": "bijli kaat di"}}, "Kisan ki bijli kaat di.")
    assert r.facts["in_custody"] is False


def test_camp_dates_are_written_out():
    import tracker
    assert tracker.camp_label({"village": "Harpur", "district": "Vaishali", "date": "2026-11-13"}) == \
        "Harpur, Vaishali (13 November 2026)"


def test_a_bare_wants_is_trimmed_from_the_request():
    assert casework.request_text("wants his money") == "his money"            # evaluation case 9: "I request: wants …"
    assert casework.request_text("Wages for three months") == "wages for three months"
