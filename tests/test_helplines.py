"""The two helplines (112 and 15100) on every screen, in the Home page style: each with its icon, as
tap-to-call links, right under the page heading. English and Hindi. Practice passwords only."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import lang

ROOT = Path(__file__).resolve().parent.parent
CLINIC, SUPERVISOR = "practice-pass-123", "sup-pass-9"


def walk(node):
    """Every element on the screen, in the order it is drawn."""
    children = getattr(node, "children", None)
    if children is None:
        yield node
        return
    for child in children.values():
        yield from walk(child)


def screen(at):
    return list(walk(at.main))


def helpline_blocks(at):
    return [e for e in screen(at) if getattr(e, "type", "") == "markdown" and 'class="helpline' in str(e.value)]


def check_under_heading(at, code):
    ok = not at.exception
    assert ok, at.exception[0].stack_trace
    items = screen(at)
    title = next(i for i, e in enumerate(items) if getattr(e, "type", "") == "title")
    after = items[title + 1]
    assert getattr(after, "type", "") == "markdown" and 'class="helpline helpline-page"' in after.value
    html = after.value
    assert 'href="tel:112"' in html and 'href="tel:15100"' in html             # tap to call
    assert '>call</span>' in html and '>support_agent</span>' in html           # phone icon, support icon
    assert lang.t("safety.bar112", code) in html and lang.t("safety.bar15100", code) in html
    assert len(helpline_blocks(at)) == 1                                       # once per screen
    assert "safety-bar" not in " ".join(str(getattr(e, "value", "")) for e in items)  # the old pill bar is gone


def open_app(monkeypatch, screen_name, code, **state):
    monkeypatch.setenv("CLINIC_PASSCODE", CLINIC)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", SUPERVISOR)
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = screen_name
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    if code != "en":
        at.radio(key="ui_lang").set_value(code).run()
    return at


SIGNED_IN = {"clinic_ok": True, "volunteer": "VA"}


@pytest.mark.parametrize("code", ["en", "hi"])
@pytest.mark.parametrize("screen_name, state, title_key", [
    ("New case", {}, "gate.title"),                       # Volunteer sign-in
    ("My cases", {}, "gate.title"),
    ("Supervisor", {}, "ui.sup.sign_in_title"),           # Supervisor sign-in
    ("New case", SIGNED_IN, "ui.new_case.title"),
    ("My cases", SIGNED_IN, "ui.cases.title"),
    ("Supervisor", {"supervisor_ok": True, **SIGNED_IN}, "ui.sup.title"),
    ("Learn", {}, "ui.learn.title"),
])
def test_helplines_under_every_page_heading(monkeypatch, code, screen_name, state, title_key):
    at = open_app(monkeypatch, screen_name, code, **state)
    assert at.title[0].value == lang.t(title_key, code)
    check_under_heading(at, code)


@pytest.mark.parametrize("code", ["en", "hi"])
def test_home_keeps_its_own_helplines_once(monkeypatch, code):
    at = open_app(monkeypatch, "Home", code)
    assert not at.exception
    [block] = helpline_blocks(at)
    assert 'class="helpline"' in block.value and 'href="tel:112"' in block.value and ">call</span>" in block.value


def test_page_helplines_use_the_home_style():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    assert ".safety-bar" not in css
    assert ".helpline a {" in css and ".helpline a.danger" in css   # the same rules for Home and every page
    assert ".helpline-page" in css
