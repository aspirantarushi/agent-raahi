"""Hindi on the screen, Hindi and Hinglish notes, and voice input."""

import base64
import json
import re
import shutil
import subprocess
import urllib.error
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import general
import intake
import lang
import llm
import privacy
import store

ROOT = Path(__file__).resolve().parent.parent
NOTES_HI = (ROOT / "case_notes_hi.txt").read_text(encoding="utf-8")
UPI_HINGLISH = (ROOT / "practice_stories" / "upi_fraud_hinglish.txt").read_text(encoding="utf-8")
MODEL = "gemini-3.5-flash-lite"


def field(value, quote):
    return {"value": value, "quote": quote}


# What a careful AI returns for the Hindi practice case (quotes copied in Devanagari).
HINDI_ANSWER = {
    "custody_began": field("2024-03-15", "उसके भाई को 15 मार्च 2024 को गिरफ़्तार किया गया था।"),
    "offence_date": field(None, "अपराध फ़रवरी 2024 में हुआ था।"),
    "today_date": field("2026-11-02", "आज की तारीख़: 2 नवंबर 2026।"),
    "sections": [{"law": "IPC", "section": "380", "quote": "उस पर आईपीसी 380 (घर में चोरी) का आरोप है।"}],
    "previously_convicted": field("no", "उसे पहले कभी सज़ा नहीं हुई है।"),
    "other_cases_pending": field("no", "उसके ख़िलाफ़ कोई दूसरा केस लंबित नहीं है।"),
    "delay_by_accused": field("no", "उसने केस में कोई देरी नहीं करवाई है।"),
    "lawyer": field("Legal aid lawyer", "उसके पास एक लीगल एड वकील है, जिससे वह दो बार मिला है।"),
}


# ---------- the language files ----------

def strings(code):
    return json.loads((ROOT / "i18n" / f"{code}.json").read_text(encoding="utf-8"))


def test_language_files_have_the_same_keys_and_placeholders():
    en, hi = strings("en"), strings("hi")
    assert set(en) == set(hi)
    for key in en:
        assert set(re.findall(r"{(\w+)}", en[key])) == set(re.findall(r"{(\w+)}", hi[key])), key
        assert hi[key].strip(), key


def test_safety_messages_in_both_languages():
    assert lang.t("safety.call112") == "Call 112 now." and lang.t("safety.call112", "hi") == "अभी 112 पर कॉल करें।"
    assert lang.t("safety.call1930", "hi") == "अभी 1930 पर कॉल करें।"
    assert "15100" in lang.t("ui.sidebar.helpline", "hi") and "112" in lang.t("ui.sidebar.danger", "hi")


def test_screen_text_is_hindi():
    hi = strings("hi")
    english_only = {"ui.result.months"}  # just a number
    for key, value in hi.items():
        if key.startswith(("ui.", "tl.", "sum.", "step.")) and key not in english_only:
            assert re.search(r"[ऀ-ॿ]", value), key


def test_hindi_numbers_match_english_in_language_files():
    from test_hindi_files import numbers
    en, hi = strings("en"), strings("hi")
    for key in en:
        if key.startswith(("ui.", "safety.", "s479.", "draft.", "elig.", "next:", "sec.")):
            assert numbers(en[key]) == numbers(hi[key]), key


def test_missing_key_falls_back_to_english():
    assert lang.t("ui.next", "bn") == "Next"  # a language without a file


# ---------- the screen in Hindi ----------

def open_app(language="hi"):
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="ui_lang").set_value(language).run()
    assert not at.exception, at.exception[0].stack_trace
    return at


def test_language_switch_changes_the_screen(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    at = open_app("hi")
    assert at.title[0].value == "नया केस"
    assert "ख़तरे में हैं? अभी 112 पर कॉल करें।" in " ".join(m.value for m in at.sidebar.markdown)
    warnings = " ".join(w.value for w in at.warning)
    assert "नाम न लिखें" in warnings  # the "no names" warning in Hindi
    assert "नाम, फ़ोन नंबर या आधार नंबर बोलकर न बताएँ।" in warnings  # before recording
    at.radio(key="ui_lang").set_value("en").run()
    assert at.title[0].value == "New case"


def test_hindi_practice_case_on_screen(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_undertrial_notes",
                        lambda notes: llm.NotesReading(HINDI_ANSWER, notes, {}, MODEL))
    original_submit = store.submit
    monkeypatch.setattr(store, "submit", lambda *a, **k: original_submit(*a, base=tmp_path, **k))
    at = open_app("hi")
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_area(key="f_notes").set_value(NOTES_HI)
    next(b for b in at.button if b.label == "नोट्स पढ़ें").click().run()
    assert any("अपराध किस तारीख़ को हुआ बताया गया है?" in m.value for m in at.markdown)
    assert any("फ़रवरी 2024" in c.value for c in at.caption)
    at.date_input(key="q-offence_date").set_value(date(2024, 2, 15))
    next(b for b in at.button if b.label == "आगे").click().run()
    assert at.text_input(key="f_section").value == "380"
    at.checkbox(key="f_checked").check().run()
    shown = " ".join(m.value for m in at.markdown)
    assert "15 जुलाई 2026" in shown and "पूरा हुआ" in shown and "15 सितंबर 2027" in shown
    assert at.radio(key="f_draft_lang").value == "hi"  # draft language follows the screen language
    next(b for b in at.button if b.label == "ड्राफ़्ट बनाएँ").click().run()
    draft = at.code[0].value
    assert draft.startswith("DRAFT — to be checked by a lawyer\nड्राफ़्ट — वकील से जाँच करवाना ज़रूरी है\n"
                            "हिंदी अनुवाद की जाँच: नहीं (Hindi translation checked: no)")
    assert "तथ्य केस नोट्स से AI की मदद (gemini-3.5-flash-lite) से पढ़े गए" in draft
    next(b for b in at.button if b.label.startswith("सुपरवाइज़र को भेजें")).click().run()
    assert not at.exception
    [record] = store.list_pending(tmp_path)
    assert record["draft_lang"] == "hi"


def test_english_draft_from_hindi_screen(monkeypatch):
    at = open_app("hi")
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15))
    at.date_input(key="f_today").set_value(date(2026, 11, 2))
    at.checkbox(key="f_never").check().run()
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    at.radio(key="f_draft_lang").set_value("en").run()
    next(b for b in at.button if b.label == "ड्राफ़्ट बनाएँ").click().run()
    assert at.code[0].value.startswith("DRAFT — to be checked by a lawyer\n\nNOT READY FOR REVIEW")


def test_general_screen_in_hindi_shows_1930_and_no_names_box(monkeypatch, tmp_path):
    from test_general import UPI_ANSWER
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en": llm.NotesReading(
                            general_answer_for_hinglish(), notes, {}, MODEL))
    at = open_app("hi")
    at.text_area(key="g_notes").set_value(UPI_HINGLISH)
    next(b for b in at.button if b.label == "कहानी पढ़ें").click().run()
    assert at.error[0].value.endswith("अभी 1930 पर कॉल करें।")
    while any(b.label == "पता नहीं" for b in at.button):
        next(b for b in at.button if b.label == "पता नहीं").click().run()
    assert at.checkbox(key="g_checked").label == "मैंने यह सार नोट्स से मिलाकर जाँच लिया है, और इसमें किसी का नाम नहीं है"
    summary = at.code[0].value
    assert "ऑनलाइन धोखाधड़ी" in summary and "(हिंदी अनुवाद की जाँच: नहीं)" in summary
    assert "Source: Moneylife" in summary  # Source lines stay in English


def general_answer_for_hinglish():
    yn = lambda v, q=None: {"value": v, "quote": q}
    return {"person_needing_help": "माँ, उम्र 68", "what_happened": ["बैंक के नाम से कॉल आया और 40,000 रुपये कटे।"],
            "timeline": [{"when": "Kal", "what": "40,000 रुपये कटे"}],
            "danger_now": yn("no", "Abhi koi dhamki nahi de raha."),
            "in_custody": yn("unknown"),
            "money_lost_online": yn("yes", "Unke account se Rs 40,000 nikal gaye, do payment mein."),
            "money_lost_in_last_few_days": yn("yes", "Kal unko ek call aaya"),
            "called_1930": yn("no", "Abhi tak 1930 pe call nahi kiya"),
            "coming_dates": [], "sections_charged": [],
            "issues": [{"category": "online_or_financial_fraud", "name": "ऑनलाइन धोखाधड़ी"}],
            "documents_held": ["बैंक के SMS", "UPI request का स्क्रीनशॉट"], "questions_to_ask": [],
            "woman": yn("yes", "meri maa 68 saal ki hain"), "under_18": yn("no", "meri maa 68 saal ki hain"),
            "sc_st": yn("unknown"), "disability": yn("unknown"),
            "state": {"value": "Bihar", "quote": "Patna, Bihar mein rehti hain"},
            "income": {"amount": None, "per": "unknown", "quote": None}}


# ---------- Hindi and Hinglish notes, checked by plain code ----------

def test_hindi_practice_case_is_filled():
    r = intake.check_ai_answer(HINDI_ANSWER, privacy.redact(NOTES_HI)[0])
    assert r.values["custody_began"] == date(2024, 3, 15)
    assert (r.values["law"], r.values["section"]) == ("IPC", "380")
    assert r.values["never_convicted"] is True and r.values["other_cases_pending"] is False
    assert r.values["lawyer"] == "Legal aid lawyer" and r.values["today"] == date(2026, 11, 2)
    assert intake.missing_facts(r.values) == ["offence_date"]  # only "फ़रवरी 2024" is given
    assert r.notes_say["offence_date"] == "अपराध फ़रवरी 2024 में हुआ था।"


def test_hindi_guessed_day_is_dropped():
    answer = dict(HINDI_ANSWER, offence_date=field("2024-02-01", "अपराध फ़रवरी 2024 में हुआ था।"))
    assert "offence_date" not in intake.check_ai_answer(answer, NOTES_HI).values


def test_hinglish_answers_are_checked():
    reading = general.check_general_answer(general_answer_for_hinglish(), UPI_HINGLISH)
    assert reading.facts["woman"] is True and reading.facts["state"] == "Bihar"
    assert general.urgent_actions(reading.facts) == [general.CALL_1930]


@pytest.mark.parametrize("quote, amount, per, expected", [
    ("वह महीने में 10 हज़ार कमाता है", 10000, "month", 120000),
    ("vo mahine mein 10 hazar kamata hai", 10000, "month", 120000),
    ("saal ki kamai 1.5 lakh", 150000, "year", 150000),
    ("आय १०,००० रुपये महीना", 10000, "month", 120000),
])
def test_hindi_and_hinglish_amounts(quote, amount, per, expected):
    raw = {"income": {"amount": amount, "per": per, "quote": quote}}
    assert general.check_general_answer(raw, quote).facts["annual_income"] == expected


@pytest.mark.parametrize("text", ["मामला धारा 498A का है", "dhara 420 lagi hai", "मज़दूरी भुगतान अधिनियम, 1936 के तहत",
                                  "भारतीय न्याय संहिता"])
def test_hindi_law_references_are_removed(text):
    assert general.legal_refs(text)


# ---------- voice input ----------

@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setattr(llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")


def test_transcribe_sends_audio_only_for_text_and_filters_numbers(fake_key, monkeypatch):
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            said = "उसके भाई को 15 मार्च 2024 को गिरफ़्तार किया गया। मेरा नंबर ९८७६५ ४३२१० है।"
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"text": said})}]}}]}).encode()

    def urlopen(request, **k):
        sent["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    result = llm.transcribe(b"RIFF fake audio", "audio/wav")
    parts = sent["body"]["contents"][0]["parts"]
    assert parts[0]["inline_data"] == {"mime_type": "audio/wav", "data": base64.b64encode(b"RIFF fake audio").decode()}
    assert "Do not translate" in parts[1]["text"]
    assert "9876543210" not in privacy.normalise_digits(result.text).replace(" ", "")
    assert "[phone number removed]" in result.text and result.removed == {"a phone number": 1}
    assert "15 मार्च 2024" in result.text


def test_transcribe_refuses_empty_or_huge_recordings(fake_key):
    with pytest.raises(llm.AIUnavailable, match="empty"):
        llm.transcribe(b"")
    with pytest.raises(llm.AIUnavailable, match="too long"):
        llm.transcribe(b"0" * (llm.MAX_AUDIO_BYTES + 1))


def test_transcribe_without_key(monkeypatch):
    monkeypatch.setattr(llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(llm.AIUnavailable, match="not set up"):
        llm.transcribe(b"RIFF fake audio")


def test_voice_box_without_ai_says_so(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    at = open_app("en")
    infos = " ".join(i.value for i in at.info)
    assert "type a short summary yourself" in infos


# ---------- the real AI (only with a key) ----------

LIVE = pytest.mark.skipif(not llm.available(), reason="No GEMINI_API_KEY: live AI test skipped")


@LIVE
def test_live_hindi_practice_case():
    reading = llm.read_undertrial_notes(NOTES_HI)
    r = intake.check_ai_answer(reading.answer, reading.notes_sent)
    assert r.values.get("custody_began") == date(2024, 3, 15)
    assert (r.values.get("law"), r.values.get("section")) == ("IPC", "380")
    assert r.values.get("never_convicted") is True and r.values.get("lawyer") == "Legal aid lawyer"
    assert "offence_date" not in r.values


@LIVE
def test_live_hinglish_story():
    reading = llm.read_general_notes(UPI_HINGLISH, output_lang="hi")
    g = general.check_general_answer(reading.answer, reading.notes_sent)
    assert general.CALL_1930 in general.urgent_actions(g.facts)
    assert any(c == "online_or_financial_fraud" for c, _ in g.issues)


@LIVE
@pytest.mark.skipif(not shutil.which("say") or not shutil.which("afconvert"), reason="needs macOS speech")
def test_live_hindi_voice(tmp_path):
    aiff, wav = tmp_path / "story.aiff", tmp_path / "story.wav"
    spoken = "मेरे भाई को पंद्रह मार्च दो हज़ार चौबीस को गिरफ़्तार किया गया। उस पर चोरी का आरोप है।"
    if subprocess.run(["say", "-v", "Lekha", "-o", str(aiff), spoken]).returncode != 0:
        pytest.skip("Hindi voice not available")
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=True)
    hindi = llm.transcribe(wav.read_bytes(), "audio/wav", script="hi")  # on the Hindi screen
    assert re.search(r"[ऀ-ॿ]", hindi.text), hindi.text  # written in Devanagari, not translated
    assert "गिरफ" in privacy.comparable(hindi.text), hindi.text
    english = llm.transcribe(wav.read_bytes(), "audio/wav", script="en")  # on the English screen: as spoken
    assert re.search(r"gira?ftar|arrest", english.text, re.I), english.text
