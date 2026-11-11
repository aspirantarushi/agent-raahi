"""Documents inside the readiness checklist: one list for the case (our files, plus documents named in
approved research), each marked "Has it", "Still to get" or "Can't get" (with a reason). Done when every
document is "Has it" or "Can't get". The separate documents card is gone. Fake data only."""

from streamlit.testing.v1 import AppTest

import casework
import general
import llm
from test_general import MODEL, WAGES, WAGES_ANSWER
from test_new_case_fixes import facts as make_facts
from volunteer import make_drafts

APPROVED_DOCS = [{"kind": "documents", "text": "Wage slip or muster roll"},
                 {"kind": "route", "text": "Write to the Labour Officer."}]


def test_one_list_from_our_files_and_approved_research():
    g = make_facts(documents_held=["WhatsApp messages from the contractor"])
    docs = casework.document_checklist(g, APPROVED_DOCS)
    assert docs[0] == "WhatsApp messages from the contractor"                # what the person has comes first
    plain, _ = casework.documents_needed(g, [])
    assert all(d in docs for d in plain)                                     # the list for this kind of problem
    assert docs[-1] == "Wage slip or muster roll"                            # plus approved research documents
    assert "Write to the Labour Officer." not in docs                       # never a route or other point
    assert len(docs) == len({d.casefold() for d in docs})                    # each once


def test_done_only_when_every_document_is_has_it_or_cant_get_with_a_reason():
    g = make_facts(documents_held=[])
    docs = casework.document_checklist(g, [])
    assert not casework.documents_done(g, [])
    g.documents_held = docs[:-1]
    g.documents_cannot = {docs[-1]: ""}
    assert not casework.documents_done(g, [])                                # "Can't get" needs a reason
    g.documents_cannot = {docs[-1]: "the office refused a copy"}
    assert casework.documents_done(g, [])


def test_summary_lists_has_still_to_get_and_cant_get_with_the_reason():
    g = make_facts(documents_held=["Bank statements showing earlier payments"])
    g.documents_cannot = {"Pay slips": "the contractor never gave any"}
    g.documents_to_get = ["Attendance records or photos"]
    text = general.summary_body(g)
    assert "Bank statements showing earlier payments" in text
    assert "  - Attendance records or photos" in text
    assert "Can't get (reason given by the volunteer):" in text and "  - Pay slips (the contractor never gave any)" in text


def wages_summary(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: llm.NotesReading(WAGES_ANSWER, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(WAGES)
    at.selectbox(key="g_notes_lang").set_value("en")
    at.button(key="g-read").click().run()
    while any(b.key and b.key.startswith("gskip-") and b.key != "gskip-all" for b in at.button):
        next(b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all").click().run()
    if any(b.key == "q-not-needed-go" for b in at.button):
        at.button(key="q-not-needed-go").click().run()
    assert not at.exception, at.exception[0].stack_trace
    return at


def doc_radios(at):
    return [r for r in at.radio if str(r.key).startswith("doc-st-")]


def test_documents_are_marked_in_the_checklist_only(monkeypatch):
    at = wages_summary(monkeypatch)
    radios = doc_radios(at)
    assert radios and {r.label: r.value for r in radios}["photos of the site attendance register"] == "has"
    assert all(r.options == ["Has it", "Still to get", "Can't get"] for r in radios)
    assert at.checkbox(key="tick-case_documents").value is False             # something is still to get
    assert not any("<h4>Documents</h4>" in m.value for m in at.markdown)     # no separate documents card
    still = [r for r in radios if r.value == "to_get"]
    for r in still[:-1]:
        r.set_value("has").run()
    doc_radios(at)[-1].set_value("cannot").run()                              # the last: can't get
    assert at.checkbox(key="tick-case_documents").value is False             # no reason yet: not done
    why = next(w for w in at.text_input if str(w.key).startswith("doc-why-"))
    why.set_value("the contractor will not give one").run()
    assert not at.exception, at.exception[0].stack_trace
    assert at.checkbox(key="tick-case_documents").value is True              # every document has it or can't get
    summary = make_drafts(at).session_state["shown_drafts"][0]
    assert "(the contractor will not give one)" in summary
