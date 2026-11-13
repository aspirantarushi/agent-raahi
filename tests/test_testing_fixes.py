"""Fixes from Arushi's testing document (12 November 2026). Fake data only."""

import time
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

import casework
import general
import llm
import store
import tracker
from test_general import MODEL, WAGES, WAGES_ANSWER, answer, yn
from test_new_case_fixes import facts as make_facts
from volunteer import make_drafts

ROOT = Path(__file__).resolve().parent.parent


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def to_summary(at):
    for _ in range(12):
        if any(b.key == "q-not-needed-go" for b in at.button):
            at.button(key="q-not-needed-go").click().run()
            continue
        if any(b.key == "la-next" for b in at.button):  # the free legal aid screen: all "Don't know"
            at.button(key="la-next").click().run()
            continue
        skip = [b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all"]
        if not skip:
            return at
        skip[0].click().run()
    return at


def wages(monkeypatch, reading=None):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes", reading or (
        lambda notes, output_lang="en", **k: llm.NotesReading(WAGES_ANSWER, notes, {}, MODEL)))
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(WAGES).run()
    at.button(key="g-read").click().run()
    return to_summary(at)


# ---------- 1. sending: why not, and the status afterwards ----------

def test_send_says_exactly_why_it_cannot_be_sent_then_sends(monkeypatch):
    at = wages(monkeypatch)
    ok(at)
    assert next(b for b in at.button if b.key == "send-g").disabled
    import html
    reasons = [html.unescape(m.value) for m in at.markdown if 'class="why-off red"' in m.value]
    assert any('Press "Make the drafts" first.' in r for r in reasons) and any("Tick" in r for r in reasons)
    make_drafts(at, letter=False)
    if any(t.key == "g_send_reason" for t in at.text_input):
        at.text_input(key="g_send_reason").set_value("practice: the rest at the next visit")
    at.checkbox(key="g_checked").check().run()
    send = next(b for b in at.button if b.key == "send-g")
    assert not send.disabled and not [m for m in at.markdown if 'class="why-off red"' in m.value]
    send.click().run()
    ok(at)
    case_id = at.session_state["case_id"]
    assert tracker.status_of(case_id) == store.WAITING
    today = f"{date.today().day} {date.today():%B %Y}"
    assert any(f"Sent on {today} · Waiting for review" in s.value for s in at.success)
    # after a reload (a new session with the case in the page address) the case card still says so
    at2 = AppTest.from_file("../app.py", default_timeout=30)
    at2.query_params["screen"] = "new"
    at2.query_params["case"] = case_id
    at2.run()
    ok(at2)
    assert any(f"Sent on {today} · Waiting for review" in m.value for m in at2.markdown)
    # and the Supervisor page lists it as waiting
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    sup = AppTest.from_file("../app.py", default_timeout=30)
    sup.session_state["screen"] = "Supervisor"
    for k, v in {"supervisor_ok": True, "supervisor_name": "SK", "sup_last_active": time.time()}.items():
        sup.session_state[k] = v
    sup.run()
    ok(sup)
    code = tracker.load(case_id)["code"]
    assert any('class="sup-row' in m.value and code in m.value for m in sup.markdown)   # a row in "Waiting for you"


# ---------- 2. every disabled button says why ----------

def test_disabled_buttons_say_why(monkeypatch):
    no_state = answer(what_happened=["The employer has not paid her wages."],
                      issues=[{"category": "employment_or_wages", "name": "unpaid wages"}], woman=yn("yes", "A woman"))
    at = wages(monkeypatch, lambda notes, output_lang="en", **k: llm.NotesReading(no_state, notes, {}, MODEL))
    skip = [b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all"]
    if skip:  # the state question: "Don't know"
        skip[0].click().run()
        to_summary(at)
    ok(at)
    assert at.button(key="rs-run-go").disabled
    assert any("Choose the state first: research needs it." in m.value for m in at.markdown)  # (no quotes to escape)


def test_delete_button_says_choose_a_case_first(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    tracker.open_case("General", "Volunteer A")
    sup = AppTest.from_file("../app.py", default_timeout=30)
    sup.session_state["screen"] = "Supervisor"
    for k, v in {"supervisor_ok": True, "supervisor_name": "SK", "sup_last_active": time.time()}.items():
        sup.session_state[k] = v
    sup.run()
    assert sup.button(key="del-go").disabled and any("Choose a case first." in m.value for m in sup.markdown)


# ---------- 3. editing the story and reading it again merges ----------

def test_near_repeated_lines_are_merged_and_a_corrected_value_replaces(tmp_path):
    case_id = tracker.open_case("General", "VA", base=tmp_path)["id"]
    tracker.add_summary(case_id, ["They were captured, beaten and robbed."], [], [], "VA", base=tmp_path)
    tracker.add_summary(case_id, ["Were captured, beaten and robbed.", "The police did not file a report."], [], [],
                        "VA", base=tmp_path)
    assert tracker.load(case_id, base=tmp_path)["summary"] == ["Were captured, beaten and robbed.",
                                                               "The police did not file a report."]
    tracker.merge_facts(case_id, {"state": "Bihar"}, "VA", "story", base=tmp_path)
    assert tracker.merge_facts(case_id, {"state": "Jharkhand"}, "VA", "story", base=tmp_path, replace=True) == []
    assert tracker.load(case_id, base=tmp_path)["facts"]["state"]["value"] == "Jharkhand"   # the newer value
    assert tracker.merge_facts(case_id, {"state": "Odisha"}, "VB", "another visit", base=tmp_path)  # still a contradiction


def test_a_question_already_answered_is_never_asked_again():
    assert general.same_question("When did the employer stop paying?", "On what date did the employer stop paying wages?")
    assert not general.same_question("What does the person want?", "Which state does the person live in?")


def test_rereading_keeps_answers_and_does_not_ask_again(monkeypatch):
    first = dict(WAGES_ANSWER, questions_to_ask=["When did the contractor stop paying?"])
    second = dict(WAGES_ANSWER, questions_to_ask=["On what date did the contractor stop paying the wages?"],
                  what_happened=["They were not paid wages for June to August 2026 by the contractor."])
    calls = []

    def reading(notes, output_lang="en", **k):
        calls.append(notes)
        return llm.NotesReading(first if len(calls) == 1 else second, notes, {}, MODEL)
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes", reading)
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(WAGES).run()
    at.button(key="g-read").click().run()
    at.text_input(key="gq-0").set_value("1 June 2026")
    next(b for b in at.button if b.key and b.key.startswith("gnext-ai")).click().run()
    to_summary(at)
    at.button(key="g-back-story").click().run() if any(b.key == "g-back-story" for b in at.button) else None
    at.text_area(key="g_notes").set_value(WAGES + " He worked on a site in Pune.").run()
    at.button(key="g-read").click().run()
    ok(at)
    assert not any("stop paying" in m.value for m in at.markdown if m.value.startswith("**"))  # not asked again
    gen = at.session_state["gen"]
    assert ("When did the contractor stop paying?", "1 June 2026") in gen["answers"]           # the answer is kept
    record = tracker.load(at.session_state["case_id"])
    lines = record["summary"]
    assert len(lines) == len({tracker._plain_line(x) for x in lines})                          # no near-repeats


# ---------- 4. a dated answer feeds the timeline and "Going on for" ----------

def test_a_dated_answer_feeds_going_on_for():
    g = make_facts(timeline=[], answers=[("When did the contractor stop paying?", "On 15 March 2026")],
                   what_happened=["The contractor has not paid the worker."])
    general.apply_answers(g)
    assert ("15 March 2026", "When did the contractor stop paying?") in g.timeline
    assert casework.duration_text(g, date(2026, 11, 12)).startswith("about 8 months")


# ---------- 5. every case can be deleted ----------

def test_an_intake_case_can_be_deleted(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    record = tracker.open_case("General", "Volunteer A")
    sup = AppTest.from_file("../app.py", default_timeout=30)
    sup.session_state["screen"] = "Supervisor"
    for k, v in {"supervisor_ok": True, "supervisor_name": "SK", "sup_last_active": time.time()}.items():
        sup.session_state[k] = v
    sup.run()
    assert any(record["id"] in o for o in sup.selectbox(key="del-case").options)  # intake in progress too
    sup.selectbox(key="del-case").set_value(record["id"])
    sup.text_input(key="del-confirm").set_value("DELETE")
    sup.button(key="del-go").click().run()
    ok(sup)
    assert tracker.load(record["id"]) is None


# ---------- 6. the password hint ----------

def test_password_boxes_hide_the_enter_hint():
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    assert '[data-testid="stTextInput"]:has(input[type="password"]) [data-testid="InputInstructions"] { display: none' in css


# ---------- 7. why no drafts are waiting ----------

def test_no_drafts_waiting_says_why_with_counts(monkeypatch, tmp_path):
    import functools
    monkeypatch.setattr(tracker, "rows", functools.partial(tracker.rows, base=tmp_path))
    monkeypatch.setattr(store, "list_pending", functools.partial(store.list_pending, base=tmp_path))
    for _ in range(3):
        tracker.open_case("General", "Volunteer A", base=tmp_path)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "sup-pass-9")
    sup = AppTest.from_file("../app.py", default_timeout=30)
    sup.session_state["screen"] = "Supervisor"
    for k, v in {"supervisor_ok": True, "supervisor_name": "SK", "sup_last_active": time.time()}.items():
        sup.session_state[k] = v
    sup.run()
    ok(sup)
    assert any("No drafts sent for review yet. 3 cases still at intake." == i.value for i in sup.info)


def test_a_line_that_says_the_same_and_more_replaces_the_shorter_one(tmp_path):
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    tracker.add_summary(case_id, ["She has WhatsApp messages from the employer."], [], [], "Volunteer A", base=tmp_path)
    tracker.add_summary(case_id, ["She has WhatsApp messages from the employer as evidence."], [], [], "Volunteer A", base=tmp_path)
    tracker.add_summary(case_id, ["She has WhatsApp messages from the employer."], [], [], "Volunteer A", base=tmp_path)
    lines = [l for l in tracker.load(case_id, base=tmp_path)["summary"] if "WhatsApp" in l]
    assert lines == ["She has WhatsApp messages from the employer as evidence."]
    assert not tracker.same_line("He was arrested.", "He was arrested in Patna.")   # too short to judge: kept apart


# ---------- wording and consistency ----------

def test_one_and_many_never_say_s_in_brackets():
    import json
    import lang
    for code in ("en", "hi"):
        assert not [k for k, v in json.load(open(Path(__file__).parent.parent / "i18n" / f"{code}.json")).items()
                    if "(s)" in v]
    assert lang.t("none_waiting.intake", n=1) == "1 case still at intake."
    assert lang.t("none_waiting.intake", n=2) == "2 cases still at intake."
    assert lang.t("none_waiting.intake", "hi", n=1) == "1 केस अभी इनटेक में है।"
    assert lang.t("none_waiting.intake", "hi", n=3) == "3 केस अभी इनटेक में हैं।"
    assert lang.t("ready.button_unticked", n=1) == "1 item not ticked"
    assert lang.t("aud.count", n=1, total=1) == "1 of 1 case." and lang.t("aud.count", n=1, total=4) == "1 of 4 cases."


def test_no_outdated_wording_left():
    import json
    import lang
    en = json.load(open(Path(__file__).parent.parent / "i18n" / "en.json"))
    for k, v in en.items():
        assert "by itself" not in v and "at once" not in v and "Research sent to the supervisor" not in v, k
        assert "Any case" not in v, k
    assert lang.t("screen.New case") == "Current case" and "cont.another" not in en and "learn.checked" not in en
    assert lang.t("case_type.General") == "Any problem"


def test_start_a_case_asks_before_leaving_an_open_case(tmp_path, monkeypatch):
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    at.button(key="nav-start").click().run()
    assert "leave_ask" not in at.session_state       # nothing open: starts straight away
    case_id = tracker.open_case("General", "Volunteer A")["id"]
    at.session_state["case_id"] = case_id
    at.button(key="nav-start").click().run()
    assert "Leave this case? It stays saved in Case tracker." in [w.value for w in at.warning]
    at.button(key="leave-no").click().run()
    assert at.session_state["case_id"] == case_id and "leave_ask" not in at.session_state  # same case
    at.button(key="nav-start").click().run()
    at.button(key="leave-yes").click().run()
    assert "case_id" not in at.session_state
    assert not [b for b in at.button if b.key == "case-another"]


# ---------- layout and two small agent features (12 November 2026) ----------

def test_the_ais_reasons_are_shown_only_without_names():
    raw = dict(WAGES_ANSWER, why_asked=["The letter should mention any written proof.",
                                        "Ask Ramesh Kumar whether others were paid."])  # a name: dropped
    notes = WAGES + " Ramesh Kumar is a co-worker."
    reading = general.check_general_answer(raw, notes)
    first, second = WAGES_ANSWER["questions_to_ask"]
    assert reading.question_reasons[first] == "The letter should mention any written proof."
    assert second in reading.questions and second not in reading.question_reasons
    assert not general.reason_is_clean("Call 9876543210 first.", notes)


def test_why_this_is_asked_under_each_question(monkeypatch):
    import html as h
    reasons = dict(WAGES_ANSWER, why_asked=["The letter should mention any written proof."])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", **k: llm.NotesReading(reasons, notes, {}, MODEL))
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    at.text_area(key="g_notes").set_value(WAGES).run()
    at.button(key="g-read").click().run()
    seen = []
    for _ in range(12):
        why = [h.unescape(m.value) for m in at.markdown if 'class="why-asked"' in m.value]
        if not why:
            break
        seen.append(why[0])
        skip = [b for b in at.button if b.key and b.key.startswith("gskip-") and b.key != "gskip-all"]
        if not skip:
            break
        skip[0].click().run()
    ok(at)
    assert "Why this is asked:</b> The letter should mention any written proof." in seen[0]   # the AI's reason
    assert "The agent suggested this to fill a gap in the story." in seen[1]                  # it gave none
    assert "The letter must say what the person is asking for." in seen[2]                   # the app's own


def test_every_fixed_question_has_its_reason_in_english_and_hindi():
    import json
    import intake
    for code in ("en", "hi"):
        strings = json.load(open(ROOT / "i18n" / f"{code}.json", encoding="utf-8"))
        for m in general.ELIGIBILITY_QUESTIONS:
            assert strings[f"whyq.elig.{m}"]
        for fact, _ in intake.FACT_QUESTIONS:
            assert strings[f"whyq.f.{fact}"]
        for key in ("whyq.person", "whyq.outcome", "whyq.year", "whyq.ai_default", "whyq.label"):
            assert strings[key]


def test_what_the_agent_did_card_from_the_audit_record(monkeypatch):
    import audit
    at = wages(monkeypatch)
    make_drafts(at, letter=False)
    ok(at)
    events = [e["event"] for e in audit.read_record(at.session_state["case_id"])["events"]]
    assert "story read" in events and "question asked" in events and "drafts made" in events
    [text] = [m.value for m in at.markdown if 'class="agent-did"' in m.value]
    assert "Story read" in text and "model Google Gemini" in text and MODEL not in text and "Question asked" in text and "Drafts made" in text
    assert "(by " not in text  # who is in the audit table; the card says what was done


def test_one_filled_button_per_screen_and_it_is_the_next_action(monkeypatch):
    at = wages(monkeypatch)
    ok(at)
    filled = lambda: [b.key for b in at.button if b.proto.type == "primary" and b.key not in ("nav-start", "gate-out")]  # noqa: E731
    assert filled() == ["rs-run-go"]                       # step 3: the problem is not in our files: research
    import html as h
    assert h.unescape([m.value for m in at.markdown if 'class="next-label"' in m.value][0]).endswith(">Next:</p>")


def test_sign_in_pages_say_what_they_are_for(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", "practice-pass-123")
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "New case"
    at.run()
    side = [m.value for m in at.markdown if 'class="signin-side"' in m.value]
    assert len(side) == 1 and "What this page is for" in side[0] and 'href="tel:15100"' in side[0]


# ---------- grey-text edits (12 November 2026) ----------

def test_grey_text_edits_and_removed_lines():
    import lang
    assert lang.t("home.how2_p") == "When something is missing, we ask. When something is unclear, we don't guess."
    assert lang.t("visit.caption") == "Each contact gets a dated entry."
    assert lang.t("slip.caption") == ("Give this slip to the person. It contains the clinic name, case number, "
                                      "access code, QR code, and helpline numbers.")
    for key in ("slip.no_url", "ui.practice_only", "eval.caption", "eval.no_sessions", "imp.caption"):
        assert key not in lang.strings("en") and key not in lang.strings("hi"), key
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    for key in ("slip.no_url", "ui.practice_only", "eval.caption", "eval.no_sessions", "imp.caption"):
        assert f't("{key}")' not in source, key


def test_log_a_visit_boxes_say_no_names_or_numbers(monkeypatch):
    import lang
    case_id = tracker.open_case("General", "Volunteer A")["id"]
    for code, text in (("en", "No names or numbers"), ("hi", "कोई नाम या नंबर नहीं")):
        at = AppTest.from_file("../app.py", default_timeout=30)
        at.session_state["screen"] = "New case"
        at.session_state["case_id"] = case_id
        at.session_state["ui_lang"] = code
        at.run()
        at.button(key="case-tab-visit").click().run()
        ok(at)
        boxes = [b for b in list(at.text_area) + list(at.text_input) if str(b.key).startswith("vis-")]
        assert len(boxes) == 3 and all(b.placeholder == text for b in boxes), [(b.key, b.placeholder) for b in boxes]
        assert lang.t("visit.caption", code) in [c.value for c in at.caption]   # the caption is unchanged
