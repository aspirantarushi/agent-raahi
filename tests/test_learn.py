"""The Learn page: the three guides from learner/, with the key points and their sources from the
verified knowledge files (Hindi from knowledge_hi/ where it exists); Home opens each guide."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import guides
import knowledge
import lang

ROOT = Path(__file__).resolve().parent.parent


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def open_learn(guide=None, code="en"):
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Learn"
    if guide:
        at.session_state["learn_guide"] = guide
    at.run()
    if code != "en":
        at.radio(key="ui_lang").set_value(code).run()
    ok(at)
    return at


def words(at):
    return " ".join(str(e.value) for e in list(at.markdown) + list(at.caption))


@pytest.mark.parametrize("guide", guides.GUIDES, ids=lambda g: g.key)
def test_each_guide_is_read_from_its_files(guide):
    c = guides.content(guide.key)
    text = (ROOT / "learner" / guide.learner_file).read_text(encoding="utf-8")
    assert c.explainer and c.explainer in text  # exactly as written
    assert len(c.quiz) == 10 and all(q.answer and q.options for q in c.quiz)
    assert [t for t, _ in c.practice] == ["Practice case 1 (basics)", "Practice case 2 (advanced)"]
    assert c.lawyer_checked == "no"
    points = guides.key_points(guide.key)
    assert [p.heading for p in points] == [e.heading for e in knowledge.entries(guide.knowledge_file)]
    assert all(p.source and p.source_line.startswith("Source: ") for p in points)


def test_hindi_key_points_come_from_the_hindi_files():
    for guide in guides.GUIDES:
        hindi = [p for p in guides.key_points(guide.key, "hi") if p.lang == "hi"]
        assert len(hindi) == len([e for e in knowledge.hindi_entries() if e.file == guide.knowledge_file])
        for p in hindi:  # the same Source line as the English entry it translates
            assert p.source == knowledge.get(guide.knowledge_file, p.english_heading).source


def test_learn_page_shows_three_guide_cards_not_coming_soon():
    at = open_learn()
    assert at.title[0].value == "Learn"
    assert [b.label for b in at.button if str(b.key).startswith("guide-")] == ["Open guide"] * 3
    page = words(at)
    for n in (1, 2, 3):
        assert lang.t(f"home.learn{n}") in page
    assert "Coming soon" not in page and "ui.learn.soon" not in lang.strings("en")


def test_opening_a_guide_shows_explainer_sources_quiz_and_practice():
    at = open_learn()
    at.button(key="guide-undertrial").click().run()
    ok(at)
    page = words(at)
    c = guides.content("undertrial")
    assert c.explainer.splitlines()[0][:60] in page
    labels = [e.label for e in at.expander]
    assert "Section 479: release after a share of the maximum sentence" in labels
    assert "Test yourself: 10 questions" in labels and "Practice cases" in labels
    assert "Source: BNSS, 2023, Section 479" in page  # each key point shows its source
    assert "Show the answer" in page and "Checked by a lawyer" not in page and "Lawyer checked" not in page
    assert at.info[0].value == "These guides come from our verified files and have not yet been reviewed by a lawyer."
    assert "undertrial" in at.query_params["guide"]  # kept in the page address


@pytest.mark.parametrize("n, key", [(1, "legal_aid"), (2, "undertrial"), (3, "fraud")])
def test_each_home_button_opens_its_own_guide(n, key):
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Home"
    at.run()
    at.button(key=f"home-learn-{n}").click().run()
    ok(at)
    assert at.session_state["screen"] == "Learn" and at.session_state["learn_guide"] == key
    assert any(lang.t(f"home.learn{n}") in m.value and "##" in m.value for m in at.markdown)  # the guide's heading


def test_guide_in_the_address_reopens_it():
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.query_params["screen"] = "learn"
    at.query_params["guide"] = "fraud"
    at.run()
    ok(at)
    assert at.session_state["learn_guide"] == "fraud"


def test_hindi_guide_uses_hindi_key_points_where_they_exist():
    at = open_learn("fraud", "hi")
    labels = [e.label for e in at.expander]
    assert "तुरंत 1930 पर कॉल करें: फ़ौरन शिकायत करें" in labels       # from knowledge_hi/
    assert "What happens after a 1930 report" in labels              # no Hindi version yet: English
    assert lang.t("learn.english_only", "hi") in words(at)
    assert lang.t("learn.quiz", "hi", n=10) in labels


def test_page_tops_and_sign_in_cards():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '.st-key-page-head { margin-top: 28px;' in css              # space below the logo bar
    tops = css.split("/* ---------- page tops")[1]
    assert "flex-direction: row" in tops and "flex-direction: column" in tops  # side by side; stacked on phones
    assert ".st-key-signin-card { background: var(--card); border: 1px solid var(--line); border-radius: 20px;" in tops
    assert source.count('with st.container(key="signin-card")') == 3   # volunteer, supervisor password, name


@pytest.mark.parametrize("screen, state", [("Supervisor", {}), ("New case", {}), ("My cases", {}),
                                           ("Supervisor", {"supervisor_ok": True})])
def test_sign_in_forms_are_inside_the_card(monkeypatch, screen, state):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = screen
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    ok(at)
    card = next(b for b in walk(at.main) if getattr(b, "type", "") == "flex_container"
                and str(getattr(b.proto, "id", "")).endswith("-signin-card"))
    inside = [e for e in walk(card) if getattr(e, "type", "") == "text_input"]
    assert inside  # the password (and name) boxes are in the card


def walk(node):
    yield node
    for child in getattr(node, "children", {}).values():
        yield from walk(child)
