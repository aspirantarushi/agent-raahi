"""Evaluation case 9: a person's name in the story ("Ramesh") was not flagged. Common Indian first names and
surnames (English letters and Devanagari) are now flagged, without flagging places or everyday words."""

import glob
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import general
import llm
import names
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
CASE9 = (ROOT / "practice_stories" / "test_set" / "case09_unpaid_wages_privacy.txt").read_text(encoding="utf-8")


def test_case9_name_is_flagged():
    assert general.names_in_story(CASE9) == ["Ramesh"]


def test_no_other_practice_story_is_flagged():
    stories = sorted(glob.glob(str(ROOT / "practice_stories" / "**" / "*.txt"), recursive=True)) + \
        [str(ROOT / "case_notes.txt"), str(ROOT / "case_notes_hi.txt")]
    flagged = {Path(f).name: general.names_in_story(Path(f).read_text(encoding="utf-8")) for f in stories}
    assert {f: n for f, n in flagged.items() if n} == {"case09_unpaid_wages_privacy.txt": ["Ramesh"]}


@pytest.mark.parametrize("story, expected", [
    ("Sunita Devi works as a cook. Her husband Rakesh Yadav hits her.", ["Sunita", "Devi", "Rakesh", "Yadav"]),
    ("sunita ke pati rakesh ne paise nahi diye", ["sunita", "rakesh"]),  # Hinglish, no capitals
    ("रमेश को चार महीने से पैसे नहीं मिले। ठेकेदार शर्मा जी कहते हैं अगले हफ़्ते।", ["रमेश", "शर्मा"]),
    ("Imran Khan and Fatima Begum were evicted.", ["Imran", "Khan", "Fatima", "Begum"]),
])
def test_common_names_are_flagged(story, expected):
    assert general.names_in_story(story) == expected


@pytest.mark.parametrize("story", [
    "He lives in Patna, Bihar and works in Pune.",               # places
    "The case is in Krishna district court.",                      # a name used as a place
    "She went to the Ganga river near Varanasi.",
    "asha hai ki das din mein paise milenge, lal batti ke paas",   # everyday words, not names
    "सीमा पर काम करते हैं, प्रकाश नहीं है, कविता लिखी, विजय हुई।",   # Hindi words that are also names
    "The worker in Uttar Pradesh was not paid.",
])
def test_places_and_everyday_words_are_not_flagged(story):
    assert general.names_in_story(story) == []


def test_lowercase_name_in_the_draft_is_caught():
    notes = "ramesh ko paise nahi mile"
    assert general.possible_names("Person needing help: ramesh, a worker", notes) == ["ramesh"]
    assert general.possible_names("Person needing help: the worker", notes) == []


def test_case9_story_name_warning_on_screen(monkeypatch):
    from test_general import MODEL, WAGES_ANSWER
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: llm.NotesReading(WAGES_ANSWER, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(CASE9)
    choose_language(at, "g_notes", language_of(CASE9))
    next(b for b in at.button if b.label == "Read the story").click().run()
    for _ in range(10):  # the questions: "Don't know" (and the free legal aid screen: Next)
        if any(b.key == "la-next" for b in at.button):
            at.button(key="la-next").click().run()
            continue
        skip = [b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all"]
        if not skip:
            break
        skip[0].click().run()
    if any(b.key == "q-not-needed-go" for b in at.button):
        at.button(key="q-not-needed-go").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert any("The story seems to contain a person's name: Ramesh" in w.value for w in at.warning)
    assert not any("WhatsApp" in w.value for w in at.warning)  # (fixed earlier) apps are not names
