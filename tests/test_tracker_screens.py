"""The shared case tracker on screen: two practice volunteers continue one case, a contradiction,
the clinic sign-in, the slip, the QR link and the tracker list. Practice data only."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import llm
import store
import tracker
import ui
from test_general import MODEL, answer, yn

STORY_A = "Practice case. A worker from Bihar was not paid wages for three months."
STORY_B = "Practice case. She now lives in Uttar Pradesh with her sister."
ANSWER_A = answer(
    what_happened=["The worker was not paid wages for three months."],
    issues=[{"category": "other", "name": "unpaid wages"}],
    state={"value": "Bihar", "quote": "A worker from Bihar"},
    questions_to_ask=["Does the worker have a written contract?"],
)
ANSWER_B = answer(
    what_happened=["The person now lives with her sister."],
    issues=[{"category": "other", "name": "unpaid wages"}],
    state={"value": "Uttar Pradesh", "quote": "She now lives in Uttar Pradesh"},
    woman=yn("yes", "She now lives"),
)


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def button(at, label):
    return next(b for b in at.button if b.label == label)


def texts(at):
    return " ".join([m.value for m in at.markdown] + [e.value for e in at.error] + [c.value for c in at.caption]
                    + [s.value for s in at.success] + [w.value for w in at.warning])


@pytest.fixture
def pretend_ai(monkeypatch):
    answers = {STORY_A: ANSWER_A, STORY_B: ANSWER_B}
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", known=None: llm.NotesReading(answers[notes], notes, {}, MODEL))


def as_volunteer(name):
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    ok(at)
    at.text_input(key="volunteer").set_value(name).run()
    return at


def volunteer_a_starts():
    at = as_volunteer("Volunteer A")
    at.text_area(key="g_notes").set_value(STORY_A)
    button(at, "Read the story").click().run()
    ok(at)
    case_id = at.session_state["case_id"]
    record = tracker.load(case_id)
    assert record["created_by"] == "Volunteer A"
    assert any("Case slip ready (code " + record["code"] in s.value for s in at.success)
    # The AI's question, then what the person wants (the story doesn't say), then the first eligibility
    # question (state is already known from the story)
    assert "Question 1 of" in texts(at)
    at.text_input(key="gq-0").set_value("No written contract")
    button(at, "Next").click().run()
    assert "What does the person want to happen?" in texts(at)
    at.text_input(key="gq-1").set_value("To get the unpaid wages")
    button(at, "Next").click().run()
    assert "Is the person needing help in jail or police custody now?" in texts(at)
    at.radio(key="ge-in_custody").set_value("No")
    button(at, "Next").click().run()
    ok(at)
    assert "Is the person needing help a woman?" in texts(at)   # Volunteer A stops here
    return case_id, record["code"]


def test_second_volunteer_continues_without_re_asking(pretend_ai):
    case_id, code = volunteer_a_starts()
    saved = tracker.load(case_id)
    assert tracker.known(saved) == {"state": "Bihar", "in_custody": False}
    assert saved["answers"] == [["Does the worker have a written contract?", "No written contract"],
                                ["What does the person want to happen? (the outcome they hope for)",
                                 "To get the unpaid wages"]]

    at = as_volunteer("Volunteer B")
    at.text_input(key="cont-code-new").set_value(code.lower())
    button(at, "Open the case").click().run()
    ok(at)
    assert at.session_state["case_id"] == case_id
    shown = texts(at)
    # Not asked again: state, custody, or the AI's question already answered
    assert "Is the person needing help a woman?" in shown
    assert "jail or police custody now?" not in shown and "Which state" not in shown
    assert "Does the worker have a written contract?" not in shown
    # The case file shows what is known, by whom
    assert "Bihar" in shown and "added" in shown and "Volunteer A" in shown
    at.radio(key="ge-woman").set_value("Yes")
    button(at, "Next").click().run()
    ok(at)
    at.button(key="q-not-needed-go").click().run()  # legal aid decided: the app says so, the volunteer continues
    facts = tracker.load(case_id)["facts"]
    assert facts["woman"]["by"] == "Volunteer B" and facts["state"]["by"] == "Volunteer A"
    assert at.session_state["shown_drafts"], "eligible as a woman: the summary is shown with no more questions"
    assert "The worker was not paid wages for three months." in at.session_state["shown_drafts"][0]


def test_a_contradiction_stops_the_summary_until_resolved(pretend_ai):
    case_id, code = volunteer_a_starts()
    at = as_volunteer("Volunteer B")
    at.text_input(key="cont-code-new").set_value(code)
    button(at, "Open the case").click().run()
    at.text_area(key="g_notes").set_value(STORY_B)
    button(at, "Read the story").click().run()
    ok(at)
    errors = " ".join(e.value for e in at.error)
    assert "Cannot conclude yet" in errors and "Bihar" in errors and "Uttar Pradesh" in errors
    assert not at.session_state["shown_drafts"]                                          # no summary or draft while it is open
    assert tracker.load(case_id)["facts"]["state"]["value"] == "Bihar"
    button(at, "Use the new value (Uttar Pradesh)").click().run()
    ok(at)
    assert "Cannot conclude yet" not in " ".join(e.value for e in at.error)
    record = tracker.load(case_id)
    assert record["facts"]["state"]["value"] == "Uttar Pradesh" and not tracker.open_conflicts(record)
    assert record["facts"]["woman"]["value"] is True            # the new, uncontested fact was added
    assert "The person now lives with her sister." in record["summary"]


def test_sending_uses_the_slip_case_number(pretend_ai, monkeypatch, tmp_path):
    case_id, code = volunteer_a_starts()
    at = as_volunteer("Volunteer A")
    at.text_input(key="cont-code-new").set_value(code)
    button(at, "Open the case").click().run()
    at.radio(key="ge-woman").set_value("Yes")
    button(at, "Next").click().run()
    at.button(key="q-not-needed-go").click().run()
    if any(t.key == "g_send_reason" for t in at.text_input):  # unticked items: a short reason is needed
        at.text_input(key="g_send_reason").set_value("practice: the rest is collected at the next visit")
    at.checkbox(key="g_checked").check().run()
    next(b for b in at.button if b.label.startswith("Send to supervisor")).click().run()
    ok(at)
    assert at.session_state["gen_sent"] == case_id
    assert tracker.status_of(case_id) == store.WAITING
    assert store.get_pending(case_id)["sent_by"] == "Volunteer A"


def test_clinic_passcode_and_name_are_needed(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    ok(at)
    assert at.title[0].value == "Volunteer sign-in"
    assert not any(t.key == "g_notes" for t in at.text_area)           # nothing of New case is shown
    at.text_input(key="gate-pass").set_value("practice-pass-123")
    button(at, "Sign in").click().run()
    assert "Type your name or initials" in at.error[0].value
    at.text_input(key="gate-pass").set_value("wrong")
    at.text_input(key="gate-name").set_value("RK")
    button(at, "Sign in").click().run()
    assert "not right" in at.error[0].value
    at.text_input(key="gate-pass").set_value("practice-pass-123")
    button(at, "Sign in").click().run()
    ok(at)
    assert at.title[0].value == "New case" and at.session_state["volunteer"] == "RK"
    assert "Signed in as RK" in texts(at)


def test_home_and_learn_need_no_passcode(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Home"
    at.run()
    ok(at)
    assert any(b.key == "home-scan" for b in at.button)               # "Scan QR code" on Home
    at.button(key="home-continue").click().run()                      # "Continue a case" opens the code box
    assert any(b.key == "cont-go-home" for b in at.button)


def test_qr_link_opens_the_case(pretend_ai):
    case_id, code = volunteer_a_starts()
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.query_params["code"] = code
    at.run()
    ok(at)
    assert at.session_state["case_id"] == case_id


def test_unknown_code_says_so(pretend_ai):
    at = as_volunteer("Volunteer B")
    at.text_input(key="cont-code-new").set_value("ZZZZZZ")
    button(at, "Open the case").click().run()
    assert any("No case has this code" in e.value for e in at.error)


def test_visit_log_and_camp_from_the_screen(pretend_ai):
    case_id, _ = volunteer_a_starts()
    at = as_volunteer("Volunteer A")
    at.session_state["case_id"] = case_id
    at.run()
    at.button(key="case-tab-visit").click().run()  # the panels are closed until chosen
    at.selectbox(key=f"vis-how-{case_id}").set_value("phone call")
    at.text_area(key=f"vis-learned-{case_id}").set_value("Wages unpaid since June")
    at.text_input(key=f"vis-next-{case_id}").set_value("Bring the attendance photos")
    button(at, "Save the visit").click().run()
    ok(at)
    visit = tracker.load(case_id)["visits"][-1]
    assert (visit["how"], visit["by"], visit["next_step"]) == ("phone call", "Volunteer A", "Bring the attendance photos")


def test_todays_camp_button_chip_and_end(pretend_ai):
    at = as_volunteer("Volunteer A")
    assert not any(t.key == "camp-today-village" for t in at.text_input)  # no silent fields
    at.button(key="camp-start").click().run()
    at.button(key="camp-save-today").click().run()
    assert any("village" in e.value for e in at.error)                   # both are needed
    at.text_input(key="camp-today-village").set_value("Rampur")
    at.text_input(key="camp-today-district").set_value("Patna")
    at.button(key="camp-save-today").click().run()
    ok(at)
    assert "Camp: Rampur, Patna · " in texts(at)
    at.text_area(key="g_notes").set_value(STORY_A)
    button(at, "Read the story").click().run()
    assert tracker.load(at.session_state["case_id"])["camp"]["village"] == "Rampur"  # the new case is tagged
    at.button(key="camp-end").click().run()
    assert "Camp: Rampur" not in texts(at) and at.button(key="camp-start")


def test_finish_intake_on_screen(pretend_ai):
    case_id, _ = volunteer_a_starts()
    at = as_volunteer("Volunteer A")
    at.session_state["case_id"] = case_id
    at.session_state["gen_sent"] = case_id  # "Finish intake" is at the end of the flow, after sending
    at.run()
    at.button(key="intake-finish").click().run()
    ok(at)
    assert tracker.status_of(case_id) == tracker.INTAKE_DONE
    assert any(s.value.startswith("Intake finished. Next step:") for s in at.success)
    assert not any(b.key == "intake-finish" for b in at.button)


def test_tracker_list_filters_and_overdue(pretend_ai):
    case_id, _ = volunteer_a_starts()
    tracker.add_visit(case_id, date.today(), "Volunteer A", "camp visit", next_step="Collect the FIR copy",
                      next_due=date(2020, 1, 1))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "My cases"
    at.run()
    ok(at)
    assert at.title[0].value == "Case tracker"
    table = next(m.value for m in at.markdown if 'class="tracker"' in m.value)
    row = next(r for r in table.split("<tr") if case_id in r)
    assert 'class="overdue"' in row and "Overdue" in row and "Collect the FIR copy" in row
    assert "Intake not finished" in row
    at.checkbox(key="tr-hide-intake").check().run()
    table = next(m.value for m in at.markdown if 'class="tracker"' in m.value)
    assert case_id not in table
    at.checkbox(key="tr-hide-intake").uncheck().run()
    at.selectbox(key="tr-volunteer").set_value("Volunteer A").run()
    table = next(m.value for m in at.markdown if 'class="tracker"' in m.value)
    assert case_id in table


def test_slip_page_shows_nothing_about_the_case(pretend_ai):
    case_id, code = volunteer_a_starts()
    record = tracker.load(case_id)
    lines = tracker.slip_lines(record, "Practice clinic")
    page = ui.slip_page(lines, tracker.qr_png_data_uri("https://example.app", code))
    printable = ui.slip_page(lines, "data:image/png;base64,AA", print_only=True)
    for html in (page, printable):
        assert code in html and case_id in html and "Practice clinic" in html
        assert "Bring this next time" in html and "अगली बार यह साथ लाएँ" in html
        assert "112" in html and "15100" in html
        for word in ("wages", "unpaid", "Bihar", "General", "Any case", "worker"):
            assert word not in html
