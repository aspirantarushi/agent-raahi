"""Home page: the landing screen, its sections, facts from knowledge/ only, no unprovable claims."""

import re

import pytest
from streamlit.testing.v1 import AppTest

import home
import knowledge


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setenv("RAAHI_START_SCREEN", "Home")
    app = AppTest.from_file("../app.py", default_timeout=20).run()
    assert not app.exception, app.exception[0].stack_trace
    return app


def page_html(app) -> str:
    return " ".join(m.value for m in app.markdown)


def test_home_is_the_landing_screen_with_every_section(at):
    html = page_html(at)
    for words in ["Listen. Ask. Refer.", "Lighting the way to legal aid.", 'id="how-it-works"', "How a case moves",
                  "Today", "With Agent Raahi", 'id="safety"', "Built to be safe", 'id="facts"',
                  "Facts from our verified files", 'id="learn-basics"', "Learn the basics", "footer"]:
        assert words in html, words
    assert 'href="tel:112"' in html and 'href="tel:15100"' in html
    assert len(re.findall(r'class="card"', html)) >= 4 + 6 + 3


def test_facts_come_word_for_word_from_knowledge_with_sources(at):
    html = page_html(at)
    for sentence, source in home.facts("en"):
        assert sentence in html and source.replace('"', "&quot;") in html
    for file, heading, english, _ in home.FACTS:
        assert english in " ".join(knowledge.get(file, heading).body.split())


def test_a_changed_knowledge_entry_stops_the_fact(monkeypatch):
    monkeypatch.setattr(home, "FACTS", [("cyber_fraud.md", "Call 1930 at once: the first hours matter most",
                                         "Report within 2 hours, always.", None)])
    with pytest.raises(ValueError, match="not found word for word"):
        home.facts()


def test_hindi_fact_used_where_a_hindi_entry_exists():
    hi = dict(home.facts("hi"))
    assert any(s.startswith("जितनी जल्दी हो सके") for s in hi)
    assert "Women, children and people in custody qualify whatever their income." in hi  # no Hindi entry: English


def test_no_testimonials_counts_or_unprovable_claims(at):
    import json
    from pathlib import Path
    en = json.loads((Path(__file__).resolve().parent.parent / "i18n" / "en.json").read_text(encoding="utf-8"))
    text = " ".join(v for k, v in en.items() if k.startswith(("home.", "app."))).lower()
    for claim in ["testimonial", "users", "trusted by", "guarantee", "%", "faster", "minutes", "thousands", "lakh"]:
        assert claim not in text, claim


def test_story_box_opens_step_1_of_new_case_with_the_story(at):
    at.text_area(key="home_story").set_value("The employer has not paid the worker for three months.")
    at.button(key="home-go").click().run()
    assert not at.exception
    assert at.session_state["screen"] == "New case" and at.radio(key="case_type").value == "Any case (start here)"
    assert at.text_area(key="g_notes").value == "The employer has not paid the worker for three months."


def test_mic_opens_new_case_with_voice(at):
    at.button(key="home-mic").click().run()
    assert at.session_state["screen"] == "New case"


def test_language_chips_and_start_a_case(at):
    at.button(key="home-lang-hi").click().run()
    assert "सुनें। पूछें। आगे भेजें।" in page_html(at)
    at.button(key="nav-start").click().run()
    assert at.session_state["screen"] == "New case"
