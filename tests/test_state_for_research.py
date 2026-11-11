"""Bug: on the live app research never ran when the story gave no state, and the research box said "Choose
the state first" with no way to choose it. Now the state is asked in step 2, can be chosen in the research
box, and the checklist and the research box share one saved value. Research itself runs only when the
volunteer presses "Run research" (nothing that produces a result happens by itself). Fake data only."""

import pytest
from streamlit.testing.v1 import AppTest

import llm
import research
from test_general import MODEL, answer, yn
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

STORY = "Practice case. A woman's employer has not paid her wages for three months. She works as a cook."
NO_STATE = answer(person_needing_help="the woman", what_happened=["The employer has not paid her wages for three months."],
                  issues=[{"category": "employment_or_wages", "name": "unpaid wages"}],
                  woman=yn("yes", "A woman's employer"), danger_now=yn("no"), in_custody=yn("no"))


@pytest.fixture
def screen(monkeypatch):
    """A story with no state, and a pretend research run that records the state it was given."""
    runs = []
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: llm.NotesReading(NO_STATE, notes, {}, MODEL))

    def run(case_id, state, issue, by, **k):
        runs.append(state)
        return {"points": []}  # nothing found: the box says research found nothing, the facts-only letter follows
    monkeypatch.setattr(research, "run", run)
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(STORY)
    choose_language(at, "g_notes", language_of(STORY))
    next(b for b in at.button if b.label == "Read the story").click().run()
    return at, runs


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def to_summary(at):
    """Answer "Don't know" to the AI's questions (never to the state question) and go on."""
    for _ in range(12):
        if any(s.key == "ge-state" for s in at.selectbox):
            return at
        if any(b.key == "q-not-needed-go" for b in at.button):
            at.button(key="q-not-needed-go").click().run()
            continue
        skip = [b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all"]
        if not skip:
            return at
        skip[0].click().run()
    return at


def markdown(at):
    return " ".join(m.value for m in at.markdown)


def state_tick(at):
    return at.checkbox(key="tick-case_state").value


def test_state_is_asked_research_runs_and_the_checklist_shows_state_done(screen):
    at, runs = screen
    to_summary(at)
    ok(at)
    assert "Which state or union territory does the person live in?" in markdown(at)  # asked in step 2
    assert runs == []                                                                  # no research without it
    at.selectbox(key="ge-state").set_value("Bihar")
    next(b for b in at.button if b.key and b.key.startswith("gnext-")).click().run()
    to_summary(at)
    if any(b.key == "q-not-needed-go" for b in at.button):
        at.button(key="q-not-needed-go").click().run()
    ok(at)
    assert runs == []                 # not by itself
    assert state_tick(at) is True     # the checklist: State done
    assert not any(s.key == "rs-state" for s in at.selectbox)  # the research box needs no dropdown now
    at.button(key="rs-run-go").click().run()  # "Run research"
    assert runs == ["Bihar"]          # with the state, once
    at.run()
    assert runs == ["Bihar"]          # not again on the next run


def test_state_skipped_then_chosen_in_the_research_box(screen):
    at, runs = screen
    to_summary(at)
    next(b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all").click().run()  # "Don't know"
    if any(b.key == "q-not-needed-go" for b in at.button):
        at.button(key="q-not-needed-go").click().run()
    ok(at)
    assert runs == [] and state_tick(at) is False
    assert any("Choose the state first" in i.value for i in at.info)
    assert any(s.key == "rs-state" for s in at.selectbox)       # now the state can be chosen right there
    assert at.button(key="rs-run-go").disabled                   # "Run research" needs the state first
    at.selectbox(key="rs-state").set_value("Kerala").run()
    ok(at)
    assert at.session_state["gen"]["facts"]["state"] == "Kerala"
    assert state_tick(at) is True                                # the checklist uses the same saved value
    assert runs == []                                            # saved; research waits for the button
    at.button(key="rs-run-go").click().run()
    assert runs == ["Kerala"]
    at.run()
    assert runs == ["Kerala"]                                    # once only


def test_state_fixed_in_the_checklist_readies_research(screen):
    at, runs = screen
    to_summary(at)
    next(b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all").click().run()
    if any(b.key == "q-not-needed-go" for b in at.button):
        at.button(key="q-not-needed-go").click().run()
    at.selectbox(key="fix-case_state").set_value("Punjab")
    at.button(key="fix-case_state-go").click().run()
    ok(at)
    assert runs == [] and state_tick(at) is True
    assert not any(s.key == "rs-state" for s in at.selectbox)   # the research box shows the same value
    assert not at.button(key="rs-run-go").disabled               # and "Run research" is ready
    at.button(key="rs-run-go").click().run()
    assert runs == ["Punjab"]
