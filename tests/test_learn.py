"""The Learn page and the public Practice page: the guides from learner/ (what you will be able to do, the
key idea, a worked example, practice cases, a five-question check), each point tied to a knowledge/ entry
and shown with a clickable source; Home opens each guide."""

import re
from datetime import date
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


READY = ["legal_aid", "undertrial"]


@pytest.mark.parametrize("key", READY)
def test_each_ready_guide_has_the_learning_design_parts(key):
    c = guides.content(key)
    assert c.ready and c.lawyer_checked == "no"
    assert len(c.outcomes) == 2                       # what you will be able to do: two lines
    assert len(c.points) == 5                         # the key idea in five short points
    assert c.example_intro and len(c.steps) >= 4      # one worked example, step by step
    assert len(c.practice) == 2 and all(p.facts and p.answer for p in c.practice)  # facts up front; model answer
    assert len(c.quiz) == 5                           # a five-question check


@pytest.mark.parametrize("key", READY)
def test_every_answer_matches_its_question_and_names_a_knowledge_entry(key):
    for q in guides.content(key).quiz:
        letters = [letter for letter, _ in q.options]
        assert letters == ["a", "b", "c", "d"] and q.answer in letters, q.text
        assert q.why and q.source.text and q.source.refs, q.text
    for source in guides.all_sources(key):          # every point, step, answer line and quiz answer
        assert source.refs, source.text
        for file, heading in source.refs:
            knowledge.get(file, heading)              # raises if the entry is not in knowledge/


def _bodies(source):
    return " ".join(" ".join((knowledge.get(f, h).body + " " + knowledge.get(f, h).source).split())
                    for f, h in source.refs)  # the entry's text and its Source line (Act and section)


@pytest.mark.parametrize("key", READY)
def test_every_number_in_an_answer_is_in_the_entry_it_names(key):
    """Accuracy: the amounts, days and fractions in each "why" and key point appear in the knowledge/
    entries they name (so an answer cannot quietly say something the files don't)."""
    c = guides.content(key)
    for item in [(q.why, q.source) for q in c.quiz] + [(p.text, p.source) for p in c.points]:
        text, source = item
        body = _bodies(source).replace("₹", "").replace(",", "")
        for number in re.findall(r"\d[\d,]*", text):
            assert number.replace(",", "") in body, (key, number, text)
        for word in ("seven days", "one-third", "half", "eight weeks"):
            if word in text.lower():
                assert word in body.lower(), (key, word, text)


def test_worked_examples_and_practice_dates_match_the_calculator():
    import section479
    rows = {o.bns_section: o for o in section479.load_offences()}
    assert rows["305"].max_prison == "84" and rows["318(4)"].max_prison == "84"
    assert rows["103(1)"].death_or_life_possible       # murder: Section 479 does not apply (quiz 4)
    assert not rows["308(2)"].death_or_life_possible and not rows["305"].death_or_life_possible   # the other options
    assert not rows["318(4)"].death_or_life_possible
    for start, third, half in [(date(2024, 3, 15), "15 July 2026", "15 September 2027"),
                               (date(2025, 3, 1), "1 July 2027", "1 September 2028")]:
        assert lang.show_date(section479.add_months(start, 28)) == third
        assert lang.show_date(section479.add_months(start, 42)) == half
    text = (ROOT / "learner" / "undertrial_bail.md").read_text(encoding="utf-8")
    for d in ("15 July 2026", "15 September 2027", "1 July 2027", "1 September 2028"):
        assert d in text


def test_legal_aid_income_limits_in_the_cases_match_the_table():
    import csv
    limits = {r["state_or_ut"]: int(r["annual_income_limit_inr"])
              for r in csv.DictReader(open(ROOT / "knowledge" / "income_limits.csv", encoding="utf-8"))}
    text = (ROOT / "learner" / "legal_aid.md").read_text(encoding="utf-8")
    assert limits["Delhi"] == 300000 and "Delhi's ₹3,00,000 limit" in text
    assert limits["Gujarat"] == 100000 and "Gujarat's limit in our table is ₹1,00,000" in text
    assert limits["Bihar"] == 150000 and "Bihar's ₹1,50,000 limit" in text


def test_no_names_in_the_guides():
    for g in guides.GUIDES:
        text = (ROOT / "learner" / g.learner_file).read_text(encoding="utf-8")
        assert "Ravi" not in text


def test_cyber_fraud_guide_is_coming_soon_with_a_reason():
    c = guides.content("fraud")
    assert not c.ready and c.status == "coming soon" and "news report" in c.why_not_ready
    assert [g.key for g in guides.ready_guides()] == READY


def test_learn_page_cards_coming_soon_and_more_topics():
    at = open_learn()
    assert at.title[0].value == "Learn"
    assert [b.key for b in at.button if str(b.key).startswith("guide-")] == ["guide-legal_aid", "guide-undertrial"]
    page = words(at)
    assert page.count('<span class="soon">Coming soon</span>') == 2    # cyber fraud, and more topics
    assert "More topics coming soon: domestic violence, wages, land, consumer complaints." in page
    assert at.button(key="learn-practice").label == "Practice: test yourself"


def test_opening_a_guide_shows_each_part_with_linked_sources():
    at = open_learn()
    at.button(key="guide-undertrial").click().run()
    ok(at)
    page = words(at)
    for part in ("You will be able to", "The key idea", "A worked example, step by step", "Try it: practice cases",
                 "Check yourself: 5 questions"):
        assert part in page, part
    assert '<p class="learn-src">Source: <a href="https://www.indiacode.nic.in/handle/123456789/21615"' in page
    assert "Model answer" in [e.label for e in at.expander]           # its own collapsible section
    assert "Checked by a lawyer" not in page and "Lawyer checked" not in page
    assert at.info[0].value == "These guides come from our verified files and have not yet been reviewed by a lawyer."
    assert "undertrial" in at.query_params["guide"]


def test_the_check_gives_instant_feedback():
    at = open_learn("legal_aid")
    at.radio(key="learn-legal_aid-1").set_value("a").run()            # wrong
    ok(at)
    assert at.error[0].value.startswith("**Not quite: the answer is b) Yes, women qualify whatever their income.**")
    at.radio(key="learn-legal_aid-1").set_value("b").run()            # right
    assert at.success[0].value.startswith("**Right.** Women, children, people in custody, SC/ST members")
    assert any("Section 12</a>" in m.value for m in at.markdown if 'class="learn-src"' in m.value)


@pytest.mark.parametrize("n, key", [(1, "legal_aid"), (2, "undertrial")])
def test_each_home_button_opens_its_own_guide(n, key):
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Home"
    at.run()
    at.button(key=f"home-learn-{n}").click().run()
    ok(at)
    assert at.session_state["screen"] == "Learn" and at.session_state["learn_guide"] == key
    assert any(lang.t(f"home.learn{n}") in m.value and "##" in m.value for m in at.markdown)  # the guide's heading


def test_home_cyber_card_says_coming_soon_and_practice_is_public(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Home"
    at.run()
    assert not any(b.key == "home-learn-3" for b in at.button)
    at.button(key="nav-practice").click().run()                         # no passcode asked
    ok(at)
    assert at.session_state["screen"] == "Practice" and at.title[0].value == "Practice: test yourself"
    assert not any(t.key == "gate-pass" for t in at.text_input)
    at.radio(key="prac-legal_aid-1").set_value("b").run()
    at.radio(key="prac-undertrial-1").set_value("a").run()
    score = [m.value for m in at.markdown if 'class="practice-score"' in m.value][0]
    assert "Score: 1 right out of 2 answered (10 questions in all)" in score


def test_guide_in_the_address_reopens_it():
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.query_params["screen"] = "learn"
    at.query_params["guide"] = "undertrial"
    at.run()
    ok(at)
    assert at.session_state["learn_guide"] == "undertrial"


def test_hindi_learn_page_says_the_guide_is_in_english():
    at = open_learn("legal_aid", "hi")
    assert lang.t("learn.english_only", "hi") in words(at)
    assert lang.t("learn.check", "hi", n=5) in words(at)


def test_page_tops_and_sign_in_cards():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '.st-key-page-head { margin-top: 28px;' in css              # space below the logo bar
    tops = css.split("/* ---------- page tops")[1]
    assert "flex-direction: row" in tops and "flex-direction: column" in tops  # side by side; stacked on phones
    assert ".st-key-signin-card { background: var(--card); border: 1px solid var(--line); border-radius: 20px;" in tops
    assert source.count('st.container(key="signin-card")') == 3   # volunteer, supervisor password, name
    assert source.count('with signin_columns(') == 3                 # each in the wide two-column card
    assert ".st-key-signin-wide {" in css and ".signin-side {" in css


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
