"""Notes and recordings in any scheduled language (pretend Bhashini and pretend AI)."""

import io
import wave
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import bhashini
import llm
import multilingual
import privacy
from test_intake import NOTES, practice_answer

TAMIL_NOTES = "பயிற்சி வழக்கு. அவரது சகோதரர் 15 மார்ச் 2024 அன்று கைது செய்யப்பட்டார். தொலைபேசி ௯௮௭௬௫௪௩௨௧௦."


@pytest.fixture
def pretend_bhashini(monkeypatch):
    sent = []

    def translate(text, source, target):
        sent.append((text, source, target))
        return bhashini.Translation(NOTES, {})  # the practice case, in English

    monkeypatch.setattr(bhashini, "translate", translate)
    return sent


# ---------- reading notes ----------

def test_english_and_hindi_go_straight_to_the_ai(pretend_bhashini):
    for language in ("en", "hi"):
        prepared = multilingual.prepare("call 9876543210 about IPC 380", language)
        assert prepared.translated_from is None and "9876543210" not in prepared.text
    assert pretend_bhashini == []


def test_other_languages_are_filtered_then_translated(pretend_bhashini):
    prepared = multilingual.prepare(TAMIL_NOTES, "ta")
    [(sent_text, source, target)] = pretend_bhashini
    assert (source, target) == ("ta", "en")
    assert "9876543210" not in privacy.normalise_digits(sent_text)  # filtered BEFORE Bhashini
    assert prepared.removed == {"a phone number": 1}
    assert prepared.translated_from == "ta" and prepared.text == NOTES


def test_without_bhashini_other_languages_say_so(monkeypatch):
    monkeypatch.setattr(bhashini.llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("BHASHINI_USER_ID", raising=False)
    monkeypatch.delenv("BHASHINI_API_KEY", raising=False)
    with pytest.raises(bhashini.BhashiniUnavailable, match="not set up"):
        multilingual.prepare(TAMIL_NOTES, "ta")
    assert multilingual.prepare("नमस्ते", "hi").text == "नमस्ते"  # Hindi still works


def test_note_languages_list_all_scheduled_languages():
    options = multilingual.note_languages()
    assert list(options)[:2] == ["en", "hi"] and len(options) == 23  # English + 22 scheduled languages
    assert options["ta"] == "தமிழ்" and options["sat"] == "ᱥᱟᱱᱛᱟᱲᱤ"


def test_tamil_notes_on_screen(monkeypatch, pretend_bhashini):
    monkeypatch.setattr(llm, "available", lambda: True)
    seen = {}

    def read(notes):
        seen["notes"] = notes
        return llm.NotesReading(practice_answer(), notes, {}, "gemini-3.5-flash-lite")

    monkeypatch.setattr(llm, "read_undertrial_notes", read)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.selectbox(key="f_notes_lang").set_value("ta").run()
    at.text_area(key="f_notes").set_value(TAMIL_NOTES)
    next(b for b in at.button if b.label == "Read notes").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert seen["notes"] == NOTES  # the AI read Bhashini's English translation
    assert any("translated from தமிழ் to English by Bhashini" in i.value for i in at.info)
    assert any("1 × a phone number" in c.value for c in at.caption)


def test_bhashini_down_on_screen(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)

    def down(*a, **k):
        raise bhashini.BhashiniUnavailable("Could not reach Bhashini (check the internet).")

    monkeypatch.setattr(bhashini, "translate", down)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.selectbox(key="g_notes_lang").set_value("bn").run()
    at.text_area(key="g_notes").set_value("বাংলায় লেখা নোট")
    next(b for b in at.button if b.label == "Read the story").click().run()
    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "Bhashini is not available, so notes in বাংলা can't be translated" in errors
    assert "English or Hindi" in errors


# ---------- voice ----------

def wav_bytes(rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


@pytest.fixture
def voices(monkeypatch):
    used = []
    monkeypatch.setattr(bhashini, "configured", lambda: True)
    monkeypatch.setattr(bhashini, "supports", lambda task, language: language in ("ta", "bn"))

    def bhashini_asr(audio, language, audio_format, rate):
        used.append(("Bhashini", language, rate))
        return bhashini.Transcript("தமிழ் உரை", {})

    def gemini(audio, mime, script="en"):
        used.append(("Gemini", script))
        return llm.Transcript("text", {}, "gemini-3.5-flash-lite")

    monkeypatch.setattr(bhashini, "speech_to_text", bhashini_asr)
    monkeypatch.setattr(llm, "transcribe", gemini)
    return used


def test_bhashini_for_languages_it_supports(voices):
    result = multilingual.speech_to_text(wav_bytes(48000), "audio/wav", "ta")
    assert result.by == "Bhashini" and voices == [("Bhashini", "ta", 48000)]


def test_gemini_for_hindi_english_and_unsupported(voices):
    multilingual.speech_to_text(wav_bytes(), "audio/wav", "hi")
    multilingual.speech_to_text(wav_bytes(), "audio/wav", "en")
    multilingual.speech_to_text(wav_bytes(), "audio/wav", "sat")  # Bhashini (pretend) doesn't support it
    assert voices == [("Gemini", "hi"), ("Gemini", "en"), ("Gemini", "other")]


def test_gemini_when_not_a_wav_recording(voices):
    multilingual.speech_to_text(b"not a wav", "audio/webm", "ta")
    assert voices == [("Gemini", "other")]


def test_gemini_when_bhashini_not_set_up(voices, monkeypatch):
    monkeypatch.setattr(bhashini, "configured", lambda: False)
    multilingual.speech_to_text(wav_bytes(), "audio/wav", "ta")
    assert voices == [("Gemini", "other")]
