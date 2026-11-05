"""Legal text in other languages: a labelled reading copy only, with numbers kept exactly."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import bhashini
import drafts
import general
import lang
import multilingual
from test_drafts import practice_facts
from test_general import UPI, UPI_ANSWER, summarise

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import translate_ui  # noqa: E402


def marked(text, source, target):
    return bhashini.Translation("\n".join(f"<{target}>{line}" for line in text.split("\n")), {})


def changes_numbers(text, source, target):
    return bhashini.Translation(text.replace("2026", "2062"), {})


def section479_draft():
    facts = practice_facts()
    return drafts.make_undertrial_draft(facts, drafts.recalculate(facts), ai_model="gemini-3.5-flash-lite")


def test_reading_copy_is_labelled_and_keeps_english_parts():
    copy = multilingual.reading_copy(section479_draft(), "ta", marked)
    lines = copy.text.splitlines()
    assert lines[0] == "Machine translated, not checked. Rely on the English or Hindi version."
    assert "DRAFT — to be checked by a lawyer" in lines  # untranslated
    assert any(l.startswith("  Source: Constitution of India, Article 20(1)") for l in lines)  # untranslated
    assert copy.kept_in_english == 0
    assert multilingual.numbers_in(copy.text) == multilingual.numbers_in(section479_draft())


def test_paragraph_with_a_changed_number_stays_english():
    original = section479_draft()
    copy = multilingual.reading_copy(original, "ta", changes_numbers)
    assert copy.kept_in_english >= 1
    assert "2062" not in copy.text  # the changed date never appears
    assert "[kept in English: a number, date or amount changed in translation]" in copy.text


def test_summary_reading_copy_keeps_knowledge_sources():
    _, _, summary = summarise(UPI_ANSWER, UPI)
    copy = multilingual.reading_copy(summary, "bn", marked)
    assert "Source: Ministry of Home Affairs" in copy.text and "<bn>Source:" not in copy.text


def test_numbers_check_reads_every_script():
    assert multilingual.numbers_in("धारा 479(2), 15 जुलाई 2026, ₹40,000") == \
        multilingual.numbers_in("ধারা ৪৭৯(২), ১৫ জুলাই ২০২৬, ₹৪০,০০০")


@pytest.fixture
def tamil_screen(monkeypatch):
    fake = lambda text, source, target: bhashini.Translation(f"«{text}»", {})
    tamil = translate_ui.translate_file("ta", translate=fake)
    monkeypatch.setattr(lang, "LANGUAGES", {**lang.LANGUAGES, "ta": "தமிழ்"})
    original = lang.strings
    monkeypatch.setattr(lang, "strings", lambda code: tamil if code == "ta" else original(code))


def test_reading_copy_button_on_a_draft(tamil_screen, monkeypatch):
    from datetime import date
    monkeypatch.setattr(bhashini, "translate", marked)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="ui_lang").set_value("ta").run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15)).run()
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    next(b for b in at.button if b.key is None and "Make draft" in b.label).click().run()
    at.button(key="rc-go-draft").click().run()
    assert not at.exception, at.exception[0].stack_trace
    copy = at.code[1].value
    assert copy.startswith("Machine translated, not checked. Rely on the English or Hindi version.")
    assert at.code[0].value.startswith("DRAFT — to be checked by a lawyer\n\nNOT READY FOR REVIEW")  # the real draft: English


def test_no_reading_copy_in_english_or_hindi():
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    assert not [b for b in at.button if (b.key or "").startswith("rc-go-")]


def test_reading_copy_when_bhashini_is_down(tamil_screen, monkeypatch):
    def down(*a, **k):
        raise bhashini.BhashiniUnavailable("Could not reach Bhashini (check the internet).")
    monkeypatch.setattr(bhashini, "translate", down)
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="ui_lang").set_value("ta").run()
    at.radio(key="case_type").set_value("Undertrial").run()
    from datetime import date
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15)).run()
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    next(b for b in at.button if b.key is None and "Make draft" in b.label).click().run()
    at.button(key="rc-go-draft").click().run()
    assert any("Use the English or Hindi version" in e.value for e in at.error)
