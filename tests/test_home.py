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
    for words in ["Listen. Ask. Refer.", "<h1>Lighting the way to legal aid.</h1>", 'id="how-it-works"',
                  "How a case moves", "Today", "With Agent Raahi", 'id="safety"', "Built to be safe", 'id="facts"',
                  "Facts from our verified files", 'id="learn-basics"', "Learn the basics", "footer"]:
        assert words in html, words
    order = [html.index(x) for x in ['id="how-it-works"', 'id="what-changes"', 'id="safety"', 'id="facts"',
                                     'id="learn-basics"', "<footer"]]
    assert order == sorted(order)  # the sections in the reference design's order
    assert 'href="tel:112"' in html and 'href="tel:15100"' in html
    assert len(re.findall(r'class="card"', html)) == 4 + 6
    assert len([b for b in at.button if str(b.key).startswith("home-learn-")]) == 3


def test_tagline_is_the_main_heading_and_the_kicker_is_smaller(at):
    html = page_html(at)
    assert '<div class="kicker">Listen. Ask. Refer.</div><h1>Lighting the way to legal aid.</h1>' in html


def test_built_to_be_safe_cards_have_icons_and_the_exact_text(at):
    html = page_html(at)
    for icon, title, text in [
        ("verified_user", "A lawyer approves every draft.", "Nothing is saved, sent or filed until the supervising "
         "lawyer approves it. No one can approve their own work."),
        ("menu_book", "Every legal point has a source.", "Information comes only from checked sources or research "
         "the supervisor has approved, each shown with its reference."),
        ("lock", "Private by design.", "Phone and Aadhaar numbers are removed before the AI sees anything. Names "
         "and notes are never stored."),
        ("help", "It stops when facts don&#x27;t add up.", "If details contradict each other or are missing, it says "
         "&quot;Cannot conclude yet&quot; and asks, instead of guessing."),
        ("balance", "No predictions.", "It never predicts outcomes, bail chances or risk, and never promises release "
         "or recovery."),
        ("rule", "Works even without AI.", "Dates and eligibility follow fixed, tested rules, so the core works even "
         "when the AI is down."),
    ]:
        assert f'<span class="mi" aria-hidden="true">{icon}</span><h3>{title}</h3><p>{text}</p>' in html, title


def test_facts_band_sources_in_italics(at):
    html = page_html(at)
    for _, source in home.facts("en"):
        assert f"<em>{source.replace('&', '&amp;').replace(chr(34), '&quot;')}</em>" in html


def test_no_emoji_on_screen_or_in_the_screen_text():
    import json
    from pathlib import Path
    emoji = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FA\uFE0F]")
    root = Path(__file__).resolve().parent.parent
    for name in ("en", "hi"):
        strings = json.loads((root / "i18n" / f"{name}.json").read_text(encoding="utf-8"))
        assert not [k for k, v in strings.items() if emoji.search(v)], name
    for name in ("app.py", "ui.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert not emoji.search(source), name
        assert not re.search(r"\\U0001F|\\u2[67][0-9a-fA-F]{2}|\\u25cb|\\ufe0f", source), name  # written as escapes


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


def test_one_language_switch_and_start_a_case(at):
    assert not [b for b in at.button if str(b.key).startswith("home-lang-")]  # no big language buttons
    assert [r.key for r in at.radio if r.key == "ui_lang"] == ["ui_lang"]    # one EN · हिंदी switch
    at.radio(key="ui_lang").set_value("hi").run()
    assert "सुनें। पूछें। आगे भेजें।" in page_html(at)
    at.button(key="nav-start").click().run()
    assert at.session_state["screen"] == "New case"


def test_top_navigation_and_no_sidebar(at):
    assert not at.sidebar.children if hasattr(at.sidebar, "children") else True
    assert len(at.sidebar.radio) == 0 and len(at.sidebar.markdown) == 0 and len(at.selectbox) == 0
    for key, screen in [("nav-new", "New case"), ("nav-tracker", "My cases"), ("nav-learn", "Learn"),
                        ("nav-supervisor", "Supervisor"), ("nav-home", "Home")]:
        at.button(key=key).click().run()
        assert not at.exception and at.session_state["screen"] == screen


def test_start_a_new_case_and_continue_a_case(at):
    at.button(key="home-continue").click().run()
    assert at.text_input(key="cont-code-home")
    at.button(key="home-scan").click().run()  # the scanner replaces the code box
    assert not any(t.key == "cont-code-home" for t in at.text_input)
    at.button(key="home-start").click().run()
    assert at.session_state["screen"] == "New case" and at.radio(key="case_type").value == "Any case (start here)"
