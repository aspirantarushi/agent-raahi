"""Drafts as documents: the page preview, Word (.docx) and PDF (A4), in English and Hindi. Fake data only."""

import io
import zipfile

import casework
import document
import general

G = general.GeneralFacts(
    person="the speaker's brother", what_happened=["He worked in a factory in Ludhiana.",
                                                   "The owner has not paid wages of ₹12,000 a month."],
    timeline=[("30 September 2026", "last salary paid")], coming_dates=[],
    issues=[("employment_or_wages", "unpaid wages")], sections=[], documents_held=["factory gate pass"], answers=[],
    still_to_ask=[], facts={"state": "Punjab", "woman": True}, today="2026-11-06", outcome="his unpaid wages paid")


def summary(code="en"):
    return general.make_summary_draft(G, "gemini-test", code)


def dlsa(code="en"):
    return casework.dlsa_application(G, general.check_eligibility(G.facts), "unpaid wages", "gemini-test", code)


def kinds(text):
    return [(b.kind, b.label or b.text[:30]) for b in document.parse(text)]


def test_summary_is_one_page_for_the_clinic_file_with_its_sections():
    blocks = document.parse(summary())
    assert blocks[0].kind == "draft" and blocks[1].kind == "title"
    assert blocks[1].text == "For the clinic file (not to be given out)"
    headings = [b.text for b in blocks if b.kind == "heading"]
    assert headings == ["At a glance", "What happened", "What the person wants", "Timeline", "Documents",
                        "Free legal aid", "Questions for the lawyer", "Next steps"]
    assert [b.part for b in blocks][-1] == "disclosure"  # the AI note last, in small grey text


def test_hindi_summary_has_the_same_shape():
    blocks = document.parse(summary("hi"))
    assert [b.kind for b in blocks[:3]] == ["draft", "draft", "title"]
    assert blocks[2].text == "क्लिनिक की फ़ाइल के लिए (किसी को देने के लिए नहीं)"
    assert len([b for b in blocks if b.kind == "heading"]) == 8


def test_letter_labels_numbers_blanks_and_signature():
    blocks = document.parse(dlsa())
    assert ("title", "APPLICATION FOR FREE LEGAL SER") in kinds(dlsa())
    labels = [b.label for b in blocks if b.label]
    assert "To," in labels and "Date:" in labels and "Name of applicant:" in labels
    assert [b.number for b in blocks if b.kind == "number"][:3] == ["1.", "2.", "3."]
    assert any(b.kind == "sign" and "thumb impression" in b.text for b in blocks)
    assert {b.part for b in blocks} == {"body", "notes", "disclosure"}


def test_page_preview_highlights_blanks_and_bolds_dates_and_money():
    page = document.to_html(dlsa())
    assert '<p class="doc-draft">DRAFT — to be checked by a lawyer</p>' in page
    assert '<mark class="blank">[date]</mark>' in page
    assert "<b>₹12,000</b>" in page
    assert 'class="doc-sign"' in page and 'class="doc-disclosure"' in page
    s = document.to_html(summary())
    assert "<b>30 September 2026:</b>" in s and '<h4 class="doc-h">Next steps</h4>' in s
    assert "<script" not in document.to_html("DRAFT — to be checked by a lawyer\n\n<script>alert(1)</script>")


def test_word_file_is_a4_with_the_text():
    from docx import Document
    data = document.to_docx(dlsa(), "DLSA application")
    assert zipfile.is_zipfile(io.BytesIO(data))
    doc = Document(io.BytesIO(data))
    sec = doc.sections[0]
    assert round(sec.page_width.cm, 1) == 21.0 and round(sec.page_height.cm, 1) == 29.7
    text = "\n".join(p.text for p in doc.paragraphs)
    assert text.startswith("DRAFT — to be checked by a lawyer") and "Signature or thumb impression" in text
    assert "[date]" in text  # blanks stay visible
    hi = Document(io.BytesIO(document.to_docx(dlsa("hi"), "x")))
    assert any("मुफ़्त" in p.text for p in hi.paragraphs)


def test_pdf_is_a4_with_hindi_and_english_fonts():
    for code in ("en", "hi"):
        data = document.to_pdf(summary(code), "Case summary")
        assert data.startswith(b"%PDF")
        assert b"/MediaBox [0 0 595.28 841.89]" in data  # A4
        assert b"NotoSans" in data
        if code == "hi":
            assert b"NotoSansDevanagari" in data


def test_hindi_and_english_pieces_get_their_own_fonts():
    assert document._scripts("AI की मदद (DLSA)") == [("AI ", False), ("की मदद (", True), ("DLSA)", False)]


def test_sources_show_their_name_as_a_link_on_screen():
    line = "Source: Legal Services Authorities Act, 1987, Section 12 (https://sclsc.gov.in/legal-services/Entitlement)"
    page = document.linked_html(line)
    assert '<a href="https://sclsc.gov.in/legal-services/Entitlement" target="_blank"' in page
    assert ">Legal Services Authorities Act, 1987, Section 12</a>" in page and "(https://" not in page
    assert ">nalsa.gov.in</a>" in document.linked_html("Source (current amended text): https://nalsa.gov.in/regulations/")


def test_signature_blank_has_no_extra_line():
    page = document.to_html("DRAFT — to be checked by a lawyer\n\nYours faithfully,\n\n[Name]\n[Signature or thumb impression]\n")
    assert 'class="doc-sign"' in page and 'class="doc-sign line"' not in page
