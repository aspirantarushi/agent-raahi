"""Agent Raahi: the name, tagline, logo, tab title, draft line, and the name check."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import drafts
import general
import lang
import ui
from test_drafts import practice_facts

ROOT = Path(__file__).resolve().parent.parent


def test_name_and_tagline_in_both_languages():
    assert (lang.t("app.name"), lang.t("app.name", "hi")) == ("Agent Raahi", "एजेंट राही")
    assert lang.t("app.tagline") == "Lighting the way to legal aid"
    assert lang.t("app.tagline", "hi") == "क़ानूनी मदद तक, रोशन राह"
    assert lang.t("app.description") == "An AI casework agent for legal aid clinics and NGOs"
    assert lang.t("meta.hi_checked.app.tagline", "hi") == "no"  # Hindi tagline not yet checked


def test_logo_is_a_tiny_inline_svg():
    svg = (ROOT / "assets" / "logo-mark.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") and len(svg.encode()) < 2048
    assert "href" not in svg and "<image" not in svg and "@import" not in svg  # nothing to download
    head = ui.header("Agent Raahi", "Lighting the way to legal aid", "An AI casework agent")
    assert "<svg" in head and "Agent <span>Raahi</span>" in head
    assert "एजेंट <span>राही</span>" in ui.header("एजेंट राही", "क़ानूनी मदद तक, रोशन राह")


def test_header_on_screen_in_both_languages():
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    html = " ".join(m.value for m in at.markdown)
    assert "Agent <span>Raahi</span>" in html and "Lighting the way to legal aid" in html
    assert "An AI casework agent for legal aid clinics and NGOs" in html
    at.radio(key="ui_lang").set_value("hi").run()
    html = " ".join(m.value for m in at.markdown)
    assert "एजेंट <span>राही</span>" in html and "क़ानूनी मदद तक, रोशन राह" in html


def test_tab_title_uses_the_name():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'st.set_page_config(page_title=lang.t("app.name"' in src


def test_drafts_say_prepared_with_agent_raahi():
    facts = practice_facts()
    result = drafts.recalculate(facts)
    en = drafts.make_undertrial_draft(facts, result, ai_model="gemini-3.5-flash-lite")
    assert "\n---\n\nPrepared with Agent Raahi.\nHow this draft was prepared:" in en
    hi = drafts.make_undertrial_draft(facts, result, ai_model="gemini-3.5-flash-lite", code="hi")
    assert "\n---\n\nएजेंट राही की मदद से तैयार।\nयह ड्राफ़्ट कैसे बना:" in hi


def test_name_check_never_flags_agent_raahi():
    notes = "The worker said Agent Raahi helped before. Raahi was used by Meena at the clinic."
    summary = "Agent Raahi was used. Meena was not paid."
    flagged = general.possible_names(summary, notes)
    assert "Raahi" not in flagged and "Agent" not in flagged
    assert flagged == ["Meena"]  # a real name is still flagged


def test_name_in_readme_and_claude_md():
    for name in ("README.md", "CLAUDE.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "Agent Raahi" in text and "Lighting the way to legal aid" in text
