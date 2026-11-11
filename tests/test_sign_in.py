"""Sign-in: "Supervisor sign-in" (the supervisor password only) and "Volunteer sign-in" (the clinic
passcode and a name). Practice passwords only."""

import pytest
from streamlit.testing.v1 import AppTest

CLINIC, SUPERVISOR = "practice-pass-123", "sup-pass-9"
WRONG_PAGE = "This is the volunteer sign-in. Supervisors: use the Supervisor page."


@pytest.fixture
def passwords(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", CLINIC)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", SUPERVISOR)


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def open_screen(screen, at=None):
    at = at or AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = screen
    return at.run()


def boxes(at):
    return {t.key for t in at.text_input}


def supervisor_signs_in(at, password=SUPERVISOR):
    at.text_input(key="sup-pass").set_value(password)
    at.button(key="sup-go").click().run()
    ok(at)
    return at


def test_supervisor_menu_opens_supervisor_sign_in_with_only_the_password(passwords):
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.button(key="nav-supervisor").click().run()  # the Supervisor menu, not signed in as a volunteer
    ok(at)
    assert at.title[0].value == "Supervisor sign-in"
    assert boxes(at) == {"sup-pass"}  # no clinic passcode, no name
    assert "gate-pass" not in boxes(at) and "gate-name" not in boxes(at)


def test_correct_supervisor_password_also_opens_the_clinic(passwords):
    at = supervisor_signs_in(open_screen("Supervisor"))
    assert at.session_state["supervisor_ok"] is True and at.session_state["clinic_ok"] is True
    assert at.title[0].value == "Supervisor" and "Signed in as supervisor." in [s.value for s in at.success]
    at = open_screen("New case", at)  # no volunteer sign-in needed in this session
    ok(at)
    assert at.title[0].value == "New case"
    assert "gate-pass" not in boxes(at)
    assert at.session_state["volunteer"] == "Supervisor"  # saved with what the supervisor does


def test_wrong_supervisor_password_gives_no_access(passwords):
    at = supervisor_signs_in(open_screen("Supervisor"), "wrong")
    assert at.error[0].value == "Wrong password."
    assert "supervisor_ok" not in at.session_state and "clinic_ok" not in at.session_state
    at = open_screen("New case", at)
    assert at.title[0].value == "Volunteer sign-in"


def test_clinic_passcode_does_not_open_the_supervisor_page(passwords):
    at = supervisor_signs_in(open_screen("Supervisor"), CLINIC)
    assert at.error[0].value == "Wrong password."
    assert "supervisor_ok" not in at.session_state


def test_other_pages_open_volunteer_sign_in(passwords):
    at = open_screen("New case")
    ok(at)
    assert at.title[0].value == "Volunteer sign-in"
    assert {"gate-pass", "gate-name"} <= boxes(at)


@pytest.mark.parametrize("name", ["", "RK"])
def test_supervisor_password_in_the_volunteer_box_points_to_the_supervisor_page(passwords, name):
    at = open_screen("New case")
    at.text_input(key="gate-pass").set_value(f" {SUPERVISOR} ")  # spaces copied in are ignored here too
    at.text_input(key="gate-name").set_value(name)
    at.button(key="gate-go").click().run()
    ok(at)
    assert at.error[0].value == WRONG_PAGE
    assert "clinic_ok" not in at.session_state and "supervisor_ok" not in at.session_state
    assert at.title[0].value == "Volunteer sign-in"


def test_supervisor_sign_out_ends_the_clinic_access_it_gave(passwords):
    at = supervisor_signs_in(open_screen("Supervisor"))
    at.button(key="sup-out").click().run()
    ok(at)
    assert at.title[0].value == "Supervisor sign-in"
    assert "clinic_ok" not in at.session_state and "volunteer" not in at.session_state
    at = open_screen("New case", at)
    assert at.title[0].value == "Volunteer sign-in"


def test_a_signed_in_volunteer_keeps_their_name_and_access(passwords):
    at = open_screen("New case")
    at.text_input(key="gate-pass").set_value(CLINIC)
    at.text_input(key="gate-name").set_value("RK")
    at.button(key="gate-go").click().run()
    at = supervisor_signs_in(open_screen("Supervisor", at))
    assert at.session_state["volunteer"] == "RK"
    at.button(key="sup-out").click().run()  # signing out as supervisor leaves the volunteer signed in
    assert at.session_state["clinic_ok"] is True and at.session_state["volunteer"] == "RK"
    at = open_screen("New case", at)
    assert at.title[0].value == "New case"


def test_supervisor_page_without_a_password_set(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", CLINIC)
    monkeypatch.delenv("SUPERVISOR_PASSWORD", raising=False)
    at = open_screen("Supervisor")
    ok(at)
    assert at.title[0].value == "Supervisor sign-in"
    assert "SUPERVISOR_PASSWORD" in at.warning[0].value and "sup-pass" not in boxes(at)
    at = open_screen("New case")
    at.text_input(key="gate-pass").set_value(CLINIC)
    at.text_input(key="gate-name").set_value("RK")
    at.button(key="gate-go").click().run()  # the volunteer sign-in still works
    assert at.session_state["clinic_ok"] is True


def test_enter_signs_in_on_both_pages():
    # Both sign-ins are forms that Enter submits (AppTest can't press Enter, so the code is checked)
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert 'st.form("sup-form", enter_to_submit=True' in source
    assert 'st.form("gate-form", enter_to_submit=True' in source


def test_supervisor_password_with_spaces_opens_the_clinic(passwords):
    at = supervisor_signs_in(open_screen("Supervisor"), f"  {SUPERVISOR} ")
    assert at.session_state["supervisor_ok"] is True and at.session_state["clinic_ok"] is True
