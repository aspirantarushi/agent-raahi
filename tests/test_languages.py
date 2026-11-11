"""Screen text in the scheduled languages: machine translated once, with every safe part kept exactly."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import bhashini
import lang

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import translate_ui  # noqa: E402
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

ENGLISH = lang.strings("en")
MACHINE_FILES = sorted(p for p in (ROOT / "i18n").glob("*.json") if p.stem not in ("en", "hi"))


def must_keep(text: str):
    """What a translation must keep exactly: {placeholders}, numbers (112, 1930, 15100...), web addresses."""
    return Counter(re.findall(r"\{\w+\}|\d+(?:\(\w+\))*|[\w.-]+\.(?:gov|org|com|in)\b", text))


def check_translation(data: dict):
    assert data.get("_status") == lang.MACHINE_STATUS
    for key, value in data.items():
        if key == "_status":
            continue
        assert key in ENGLISH, key
        assert not key.startswith(translate_ui.LEGAL_PREFIXES), f"legal text must not be machine translated: {key}"
        assert must_keep(value) == must_keep(ENGLISH[key]), key


def fake_translate(text, source, target):
    return bhashini.Translation(f"«{target}:{text}»", {})


# ---------- the translation script ----------

def test_script_keeps_placeholders_numbers_and_helplines():
    data = translate_ui.translate_file("ta", translate=fake_translate)
    check_translation(data)
    assert data["ui.sidebar.danger"] == "«ta:In danger? Call» 112 «ta:now.»"
    assert data["ui.sidebar.helpline"] == "«ta:Free legal aid helpline:» **15100**"
    assert "{case_id}" in data["ui.sent"]
    assert "cybercrime.gov.in" in data["ui.general.cyber_info"] and "1930" in data["ui.general.cyber_info"]


def test_script_leaves_legal_text_in_english():
    data = translate_ui.translate_file("bn", translate=fake_translate)
    assert not [k for k in data if k.startswith(translate_ui.LEGAL_PREFIXES)]
    assert lang.t("s479.not_automatic", "bn") == ENGLISH["s479.not_automatic"]  # falls back to English


def test_script_never_touches_hindi(tmp_path, monkeypatch):
    monkeypatch.setattr(translate_ui, "ROOT", tmp_path)
    (tmp_path / "i18n").mkdir()
    monkeypatch.setattr(translate_ui.bhashini, "configured", lambda: True)
    monkeypatch.setattr(translate_ui, "translate_file", lambda code: {"_status": lang.MACHINE_STATUS})
    translate_ui.main(["hi", "ta"])
    assert not (tmp_path / "i18n" / "hi.json").exists() and (tmp_path / "i18n" / "ta.json").exists()


def test_check_catches_a_changed_number():
    data = translate_ui.translate_file("te", translate=fake_translate)
    data["ui.sidebar.danger"] = data["ui.sidebar.danger"].replace("112", "121")
    with pytest.raises(AssertionError):
        check_translation(data)


# ---------- every machine-translated file that exists ----------

@pytest.mark.parametrize("path", MACHINE_FILES, ids=lambda p: p.stem)
def test_machine_translated_files_keep_everything_exact(path):
    assert path.stem in lang.NATIVE_NAMES
    check_translation(json.loads(path.read_text(encoding="utf-8")))


# ---------- the language switch ----------

def test_switch_lists_each_language_in_its_own_script(tmp_path, monkeypatch):
    for code in ("en", "hi", "ta", "sat"):
        (tmp_path / f"{code}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(lang, "FOLDER", tmp_path)
    assert lang._available() == {"en": "English", "hi": "हिंदी", "sat": "ᱥᱟᱱᱛᱟᱲᱤ", "ta": "தமிழ்"}


def test_22_languages_have_own_script_names():
    assert len([c for c in lang.NATIVE_NAMES if c != "en"]) == 22


def test_app_in_a_machine_translated_language(monkeypatch):
    tamil = translate_ui.translate_file("ta", translate=fake_translate)
    monkeypatch.setattr(lang, "LANGUAGES", {**lang.LANGUAGES, "ta": "தமிழ்"})
    original = lang.strings
    monkeypatch.setattr(lang, "strings", lambda code: tamil if code == "ta" else original(code))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="ui_lang").set_value("ta").run()
    assert not at.exception, at.exception[0].stack_trace
    assert at.title[0].value == "«ta:New case»"
    assert any("machine translated" in c.value for c in at.caption)
    assert 'href="tel:112"' in " ".join(m.value for m in at.markdown)


def test_drafts_offered_only_in_english_and_hindi(monkeypatch):
    tamil = translate_ui.translate_file("ta", translate=fake_translate)
    monkeypatch.setattr(lang, "LANGUAGES", {**lang.LANGUAGES, "ta": "தமிழ்"})
    original = lang.strings
    monkeypatch.setattr(lang, "strings", lambda code: tamil if code == "ta" else original(code))
    from datetime import date
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.radio(key="ui_lang").set_value("ta").run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("380")
    at.date_input(key="f_offence_date").set_value(date(2024, 2, 15))
    at.date_input(key="f_custody").set_value(date(2024, 3, 15)).run()
    calculate(at.run())  # "Calculate the dates"
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    assert not at.exception, at.exception[0].stack_trace
    assert at.radio(key="f_draft_lang").options == ["English", "हिंदी"]
    assert at.radio(key="f_draft_lang").value == "en"
