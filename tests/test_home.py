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
    """The page's HTML: every markdown block, plus the facts carousel (its own small page)."""
    return " ".join([m.value for m in app.markdown] + [f.proto.srcdoc for f in app.get("iframe")])


def carousel(app) -> str:
    [frame] = app.get("iframe")
    return frame.proto.srcdoc


def test_home_is_the_landing_screen_with_every_section(at):
    html = page_html(at)
    for words in ["Listen. Ask. Refer.", "<h1>Lighting the way to legal aid.</h1>", 'id="how-it-works"',
                  "How a case moves", "Today", "With Agent Raahi", 'id="safety"', "Built to be safe", 'id="facts"',
                  "Facts from our verified files", 'id="learn-basics"', "Learn the basics", "footer"]:
        assert words in html, words
    blocks = " ".join(m.value for m in at.markdown)
    order = [blocks.index(x) for x in ['id="how-it-works"', 'id="what-changes"', 'id="safety"', 'id="learn-basics"',
                                       "<footer"]]
    assert order == sorted(order)  # the sections in the reference design's order
    assert 'id="facts"' in carousel(at)  # the facts carousel, between Safety and Learn (checked on screenshots)
    assert 'href="tel:112"' in html and 'href="tel:15100"' in html
    assert len(re.findall(r'class="card"', html)) == 5 + 6  # five stages, six safety cards
    assert len([b for b in at.button if str(b.key).startswith("home-learn-")]) == 2  # cyber fraud: coming soon
    assert "Practice: test yourself" in html  # the 4th card


def test_tagline_is_the_main_heading_and_the_kicker_is_smaller(at):
    html = page_html(at)
    assert '<div class="kicker">Listen. Ask. Refer.</div><h1>Lighting the way to legal aid.</h1>' in html


def test_built_to_be_safe_cards_have_icons_and_the_exact_text(at):
    html = page_html(at)
    for icon, title, text in [
        ("verified_user", "A lawyer approves every draft.", "Nothing is sent or filed until the supervising "
         "lawyer approves it. No one can approve their own work."),
        ("menu_book", "Every legal point has a source.", "Points come from our verified files or from official "
         "websites. Anything not yet checked is labelled until the supervisor approves it."),
        ("lock", "Private by design.", "Phone and Aadhaar numbers are removed before the AI sees anything. The "
         "person&#x27;s story is never stored, and volunteer notes must not include names."),
        ("help", "It stops when facts don&#x27;t add up.", "If details contradict each other or are missing, it says "
         "&quot;Cannot conclude yet&quot; and asks, instead of guessing."),
        ("balance", "No predictions.", "It never predicts outcomes, bail chances or risk, and never promises release "
         "or recovery."),
        ("rule", "Works even without AI.", "Dates and eligibility follow fixed, tested rules, so the core works even "
         "when the AI is down."),
    ]:
        assert f'<span class="mi" aria-hidden="true">{icon}</span><h3>{title}</h3><p>{text}</p>' in html, title


def test_facts_band_source_names_are_links_in_italics(at):
    html = page_html(at)
    for _, source, link in home.facts("en"):
        name = source.replace("&", "&amp;").replace(chr(34), "&quot;")
        href = link.replace("&", "&amp;")
        if link == "none":  # broken, with no working official copy: the name only, never a dead link
            assert f"<em>Source: {name}</em>" in html
            continue
        assert (f'<em>Source: <a href="{href}" target="_blank" rel="noopener noreferrer">{name}</a></em>') in html
        assert f"({link})" not in html  # no web address in brackets


def test_hero_logo_helplines_and_start_icon(at):
    html = page_html(at)
    assert html.index('<div class="hero-brand"><svg width="72"') < html.index('<span class="badge">')
    lines = html[html.index('<div class="helpline">'):]
    assert lines.index("Free and open source.") < lines.index('href="tel:112"')
    assert '<a class="danger" href="tel:112"><span class="mi" aria-hidden="true">call</span>' in lines
    assert '<a href="tel:15100"><span class="mi" aria-hidden="true">support_agent</span>' in lines
    assert at.button(key="home-start").icon == ":material/note_add:"


def test_learn_section_four_cards_with_icons(at):
    html = page_html(at)
    assert '<section id="learn-basics" class="sec center learn">' in html
    for icon in ["volunteer_activism", "gavel", "quiz"]:
        assert f'<div class="card guide"><span class="mi" aria-hidden="true">{icon}</span><h3>' in html
    assert '<div class="card guide soon-card"><span class="mi" aria-hidden="true">phishing</span><span class="soon">Coming soon</span>' in html
    assert at.button(key="nav-practice").icon == ":material/quiz:"
    at.button(key="nav-practice").click().run()
    assert at.session_state["screen"] == "Practice"   # public, like Learn; the timing tool is on Supervisor


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
    for sentence, source, link in home.facts("en"):
        assert sentence.replace("'", "&#x27;") in html and source.replace('"', "&quot;") in html
    for file, heading, basis, _, _ in home.FACTS:  # every card names the exact sentences it is based on
        body = " ".join(knowledge.get(file, heading).body.split())
        assert basis and all(" ".join(b.split()) in body for b in basis), heading


def test_a_changed_knowledge_entry_stops_the_fact(monkeypatch):
    monkeypatch.setattr(home, "FACTS", [("cyber_fraud.md", "Call 1930 at once: report immediately",
                                         ["Report within 2 hours, always."], "Report within 2 hours.", None)])
    with pytest.raises(ValueError, match="not found word for word"):
        home.facts()


def test_every_fact_has_plain_english_and_hindi():
    en, hi = home.facts("en"), home.facts("hi")
    assert len(en) == len(hi) == 6  # legal aid and Section 479 only
    assert not any("1930" in e or "arrest over a video call" in e for e, _, _ in en)
    for (e, se, le), (h, sh, lh) in zip(en, hi):
        assert re.search(r"[ऀ-ॿ]", h) and not re.search(r"[ऀ-ॿ]", e)
        assert (se, le) == (sh, lh) and (le.startswith("https://") or le == "none")  # the same source and link in both
    # a link that is broken with no working official copy shows the source name only (Khatri II)
    assert [le for _, _, le in en].count("none") == 1
    assert "death or life imprisonment" in en[2][0]  # Section 479: the exception from knowledge/ is stated
    assert "case to file or defend" in en[0][0]      # Section 12: free legal aid is for a case


def test_facts_carousel_controls(at):
    page = carousel(at)
    assert page.count('class="slide"') == 6 and 'aria-roledescription="carousel"' in page
    for label in ("Previous fact", "Next fact", "Pause the facts", "Fact 1 of 6"):
        assert label in page
    assert "prefers-reduced-motion: reduce" in page and "7000" in page   # no motion when asked; 7 seconds
    assert "scroll-snap-type: x mandatory" in page                       # swipe on phones
    assert "mouseenter" in page and "touchstart" in page                 # pause on hover or tap
    assert page.count('target="_blank" rel="noopener noreferrer"') == 5  # one source shown by name only and "<em>Source: <a" in page
    at.radio(key="ui_lang").set_value("hi").run()
    assert "पिछला तथ्य" in carousel(at) and "<em>स्रोत: <a" in carousel(at)


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


def test_with_agent_raahi_box_lists_five_features_and_no_example_case():
    import ui
    import lang
    for code in ("en", "hi"):
        t = (lambda k: lang.t(k, code))
        page = ui.compare({"eyebrow": t("home.today_t"), "title": t("home.today_h"), "chips": [], "text": ""},
                          {"eyebrow": t("home.raahi_t"), "title": t("home.raahi_h"),
                           "rows": [("qr_code_2", t(f"home.raahi_f{i}_b"), t(f"home.raahi_f{i}")) for i in range(1, 6)]})
        assert page.count("<li>") == 5 and 'class="mini"' not in page and "progress" not in page
        assert f"<b>{t('home.raahi_f1_b')}</b>" in page
    assert lang.t("home.raahi_h", "en") == "One case file, from first story to follow-up."
    assert lang.t("home.raahi_f5_b", "en") == "Follow-up dates:"


def test_footer_is_one_short_line_with_the_privacy_link():
    import ui
    import lang
    t = (lambda k: lang.t(k, "en"))
    page = ui.footer(t("app.name"), [t("footer.open_source"), t("footer.built_on")], t("footer.privacy"))
    assert page.count("<span class=\"fi\">") == 4 and "Practice data only" not in page
    assert 'href="https://github.com/aspirantarushi/agent-raahi/blob/main/docs/PRIVACY.md" target="_blank"' in page
    assert "Open source (MIT licence)" in page and "Built on AgentFoundry" in page
