"""Nothing that produces a result happens by itself: the volunteer presses a button (Section 479 dates,
research, the letter, the drafts, speech to text), and a suggested language is confirmed. Fake data only."""

from datetime import date

from streamlit.testing.v1 import AppTest

import llm
import sarvam
from test_general import MODEL, WAGES, WAGES_ANSWER
from volunteer import make_drafts


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def undertrial():
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15))
    at.date_input(key="f_today").set_value(date(2026, 11, 2))
    at.checkbox(key="f_never").check().run()
    ok(at)
    return at


def dates_shown(at):
    return any("One-third" in m.value for m in at.markdown)


def test_section_479_dates_only_after_calculate_and_cleared_by_an_edit():
    at = undertrial()
    assert not dates_shown(at)
    card = " ".join(m.value for m in at.markdown)
    assert "The dates will be worked out from these facts" in card and "IPC 380" in card  # the fields, before
    at.button(key="f-calc").click().run()
    assert dates_shown(at) and "15 July 2026" in " ".join(m.value for m in at.markdown)
    at.date_input(key="f_custody").set_value(date(2024, 4, 15)).run()   # a field changes
    assert not dates_shown(at)
    assert any('press "Calculate the dates" again' in i.value for i in at.info)
    at.button(key="f-calc").click().run()
    assert "15 August 2026" in " ".join(m.value for m in at.markdown)     # the new dates, once pressed again


def test_edit_unticks_the_check_and_hides_the_dates(monkeypatch):
    from test_intake import NOTES, practice_answer
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes", lambda notes: llm.NotesReading(practice_answer(), notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_area(key="f_notes").set_value(NOTES)
    at.selectbox(key="f_notes_lang").set_value("en")
    at.button(key="f-read").click().run()
    at.checkbox(key="f_checked").check().run()
    at.button(key="f-calc").click().run()
    assert dates_shown(at)
    at.button(key="f-edit").click().run()
    assert at.checkbox(key="f_checked").value is False and not dates_shown(at)


def test_language_is_suggested_and_pre_selected(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    read = []
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: read.append(notes) or llm.NotesReading(WAGES_ANSWER, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    assert at.button(key="g-read").disabled                             # no story yet: says why
    assert any("Type or speak the story first." in m.value for m in at.markdown)
    at.text_area(key="g_notes").set_value("Malik ne teen mahine se salary nahi di, kya karein? Bhai bahut pareshan hai.").run()
    assert at.selectbox(key="g_notes_lang").value == "hi-Latn"          # the suggestion, pre-selected
    assert any("Detected: Hinglish" in c.value for c in at.caption)     # the volunteer can change it
    assert not at.button(key="g-read").disabled
    at.selectbox(key="g_notes_lang").set_value("en").run()              # the volunteer's choice wins
    at.text_area(key="g_notes").set_value("Malik ne teen mahine se salary nahi di. Bhai bahut pareshan hai, kya karein?").run()
    assert at.selectbox(key="g_notes_lang").value == "en"
    at.button(key="g-read").click().run()
    assert len(read) == 1


class Recording:
    type = "audio/wav"

    def __init__(self, data):
        self.data = data

    def getvalue(self):
        return self.data


def test_speech_becomes_text_only_when_asked(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setenv("SARVAM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(sarvam, "_post", lambda *a: sent.append(1) or {"transcript": "The worker was not paid."})
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.session_state["g_audio"] = Recording(b"RIFF fake")
    at.run()
    assert sent == [] and not at.text_area(key="g_notes").value       # a recording alone sends nothing
    assert any(b.key == "g_audio-convert" for b in at.button)         # "Turn speech into text" is offered
    # What pressing it does (the test tool cannot keep a recording in the mic widget across a click):
    at.session_state["g_audio"] = Recording(b"RIFF fake")
    at.session_state["g_audio-pending"] = True
    at.run()
    ok(at)
    assert sent == [1] and at.text_area(key="g_notes").value == "The worker was not paid."
    assert not any(b.key == "g_audio-convert" for b in at.button)     # done for this recording


def test_drafts_only_after_make_the_drafts_and_cleared_by_a_change(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: llm.NotesReading(WAGES_ANSWER, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(WAGES)
    at.selectbox(key="g_notes_lang").set_value("en")
    at.button(key="g-read").click().run()
    while any(b.key and b.key.startswith("gskip-") and b.key != "gskip-all" for b in at.button):
        next(b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all").click().run()
    if any(b.key == "q-not-needed-go" for b in at.button):
        at.button(key="q-not-needed-go").click().run()
    ok(at)
    assert not at.session_state["shown_drafts"]                       # nothing drafted by itself
    send = next(b for b in at.button if b.key == "send-g")
    assert send.disabled                                              # and nothing can be sent yet
    make_drafts(at, letter=False)
    assert at.session_state["shown_drafts"]                           # after "Make the drafts"
    tick = next(c for c in at.checkbox if str(c.key).startswith("tick-"))
    (tick.uncheck() if tick.value else tick.check()).run()             # a change to what the drafts are made from
    assert not at.session_state["shown_drafts"]
    assert any('press "Make the drafts" again' in i.value for i in at.info)
