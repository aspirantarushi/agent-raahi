"""Hindi drafts: templates_hi/, the translation label, the Hindi AI disclosure, approval."""

import re
from datetime import date

import drafts
import store
from drafts import DRAFT_HEADER
from test_drafts import practice_facts
from test_hindi_files import numbers

MODEL = "gemini-3.5-flash-lite"


def hindi_draft(**changes):
    facts = practice_facts(**changes)
    result = drafts.recalculate(facts)
    return facts, result, drafts.make_undertrial_draft(facts, result, ai_model=MODEL, code="hi")


def test_hindi_practice_case_draft():
    _, _, text = hindi_draft()
    lines = text.splitlines()
    assert lines[0] == DRAFT_HEADER  # the hard rule: every draft starts with this line
    assert lines[1] == "ड्राफ़्ट — वकील से जाँच करवाना ज़रूरी है"
    assert lines[2] == "हिंदी अनुवाद की जाँच: नहीं (Hindi translation checked: no)"
    assert "- लगाई गई धाराएँ: IPC 380 (अब BNS 305)" in lines
    assert "- अपराध की अधिकतम सज़ा: 7 साल (84 महीने) (IPC 380 के अनुसार)" in lines
    assert "- हिरासत शुरू होने की तारीख़: 15 मार्च 2024" in lines
    assert "- अधिकतम सज़ा का एक-तिहाई (सिर्फ़ पहली बार के आरोपी के लिए): 15 जुलाई 2026 — पूरा हुआ" in lines
    assert "- अधिकतम सज़ा का आधा: 15 सितंबर 2027 — अभी पूरा नहीं हुआ" in lines
    assert "मुफ़्त क़ानूनी सेवाओं के लिए आवेदन" not in text  # has a legal aid lawyer: no DLSA application


def test_hindi_and_english_drafts_have_the_same_facts():
    facts = practice_facts()
    result = drafts.recalculate(facts)
    en = drafts.make_undertrial_draft(facts, result, ai_model=MODEL)
    hi = drafts.make_undertrial_draft(facts, result, ai_model=MODEL, code="hi")
    case_details = lambda t: "\n".join(l for l in t.splitlines() if l.startswith("- "))
    assert numbers(case_details(hi)) == numbers(case_details(en))


def test_source_lines_stay_in_english():
    _, _, text = hindi_draft()
    assert "  Source: Constitution of India, Article 20(1)" in text


def test_hindi_draft_with_dlsa_application():
    _, _, text = hindi_draft(lawyer="None")
    assert "मुफ़्त क़ानूनी सेवाओं के लिए आवेदन" in text
    assert "4. क्या आवेदक विधिक सेवा प्राधिकरण अधिनियम, 1987 की धारा 12 के किसी समूह में आता है? हाँ — हिरासत में व्यक्ति" in text
    assert "आवेदक एक विचाराधीन क़ैदी है, जो 15 मार्च 2024 से हिरासत में है" in text
    assert "1. आवेदक का नाम: [DLSA में हाथ से भरें — ऐप में नहीं रखा जाता]" in text  # personal blanks stay empty
    assert text.count("हिंदी अनुवाद की जाँच") == 1


def test_hindi_disclosure_and_approval(tmp_path):
    facts, _, text = hindi_draft()
    assert text.rstrip().splitlines()[-1].startswith("यह ड्राफ़्ट कैसे बना: तथ्य केस नोट्स से AI की मदद (gemini-3.5-flash-lite)")
    assert "सुपरवाइज़र ने ड्राफ़्ट को [तारीख़] को जाँच कर मंज़ूरी दी।" in text
    case_id = store.submit(text, facts, base=tmp_path, draft_lang="hi")
    store.approve(case_id, base=tmp_path, approved_on=date(2026, 11, 5))
    saved = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "सुपरवाइज़र ने ड्राफ़्ट को 5 नवंबर 2026 को जाँच कर मंज़ूरी दी।" in saved


def test_hindi_disclosure_put_back_in_hindi(tmp_path):
    facts, _, text = hindi_draft()
    case_id = store.submit(text, facts, base=tmp_path, draft_lang="hi")
    store.approve(case_id, edited_text=text.split("\n---\n\nयह ड्राफ़्ट")[0], base=tmp_path,
                  approved_on=date(2026, 11, 5))
    saved = (tmp_path / "drafts" / f"{case_id}.md").read_text(encoding="utf-8")
    assert "यह ड्राफ़्ट कैसे बना:" in saved and "5 नवंबर 2026" in saved


def test_no_ai_hindi_disclosure_has_no_court_sentence():
    facts = practice_facts()
    text = drafts.make_undertrial_draft(facts, drafts.recalculate(facts), code="hi")
    assert "तथ्य एक स्वयंसेवक ने भरे" in text and "अदालत के नियमों के अनुसार AI" not in text


def test_checked_label_changes_when_template_marked_yes(tmp_path, monkeypatch):
    for name in ("section479_note.md", "dlsa_application.md"):
        src = (drafts.TEMPLATES_HI / name).read_text(encoding="utf-8")
        (tmp_path / name).write_text(src.replace("checked: no -->", "checked: yes -->", 1), encoding="utf-8")
    monkeypatch.setattr(drafts, "TEMPLATES_HI", tmp_path)
    _, _, text = hindi_draft()
    assert text.splitlines()[2] == "हिंदी अनुवाद की जाँच: हाँ (Hindi translation checked: yes)"
