"""Voice input with Sarvam AI (saaras:v4) first, Gemini as the backup, then typing. Fake audio results
only: no test reaches the real Sarvam service, except the one live test run by hand
(RAAHI_LIVE_SARVAM=1 .venv/bin/python -m pytest tests/test_sarvam.py -k live)."""

import io
import math
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import audit
import llm
import multilingual
import sarvam
import storage

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000


def wav(pattern):
    """A 16-bit mono WAV: pattern = [(seconds, loud?)]. Loud parts are a tone, quiet parts silence."""
    frames = bytearray()
    for seconds, loud in pattern:
        for i in range(int(seconds * RATE)):
            value = int(8000 * math.sin(2 * math.pi * 220 * i / RATE)) if loud else 0
            frames += value.to_bytes(2, "little", signed=True)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(RATE), w.writeframes(bytes(frames))
    return out.getvalue()


def seconds(audio):
    with wave.open(io.BytesIO(audio)) as w:
        return w.getnframes() / w.getframerate()


@pytest.fixture
def fake_sarvam(monkeypatch):
    """A pretend Sarvam: answers "part 1", "part 2", ... and records what was sent (never the real one)."""
    sent = []
    monkeypatch.setenv("SARVAM_API_KEY", "test-key-not-real")

    def post(audio, mime, language_code, mode, key):
        sent.append({"seconds": seconds(audio) if audio[:4] == b"RIFF" else None, "language_code": language_code,
                     "mode": mode, "key": key, "mime": mime})
        return {"request_id": "x", "transcript": f"part {len(sent)}", "language_code": language_code}
    monkeypatch.setattr(sarvam, "_post", post)
    return sent


@pytest.fixture
def fake_gemini(monkeypatch):
    used = []

    def gemini(audio, mime, script="en"):
        used.append(script)
        return llm.Transcript("backup text", {}, "gemini-3.5-flash-lite")
    monkeypatch.setattr(llm, "transcribe", gemini)
    return used


def problems():
    return [p for p in audit.list_problems() if p.get("where") == audit.AI_SERVICE and "Sarvam" in p["text"]]


# ---------- modes ----------

@pytest.mark.parametrize("language, code, mode", [("en", "unknown", "transcribe"), ("hi", "hi-IN", "transcribe"),
                                                  ("hi-Latn", "hi-IN", "translit")])
def test_mode_by_notes_language(fake_sarvam, language, code, mode):
    result = multilingual.speech_to_text(wav([(3, True)]), "audio/wav", language)
    assert fake_sarvam[0]["language_code"] == code and fake_sarvam[0]["mode"] == mode
    assert result.by == "Sarvam AI (saaras:v4)" and not result.backup


def test_model_and_endpoint():
    assert sarvam.MODEL == "saaras:v4" and sarvam.URL == "https://api.sarvam.ai/speech-to-text"


def test_the_request_is_a_form_with_the_model_language_and_mode():
    body, content_type = sarvam._form({"model": "saaras:v4", "language_code": "hi-IN", "mode": "translit"},
                                      b"RIFFaudio", "speech.wav", "audio/wav")
    assert content_type.startswith("multipart/form-data; boundary=")
    for part in (b'name="model"\r\n\r\nsaaras:v4', b'name="language_code"\r\n\r\nhi-IN', b'name="mode"\r\n\r\ntranslit',
                 b'name="file"; filename="speech.wav"', b"RIFFaudio"):
        assert part in body


# ---------- 30 seconds at most: split at pauses, joined in order ----------

def test_short_recording_is_one_part(fake_sarvam):
    audio = wav([(20, True)])
    assert sarvam.split(audio) == [audio]


def test_long_recording_is_split_at_pauses_under_30_seconds():
    # 70 s: speech with pauses at 22-23 s and 46-47 s
    audio = wav([(22, True), (1, False), (23, True), (1, False), (23, True)])
    parts = sarvam.split(audio)
    lengths = [seconds(p) for p in parts]
    assert all(n < 30 for n in lengths) and abs(sum(lengths) - 70) < 0.1  # nothing lost
    assert 22 <= lengths[0] <= 23 and 22.5 <= lengths[0] + lengths[1] - 23 <= 24  # cut inside the pauses


def test_long_recording_without_pauses_is_still_under_30_seconds():
    parts = sarvam.split(wav([(65, True)]))
    assert len(parts) == 3 and all(seconds(p) < 30 for p in parts)


def test_parts_are_sent_one_by_one_and_joined_in_order_with_progress(fake_sarvam):
    seen = []
    result = multilingual.speech_to_text(wav([(25, True), (1, False), (25, True), (1, False), (20, True)]),
                                         "audio/wav", "hi", progress=lambda n, total: seen.append((n, total)))
    assert result.text == "part 1 part 2 part 3"
    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert all(s["seconds"] < 30 for s in fake_sarvam)


def test_numbers_are_removed_from_the_text(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(sarvam, "_post", lambda *a: {"transcript": "Mera number 98765 43210 hai, Aadhaar 2345 6789 0123."})
    result = sarvam.transcribe(wav([(2, True)]), "audio/wav", "hi-Latn")
    assert "98765" not in result.text and "2345 6789" not in result.text
    assert result.removed == {"a phone number": 1, "an Aadhaar number": 1}


def test_audio_is_never_saved(fake_sarvam, tmp_path):
    before = set(Path(os.environ["RAAHI_DATA_DIR"]).rglob("*"))
    multilingual.speech_to_text(wav([(2, True)]), "audio/wav", "en")
    after = set(Path(os.environ["RAAHI_DATA_DIR"]).rglob("*"))
    assert not [p for p in after - before if p.suffix in (".wav", ".webm", ".mp3", ".ogg")]


# ---------- the backup: Gemini, then typing; logged ----------

def test_no_key_uses_gemini_and_logs_it(monkeypatch, fake_gemini):
    monkeypatch.setenv("SARVAM_API_KEY", "")
    result = multilingual.speech_to_text(wav([(2, True)]), "audio/wav", "hi-Latn")
    assert result.backup and result.by == "gemini-3.5-flash-lite" and fake_gemini == ["en"]  # Hinglish: as spoken
    assert "no key" in problems()[0]["text"] and "backup" in problems()[0]["text"]


@pytest.mark.parametrize("kind, code", [("quota", 429), ("busy", 503), ("timeout", None), ("key", 403)])
def test_sarvam_failure_uses_gemini_and_logs_it(monkeypatch, fake_gemini, kind, code):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key-not-real")

    def fails(*a):
        raise sarvam.SarvamUnavailable("down", kind, code)
    monkeypatch.setattr(sarvam, "_post", fails)
    progress = []
    result = multilingual.speech_to_text(wav([(2, True)]), "audio/wav", "hi", progress=lambda n, t: progress.append((n, t)))
    assert result.text == "backup text" and result.backup and fake_gemini == ["hi"]
    assert progress[-1] == (0, 0)  # the screen says the backup is being used
    entry = problems()[0]
    assert kind in entry["text"] and entry["ai_failures"][0]["model"] == "Sarvam AI (saaras:v4)"


def test_both_fail_asks_to_type_and_logs_it(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(sarvam, "_post", lambda *a: (_ for _ in ()).throw(sarvam.SarvamUnavailable("down", "busy", 503)))
    monkeypatch.setattr(llm, "transcribe", lambda *a, **k: (_ for _ in ()).throw(llm.AIUnavailable("busy", busy=True)))
    with pytest.raises(llm.AIUnavailable):
        multilingual.speech_to_text(wav([(2, True)]), "audio/wav", "en")
    assert "the volunteer was asked to type the story" in problems()[0]["text"]


def test_no_audio_or_text_goes_into_the_problems_log(monkeypatch, fake_gemini):
    monkeypatch.setenv("SARVAM_API_KEY", "")
    multilingual.speech_to_text(wav([(2, True)]), "audio/wav", "en")
    saved = str(problems()[0])
    assert "backup text" not in saved and "RIFF" not in saved


# ---------- on screen ----------

class Recording:
    def __init__(self, data):
        self.data, self.type = data, "audio/wav"

    def getvalue(self):
        return self.data


def new_case(monkeypatch, code="en"):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    if code != "en":
        at.radio(key="ui_lang").set_value(code).run()
    return at


def test_voice_text_goes_into_the_story_box_for_checking(monkeypatch, fake_sarvam):
    at = new_case(monkeypatch)
    at.session_state["g_audio"] = Recording(wav([(25, True), (1, False), (25, True)]))
    at.session_state["g_audio-pending"] = True  # what stopping the recording does
    at.run()
    assert not at.exception, at.exception[0].stack_trace
    assert at.text_area(key="g_notes").value == "part 1 part 2"
    assert any("The text is in the box below. Read it and correct anything wrong." in s.value for s in at.success)


def test_backup_message_on_screen(monkeypatch, fake_gemini):
    monkeypatch.setenv("SARVAM_API_KEY", "")
    at = new_case(monkeypatch)
    at.session_state["g_audio"] = Recording(wav([(2, True)]))
    at.session_state["g_audio-pending"] = True
    at.run()
    assert at.text_area(key="g_notes").value == "backup text"
    assert any("the backup (Google Gemini) turned the speech into text" in s.value for s in at.success)


def test_both_failing_on_screen_asks_to_type(monkeypatch):
    monkeypatch.setattr(llm, "transcribe", lambda *a, **k: (_ for _ in ()).throw(llm.AIUnavailable("busy", busy=True)))
    at = new_case(monkeypatch)
    at.session_state["g_audio"] = Recording(wav([(2, True)]))
    at.session_state["g_audio-pending"] = True
    at.run()
    assert not at.exception
    assert any("could not be turned into text just now" in e.value and "You can type the story instead." in e.value
               for e in at.error)
    assert not at.text_area(key="g_notes").value


@pytest.mark.parametrize("code, words", [("en", "Sarvam AI (an Indian speech service; Google Gemini as a backup)"),
                                         ("hi", "Sarvam AI (एक भारतीय स्पीच सेवा; बैकअप के रूप में Google Gemini)")])
def test_warning_under_the_mic_names_sarvam(monkeypatch, code, words):
    at = new_case(monkeypatch, code)
    assert any(words in c.value for c in at.caption)


def test_progress_messages():
    import lang
    assert lang.t("ui.voice.part", n=2, total=4) == "Turning speech into text… (part 2 of 4)"
    assert lang.t("ui.voice.part", "hi", n=2, total=4).endswith("(भाग 2 / 4)")


def test_privacy_document_names_sarvam_and_its_settings():
    text = " ".join((ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8").split())  # ignore line breaks
    assert "Sarvam AI" in text and "training is turned off" in text and "1 day" in text


# ---------- the live test (run by hand) ----------

@pytest.mark.live_sarvam
@pytest.mark.skipif(os.environ.get("RAAHI_LIVE_SARVAM") != "1", reason="live Sarvam test: run by hand with RAAHI_LIVE_SARVAM=1")
@pytest.mark.skipif(not shutil.which("say") or not shutil.which("afconvert"), reason="needs macOS speech")
def test_live_sarvam_hindi_hinglish_and_a_long_recording(tmp_path, monkeypatch):
    key = next((l.split("=", 1)[1].strip().strip('"\'') for l in (ROOT / ".env").read_text().splitlines()
                if l.startswith("SARVAM_API_KEY=")), "")
    if not key:
        pytest.skip("no SARVAM_API_KEY in .env")
    monkeypatch.setenv("SARVAM_API_KEY", key)

    def recording(text, name):
        aiff, out = tmp_path / f"{name}.aiff", tmp_path / f"{name}.wav"
        if subprocess.run(["say", "-v", "Lekha", "-o", str(aiff), text]).returncode != 0:
            pytest.skip("Hindi voice not available")
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(out)], check=True)
        return out.read_bytes()

    short = recording("मेरे भाई का फ़ोन चोरी हो गया और उसके खाते से अठारह हज़ार रुपये कट गए।", "short")
    hindi = sarvam.transcribe(short, "audio/wav", "hi")
    assert re.search(r"[ऀ-ॿ]", hindi.text) and "भाई" in hindi.text, hindi.text
    as_spoken = sarvam.transcribe(short, "audio/wav", "en")  # English notes, Hindi speech: never translated
    assert "brother" not in as_spoken.text.lower(), as_spoken.text
    hinglish = sarvam.transcribe(short, "audio/wav", "hi-Latn")
    assert not re.search(r"[ऀ-ॿ]", hinglish.text) and re.search(r"bhai", hinglish.text, re.I), hinglish.text
    long = recording(" [[slnc 800]] ".join(["मेरी बहन उत्तर प्रदेश में रहती हैं और घरों में काम करती हैं।"] * 8), "long")
    seen = []
    result = sarvam.transcribe(long, "audio/wav", "hi", progress=lambda n, t: seen.append((n, t)))
    assert result.parts >= 2 and seen[-1] == (result.parts, result.parts) and result.text.count("बहन") >= 6
