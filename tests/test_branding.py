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


EN_MARK = '<small class="agent">Agent</small> <span>Raahi</span>'
HI_MARK = '<small class="agent">एजेंट</small> <span>राही</span>'
BRAND_FILES = ("raahi-mark.svg", "raahi-mark-on-dark.svg", "favicon.svg", "raahi-app-icon.svg")


def test_brand_files_are_present_and_drawn_inline_unchanged():
    for name in BRAND_FILES:
        svg = (ROOT / "assets" / "brand" / name).read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "<image" not in svg and "@import" not in svg  # nothing to download
    for path, draw in ((ui.LOGO_FILE, ui.logo_mark), (ui.LOGO_ON_DARK_FILE, ui.logo_on_dark)):
        shown = draw(32)
        assert len(shown.encode()) < 2048 and "<metadata>" not in shown  # light on 3G
        drawing = path.read_text(encoding="utf-8").split("</metadata>", 1)[1]
        assert drawing.strip() in shown  # the paths and colours exactly as in the file


def test_logo_on_light_and_on_navy():
    assert "#13213B" in ui.logo_mark() and "#E8A33D" in ui.logo_mark()           # navy R, amber light
    assert "#F8F6F1" in ui.logo_on_dark() and "#13213B" not in ui.logo_on_dark()  # light R on navy
    band = ui.facts_band("Facts", [("A fact.", "Source: x")])
    assert "#F8F6F1" in band and "#E8A33D" not in band


def test_logo_is_in_the_header():
    head = ui.header("Agent Raahi", "Lighting the way to legal aid", "An AI casework agent")
    assert "<svg" in head and EN_MARK in head and "#E8A33D" in head
    assert HI_MARK in ui.header("एजेंट राही", "क़ानूनी मदद तक, रोशन राह")
    assert ui.logo_mark(48) in ui.brand("Agent Raahi")  # the header logo, 1.5 times the old 32px


def test_header_on_screen_in_both_languages():
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    html = " ".join(m.value for m in at.markdown)
    assert EN_MARK in html and "Lighting the way to legal aid" in html
    assert "An AI casework agent for legal aid clinics and NGOs" in html
    at.radio(key="ui_lang").set_value("hi").run()
    html = " ".join(m.value for m in at.markdown)
    assert HI_MARK in html and "क़ानूनी मदद तक, रोशन राह" in html


def test_tab_title_and_icon():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'st.set_page_config(page_title=lang.t("app.name"' in src
    assert "page_icon=str(ui.FAVICON_FILE)" in src and ui.FAVICON_FILE.name == "favicon.svg"


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
