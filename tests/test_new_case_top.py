"""New case, the top of the page: one card (who, Sign out, today's camp, Continue a case) with the camp
and a tip beside it on laptops; no repeated "case numbers only" line; the two case type cards."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import lang

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")


def signed_in(monkeypatch, code="en"):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.session_state["clinic_ok"] = True
    at.session_state["volunteer"] = "Arushi"
    at.run()
    if code != "en":
        at.radio(key="ui_lang").set_value(code).run()
    assert not at.exception, at.exception[0].stack_trace
    return at


def text(at):
    return " ".join(str(m.value) for m in list(at.markdown) + list(at.caption))


def test_one_card_in_order_who_sign_out_camp_continue(monkeypatch):
    at = signed_in(monkeypatch)
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    top = source.split("def new_case_screen")[1].split("current_case_panel()")[0]
    assert 'key="worker-bar"' in top and "volunteer_line(card=True)" in top and 'continue_box("new")' in top
    assert "Signed in as Arushi" in text(at)
    labels = [b.label for b in at.button if b.key in ("gate-out", "camp-start")]
    assert labels == ["Sign out", "Start today's camp"]
    assert 'key="gate-out", type="primary"' in source  # Sign out: navy, filled
    assert any(t.key == "cont-code-new" for t in at.text_input)  # Continue a case (its code box)


def test_camp_status_and_tip_beside_the_card(monkeypatch):
    for code in ("en", "hi"):
        at = signed_in(monkeypatch, code)
        page = text(at)
        assert 'class="nc-side"' in page
        assert lang.t("nc.no_camp", code) in page and lang.t("nc.tip", code).replace("'", "&#x27;") in page


def test_the_case_numbers_line_is_gone(monkeypatch):
    at = signed_in(monkeypatch)
    assert not any("Use only case numbers (CNR, FIR)" in c.value for c in at.caption)
    assert "ui.new_case.caption" not in lang.strings("en") and "ui.new_case.caption" not in lang.strings("hi")
    # the story box still has the warning
    assert any("Do not type names" in w.value for w in at.warning)


def test_case_type_cards_have_short_descriptions(monkeypatch):
    assert lang.t("case_type.cap.any") == "Tell the story; the agent asks only what is missing."
    assert lang.t("case_type.cap.479") == "Someone in jail awaiting trial: release dates for the lawyer."
    at = signed_in(monkeypatch)
    assert at.radio(key="case_type").value == "Any case (start here)"


def test_card_layout_rules():
    # laptop: a 360 px card; every control 44 px high, starting at the same place; phone: full width, no tip
    assert "width: 360px !important" in CSS
    assert "height: 44px !important; min-height: 44px !important; padding: 0 16px !important" in CSS
    phone = CSS.split("/* ---------- New case, top:")[1]
    assert ".nc-side .nc-tip" in phone and "display: none !important" in phone
    assert ".st-key-worker-bar { width: 100% !important;" in phone
    # case type cards: same height, icon centred on the title, one-line descriptions
    assert "white-space: nowrap; overflow: hidden; text-overflow: ellipsis" in phone
    assert "line-height: 36px" in phone


def test_story_box_says_prototype_practice_data_only(monkeypatch):
    assert lang.t("ui.practice_only") == "Prototype: practice data only. Do not enter real cases."
    assert lang.t("ui.practice_only", "hi") == "प्रोटोटाइप: सिर्फ़ अभ्यास का डेटा। असली केस न डालें।"
    for code in ("en", "hi"):
        at = signed_in(monkeypatch, code)
        assert lang.t("ui.practice_only", code) in [c.value for c in at.caption]
    for path in ("i18n/en.json", "i18n/hi.json", "README.md"):
        words = (ROOT / path).read_text(encoding="utf-8")
        assert "in this pilot" not in words and "इस पायलट" not in words
    assert "prototype, ready for a pilot" in (ROOT / "README.md").read_text(encoding="utf-8")
