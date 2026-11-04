"""Legal aid agent: Streamlit web app.

Run with:  streamlit run app.py

All visible text comes from i18n/<language>.json through t("key"). Widget keys and the values
the code checks (for example "Yes", "Undertrial", "None") stay in English; only what is shown
is translated.
"""

import hmac
import json
import os
import re
from datetime import date

import streamlit as st

import audit
import drafts
import general
import intake
import lang
import llm
import section479
import store
import timeline

st.set_page_config(page_title="Legal aid agent", page_icon="⚖️", layout="centered")

# Large, readable text on phones and laptops.
st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown p, .stMarkdown li, label { font-size: 1.15rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- language ----------

def code() -> str:
    return st.session_state.get("ui_lang", lang.DEFAULT)


def t(key: str, **params) -> str:
    return lang.t(key, code(), **params)


def show_date(d: date) -> str:
    return lang.show_date(d, code())


# Choice buttons (radios) and lists whose wording changes with the language. In Streamlit, a radio's
# identity includes its label and option wording, so a new language would reset it to its default.
# When the language is switched, these are saved again first, so the new-language widgets keep them.
KEEP_ON_LANGUAGE_SWITCH = ("case_type", "screen", "f_lawyer", "f_draft_lang", "g_draft_lang", "f_offence_pick",
                           "ge-", "q-never", "q-other_cases_pending", "q-delay_days_by_accused", "q-lawyer",
                           "tl-action-", "tl-step-", "action-")
LANGUAGE_LABEL = "Language / \u092d\u093e\u0937\u093e"  # the same in every language, so the switch never resets


def keep_choices():
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(KEEP_ON_LANGUAGE_SWITCH):
            try:
                st.session_state[key] = st.session_state[key]
            except Exception:  # some widgets (buttons) can't be set; they hold no choice anyway
                pass


def language_switch():
    """English / हिंदी at the top of every screen, remembered for the session."""
    st.radio(LANGUAGE_LABEL, list(lang.LANGUAGES), format_func=lang.LANGUAGES.get, horizontal=True,
             key="ui_lang", on_change=keep_choices)


def option_text(prefix: str):
    """format_func for a radio whose values stay in English: shows the value in the current language.
    The language is fixed when the widget is drawn, so the same value always shows the same words."""
    language = code()
    return lambda value: lang.t(prefix + value, language) if (prefix + value) in lang.strings("en") else value


# ---------- New case ----------

# Form fields are kept in session state, so the AI (or the missing-fact questions)
# can fill them in before the form is drawn.
FORM_DEFAULTS = {
    "f_law": "IPC", "f_section": "", "f_offence_date": None, "f_custody": None,
    "f_today": None, "f_never": False, "f_other": False, "f_many": False, "f_delay": 0,
    "f_answer": "", "f_confirm": False, "f_lawyer": None, "f_checked": False,
}
FACT_TO_KEY = {
    "law": "f_law", "section": "f_section", "offence_date": "f_offence_date",
    "custody_began": "f_custody", "today": "f_today", "never_convicted": "f_never",
    "other_cases_pending": "f_other", "more_than_one_section": "f_many",
    "delay_days_by_accused": "f_delay", "answer": "f_answer", "lawyer": "f_lawyer",
}
FACT_LABEL_KEYS = ["custody_began", "offence_date", "today", "section", "law", "more_than_one_section",
                   "never_convicted", "other_cases_pending", "delay_days_by_accused", "lawyer", "answer"]


def fact_label(fact: str) -> str:
    return t(f"fact.{fact}")


def init_form():
    for key, value in FORM_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    if st.session_state["f_today"] is None:
        st.session_state["f_today"] = date.today()


def save_problem(key: str, case_id, where: str):
    text = st.session_state.get(f"problem-{key}", "")
    try:
        audit.report_problem(text, case_id, where)
    except ValueError:
        st.session_state[f"problem-msg-{key}"] = ("error", t("ui.problem.empty"))
        return
    st.session_state[f"problem-{key}"] = ""
    st.session_state[f"problem-msg-{key}"] = ("ok", t("ui.problem.thanks"))


def report_problem_box(key: str, where: str, case_id=None):
    """A small "Report a problem" box. Saved to the problems log with the case number and date."""
    with st.expander(t("ui.problem.title")):
        st.caption(t("ui.problem.caption"))
        st.text_area(t("ui.problem.what"), key=f"problem-{key}", max_chars=audit.MAX_PROBLEM_LENGTH, height=100)
        st.button(t("ui.problem.send"), key=f"problem-send-{key}", on_click=save_problem, args=(key, case_id, where))
        msg = st.session_state.pop(f"problem-msg-{key}", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


def ai_info_for_audit():
    """What the AI did for this form, for the audit record (None if no AI was used)."""
    ai = st.session_state.get("ai")
    if not ai:
        return None
    reading = ai["reading"]
    return {"model": ai["model"], "read_at": ai["read_at"], "extracted": dict(reading.values),
            "not_accepted": sorted({d.split(":")[0] for d in reading.dropped})}


def new_case_screen():
    st.title(t("ui.new_case.title"))
    st.caption(t("ui.new_case.caption"))

    case_type = st.radio(t("ui.new_case.kind"), CASE_TYPES, horizontal=True, key="case_type",
                         format_func=option_text("case_type."))
    if case_type == ANY_CASE:
        general_screen()
    else:
        init_form()
        notes_box()
        if not ask_missing_facts():  # while missing facts are asked one at a time, the form waits
            undertrial_form()
    sent = st.session_state.get("sent") if case_type != ANY_CASE else None
    case_id = sent["id"] if sent else st.session_state.get("gen_sent")
    report_problem_box("new-case", "New case", case_id)


# ----- voice: "Speak the story" -----

def transcribe_recording(audio_key: str, target_key: str):
    """Runs when "Turn speech into text" is clicked. The recording is only sent to Gemini to become
    text; it is never saved. The text goes through the privacy filter, then into the notes box."""
    st.session_state.pop(f"{audio_key}-msg", None)
    recording = st.session_state.get(audio_key)
    if recording is None:
        st.session_state[f"{audio_key}-msg"] = ("error", t("ui.voice.nothing"))
        return
    try:
        transcript = llm.transcribe(recording.getvalue(), getattr(recording, "type", None) or "audio/wav",
                                    script=code())
    except llm.AIUnavailable as err:
        st.session_state[f"{audio_key}-msg"] = ("error", f"{err} {t('ui.voice.type_instead')}")
        return
    if not transcript.text:
        st.session_state[f"{audio_key}-msg"] = ("error", t("ui.voice.nothing_heard"))
        return
    before = st.session_state.get(target_key, "").rstrip()
    st.session_state[target_key] = (before + "\n" if before else "") + transcript.text
    msg = t("ui.voice.done")
    if transcript.removed:
        msg += " " + t("ui.voice.removed", what=", ".join(f"{n} × {k}" for k, n in transcript.removed.items()))
    st.session_state[f"{audio_key}-msg"] = ("ok", msg)


def voice_box(audio_key: str, target_key: str):
    with st.expander(t("ui.voice.title")):
        st.warning(t("ui.voice.warning"))
        if not llm.available():
            st.info(t("ui.voice.no_ai"))
            return
        st.audio_input(t("ui.voice.record"), key=audio_key)
        st.button(t("ui.voice.convert"), key=f"{audio_key}-go", on_click=transcribe_recording,
                  args=(audio_key, target_key))
        st.caption(t("ui.voice.caption"))
        msg = st.session_state.pop(f"{audio_key}-msg", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


# ----- any case: general intake -----

ANY_CASE = "Any case (start here)"
CASE_TYPES = [ANY_CASE, "Undertrial"]


def case_type_label(case_type: str) -> str:
    return t("case_type.General") if case_type == general.CASE_TYPE else t(f"case_type.{case_type}")


def _start_general(reading, model, removed):
    st.session_state["gen"] = {"reading": reading, "model": model, "read_at": audit.now(), "removed": removed,
                               "facts": dict(reading.facts), "answers": [], "q_index": 0,
                               "unanswered": [], "skipped": set(), "done": False}
    for key in ("g_checked", "gen_sent"):
        st.session_state.pop(key, None)


def read_general():
    """Runs when "Read the story" is clicked."""
    st.session_state.pop("gen_error", None)
    try:
        notes_reading = llm.read_general_notes(st.session_state.get("g_notes", ""), output_lang=code())
    except llm.AIUnavailable as err:
        st.session_state["gen_error"] = str(err)
        return
    reading = general.check_general_answer(notes_reading.answer, notes_reading.notes_sent)
    _start_general(reading, notes_reading.model, notes_reading.removed)


def start_general_without_ai():
    text = st.session_state.get("g_manual", "")
    reading = general.GeneralReading(
        what_happened=[general.clean(x) for x in re.split(r"(?<=[.!?।])\s+", text) if x.strip()][:6],
        issues=[("other", t("ui.general.problem_described"))])
    st.session_state.pop("gen_error", None)
    _start_general(reading, None, {})


def clear_general():
    for key in ["gen", "gen_error", "g_notes", "g_manual", "g_checked", "gen_sent"]:
        st.session_state.pop(key, None)


def open_section479():
    """Hand the same story to the undertrial reader, so the Section 479 form is filled in."""
    st.session_state["case_type"] = "Undertrial"
    st.session_state["f_notes"] = st.session_state.get("g_notes", "")
    read_notes()


def general_question(gen):
    """The next question to ask: the AI's questions first (most important first), then only
    the facts the free legal aid check still needs."""
    if gen["done"]:
        return None
    questions = gen["reading"].questions
    if gen["q_index"] < len(questions):
        return ("ai", gen["q_index"], questions[gen["q_index"]])
    missing = [m for m in general.check_eligibility(gen["facts"]).missing if m not in gen["skipped"]]
    if missing:
        return ("eligibility", missing[0], t(f"elig.q.{missing[0]}"))
    return None


def answer_general(kind: str, ref, skip: bool = False):
    gen = st.session_state["gen"]
    get = st.session_state.get
    if kind == "ai":
        question = gen["reading"].questions[ref]
        text = (get(f"gq-{ref}") or "").strip()
        if skip:
            gen["unanswered"].append(question)
        elif text:
            gen["answers"].append((question, text))
        else:
            return  # nothing typed yet: stay on this question
        gen["q_index"] += 1
        return
    fact = ref
    if fact == "state":
        value = get("ge-state")
    elif fact == "annual_income":
        amount, per = get("ge-income"), get("ge-income-per")
        value = int(amount) * (12 if per == "per month" else 1) if amount is not None and per else None
    else:
        choice = get(f"ge-{fact}")
        value = {"Yes": True, "No": False}.get(choice)
        if choice == "Not sure":
            skip = True
    if skip:
        gen["skipped"].add(fact)
    elif value is not None:
        gen["facts"][fact] = value


def skip_general_questions():
    gen = st.session_state["gen"]
    gen["unanswered"] += gen["reading"].questions[gen["q_index"]:]
    gen["q_index"] = len(gen["reading"].questions)
    gen["done"] = True


URGENT_KEYS = {general.CALL_112: "safety.call112", general.CALL_1930: "safety.call1930"}


def general_screen():
    st.header(t("ui.general.header"))
    gen = st.session_state.get("gen")
    if gen:  # urgent actions always at the top
        for action in general.urgent_actions(gen["facts"]):
            st.error(f"## \U0001F6A8 {t(URGENT_KEYS[action])}")

    with st.expander(t("ui.general.story_box"), expanded=gen is None):
        st.warning(t("ui.general.names_warning"))
        if llm.available():
            voice_box("g_audio", "g_notes")
            st.text_area(t("ui.general.story_label"), key="g_notes", height=220,
                         placeholder=t("ui.general.story_placeholder"))
            col1, col2 = st.columns(2)
            col1.button(t("ui.general.read"), type="primary", on_click=read_general)
            if gen:
                col2.button(t("ui.general.clear"), on_click=clear_general)
        else:
            st.info(t("ui.general.no_ai"))
        if not llm.available() or st.session_state.get("gen_error"):
            st.text_area(t("ui.general.manual_label"), key="g_manual", height=120)
            st.button(t("ui.general.start_without_ai"), on_click=start_general_without_ai)
    if st.session_state.get("gen_error"):
        st.error(st.session_state["gen_error"] + " " + t("ui.general.type_instead"))
    if not gen:
        return

    if gen["removed"]:
        st.caption(t("ui.removed_before_sending") + ", ".join(f"{n} × {k}" for k, n in gen["removed"].items()))

    question = general_question(gen)
    if question:
        kind, ref, text = question
        st.subheader(t("ui.general.questions"))
        with st.container(border=True):
            st.markdown(f"**{text}**")
            if kind == "ai":
                st.text_input(t("ui.general.answer_no_names"), key=f"gq-{ref}", max_chars=300)
            elif ref == "state":
                st.selectbox(t("ui.general.state"), general.state_names(), index=None, key="ge-state")
            elif ref == "annual_income":
                col1, col2 = st.columns(2)
                col1.number_input(t("ui.general.amount"), min_value=0, step=500, value=None, key="ge-income")
                col2.radio(t("ui.general.per"), ["per month", "per year"], index=None, key="ge-income-per",
                           horizontal=True, format_func=option_text("opt."))
            else:
                st.radio(t("ui.answer"), ["Yes", "No", "Not sure"], index=None, key=f"ge-{ref}", horizontal=True,
                         format_func=option_text("opt."))
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.button(t("ui.next"), type="primary", key=f"gnext-{kind}-{ref}", on_click=answer_general,
                        args=(kind, ref))
            col2.button(t("ui.dont_know"), key=f"gskip-{kind}-{ref}", on_click=answer_general, args=(kind, ref, True))
            col3.button(t("ui.general.skip_rest"), key="gskip-all", on_click=skip_general_questions)
        return

    general_summary(gen)


def draft_language_choice(key: str) -> str:
    st.session_state.setdefault(key, code())
    return st.radio(t("ui.draft_language"), list(lang.LANGUAGES), format_func=lang.LANGUAGES.get,
                    horizontal=True, key=key)


def general_summary(gen):
    reading = gen["reading"]
    eligibility = general.check_eligibility(gen["facts"])
    still_to_ask = gen["unanswered"] + [general.ELIGIBILITY_QUESTIONS[m] for m in eligibility.missing]
    facts = general.build_facts(reading, gen["answers"], still_to_ask, gen["facts"], date.today())

    categories = [c for c, _ in reading.issues]
    if "arrest_or_custody" in categories:
        st.info(t("ui.general.custody_info"))
        st.button(t("ui.general.open_479"), on_click=open_section479, disabled=not llm.available())
    if "online_or_financial_fraud" in categories:
        st.info(t("ui.general.cyber_info"))

    st.subheader(t("ui.general.summary"))
    draft_lang = draft_language_choice("g_draft_lang")
    draft = general.make_summary_draft(facts, gen["model"], draft_lang)
    if draft_lang == "hi":
        st.caption(t("ui.hindi_label_note"))
    st.code(draft, language=None, wrap_lines=True)
    names = general.possible_names(draft, st.session_state.get("g_notes", ""))
    if names:
        st.warning(t("ui.general.possible_names", names=", ".join(names)))

    sent = st.session_state.get("gen_sent")
    if sent:
        st.success(t("ui.sent", case_id=sent))
        report_problem_box("gen-draft", "Any-case summary", sent)
        return
    checked = st.checkbox(t("ui.general.checked_no_names"), key="g_checked")
    if st.button(t("ui.send_to_supervisor"), disabled=not checked):
        ai = None
        if gen["model"]:
            ai = {"model": gen["model"], "read_at": gen["read_at"], "extracted": dict(reading.facts),
                  "not_accepted": sorted(set(reading.dropped))}
        try:
            case_id = store.submit(draft, facts, ai=ai, draft_lang=draft_lang)
        except ValueError as err:
            st.error(str(err))
            return
        st.session_state["gen_sent"] = case_id
        st.rerun()
    report_problem_box("gen-draft", "Any-case summary", None)


# ----- the undertrial notes -----

def show_value(value) -> str:
    if isinstance(value, bool):
        return t("yes") if value else t("no")
    if isinstance(value, date):
        return show_date(value)
    return str(value)


def apply_to_form(values: dict):
    for fact, value in values.items():
        key = FACT_TO_KEY.get(fact)
        if key and value is not None:
            st.session_state[key] = value
    if values.get("answer"):
        st.session_state["f_confirm"] = False  # the volunteer confirms the row on the form


def read_notes():
    """Runs when "Read notes" is clicked, before the page is drawn again."""
    st.session_state.pop("ai_error", None)
    try:
        notes_reading = llm.read_undertrial_notes(st.session_state.get("f_notes", ""))
    except llm.AIUnavailable as err:
        st.session_state["ai_error"] = str(err)
        return
    reading = intake.check_ai_answer(notes_reading.answer, notes_reading.notes_sent)
    removed = notes_reading.removed
    for key, value in FORM_DEFAULTS.items():  # start from an empty form
        st.session_state[key] = value
    st.session_state["f_today"] = date.today()
    st.session_state["ai"] = {"reading": reading, "removed": removed, "skipped": set(),
                              "values": dict(reading.values), "model": notes_reading.model,
                              "read_at": audit.now()}
    st.session_state.pop("draft", None)
    if not intake.missing_facts(reading.values):
        apply_to_form(reading.values)


def clear_notes():
    for key in list(FORM_DEFAULTS) + ["ai", "ai_error", "f_notes", "draft"]:
        st.session_state.pop(key, None)


def notes_box():
    ai = st.session_state.get("ai")
    with st.expander(t("ui.notes.box"), expanded=ai is None):
        st.warning(t("ui.notes.warning"))
        if not llm.available():
            st.info(t("ui.notes.no_ai"))
            return
        voice_box("f_audio", "f_notes")
        st.text_area(t("ui.notes.label"), key="f_notes", height=220, placeholder=t("ui.notes.placeholder"))
        col1, col2 = st.columns(2)
        col1.button(t("ui.notes.read"), type="primary", on_click=read_notes)
        if ai:
            col2.button(t("ui.notes.clear"), on_click=clear_notes)
    if st.session_state.get("ai_error"):
        st.error(st.session_state["ai_error"] + " " + t("ui.notes.by_hand"))


# ----- asking for missing facts, one at a time -----

def answer_fact(fact: str, skip: bool = False):
    """Runs when Next or Don't know is clicked. Reads the answer at click time."""
    ai = st.session_state["ai"]
    value = None if skip else read_answer(fact)
    if value is None and st.session_state.get(f"q-{fact}") == "Not sure":
        skip = True  # "Not sure" counts as "Don't know"
    if fact == "never_convicted" and st.session_state.get("q-never") == "Not sure":
        skip = True
    if value is None:
        if not skip:
            return  # nothing given yet: stay on this question
        ai["skipped"].add(fact)
    else:
        ai["values"][fact] = value
        if fact == "section":
            ai["values"]["law"] = st.session_state.get("q-law", "IPC")
            ai["values"]["more_than_one_section"] = bool(st.session_state.get("q-many"))
    if not intake.missing_facts(ai["values"], ai["skipped"]):
        apply_to_form(ai["values"])


def skip_all():
    ai = st.session_state["ai"]
    ai["skipped"].update(intake.missing_facts(ai["values"], ai["skipped"]))
    apply_to_form(ai["values"])


def intake_question(number: int) -> str:
    """The question from knowledge/intake_undertrial.md, in Hindi from hi.json when chosen."""
    english = intake.intake_questions()[number]
    return lang.strings(code()).get(f"intake.q.{number}", english) if code() != "en" else english


def ask_missing_facts() -> bool:
    """Ask the first missing fact. Returns True while questions remain."""
    ai = st.session_state.get("ai")
    if not ai:
        return False
    missing = intake.missing_facts(ai["values"], ai["skipped"])
    if not missing:
        return False

    fact = missing[0]
    number = dict(intake.FACT_QUESTIONS)[fact]
    st.subheader(t("ui.missing.title", n=len(missing)))
    if ai["removed"]:
        st.caption(t("ui.removed_before_sending") + ", ".join(f"{n} × {k}" for k, n in ai["removed"].items()))
    found = {f: v for f, v in ai["values"].items() if f in FACT_LABEL_KEYS}
    if found:
        st.caption(t("ui.missing.found") + "; ".join(f"{fact_label(f)}: {show_value(v)}" for f, v in found.items()))

    with st.container(border=True):
        question = intake_question(number)
        if fact == "answer":
            question = intake.offence_question(ai["values"])
        st.markdown(f"**{question}**")
        if fact in ai["reading"].notes_say:
            st.caption(t("ui.missing.notes_say", quote=ai["reading"].notes_say[fact]))
        question_widget(fact)
        col1, col2, col3 = st.columns([1, 1, 2])
        col1.button(t("ui.next"), type="primary", key=f"next-{fact}", on_click=answer_fact, args=(fact,))
        col2.button(t("ui.dont_know"), key=f"skip-{fact}", on_click=answer_fact, args=(fact, True))
        col3.button(t("ui.missing.skip_rest"), key="skip-all", on_click=skip_all)
    return True


def question_widget(fact: str):
    """Draw one input for one missing fact."""
    opt = option_text("opt.")
    if fact in ("custody_began", "offence_date"):
        st.date_input(t("ui.date"), value=None, format="DD/MM/YYYY", key=f"q-{fact}",
                      min_value=date(1990, 1, 1), max_value=date.today())
    elif fact == "section":
        col1, col2 = st.columns([1, 2])
        col1.selectbox(t("fact.law"), ["IPC", "BNS"], key="q-law")
        col2.text_input(t("ui.form.section"), key="q-section", placeholder=t("ui.missing.section_example"))
        st.checkbox(t("ui.missing.many"), key="q-many")
    elif fact == "never_convicted":
        st.radio(t("ui.answer"), ["Never", "Yes", "Not sure"], index=None, key="q-never", horizontal=True,
                 format_func=opt)
    elif fact in ("other_cases_pending", "delay_days_by_accused"):
        st.radio(t("ui.answer"), ["No", "Yes", "Not sure"], index=None, key=f"q-{fact}", horizontal=True,
                 format_func=opt)
        if fact == "delay_days_by_accused" and st.session_state.get("q-delay_days_by_accused") == "Yes":
            st.number_input(t("ui.missing.delay_days"), min_value=1, step=1, value=None, key="q-delay-days")
    elif fact == "answer":
        st.text_input(t("ui.answer"), key="q-answer", max_chars=200)
    elif fact == "lawyer":
        st.radio(t("ui.answer"), drafts.LAWYER_OPTIONS, index=None, key="q-lawyer", format_func=option_text("lawyer."))


def read_answer(fact: str):
    """The answer given to a missing-fact question, or None if none (or "Not sure")."""
    get = st.session_state.get
    if fact in ("custody_began", "offence_date"):
        return get(f"q-{fact}")
    if fact == "section":
        return (get("q-section") or "").strip() or None
    if fact == "never_convicted":
        return {"Never": True, "Yes": False}.get(get("q-never"))
    if fact == "other_cases_pending":
        return {"No": False, "Yes": True}.get(get("q-other_cases_pending"))
    if fact == "delay_days_by_accused":
        choice = get("q-delay_days_by_accused")
        if choice == "No":
            return 0
        if choice == "Yes" and get("q-delay-days"):
            return int(get("q-delay-days"))
        return None
    if fact == "answer":
        return (get("q-answer") or "").strip() or None
    if fact == "lawyer":
        return get("q-lawyer")
    return None


# ----- the undertrial form -----

def checked_by_volunteer() -> bool:
    """After an AI reading, the volunteer must check every field before the calculator runs."""
    ai = st.session_state.get("ai")
    if not ai:
        return True
    reading = ai["reading"]
    with st.container(border=True):
        st.markdown(f"**{t('ui.check.title')}**")
        rows = [f"- {fact_label(f)}: {show_value(v)} — {t('ui.check.notes')}: “{reading.evidence[f]}”"
                for f, v in reading.values.items() if f in FACT_LABEL_KEYS and f in reading.evidence]
        asked = [f for f in ai["values"] if f not in reading.values and f in FACT_LABEL_KEYS]
        if rows:
            st.markdown(t("ui.check.found") + "\n" + "\n".join(rows))
        if asked:
            st.markdown(t("ui.check.you_answered") + ", ".join(fact_label(f) for f in asked))
        unknown = [fact_label(f) for f in ai["skipped"] if f in FACT_LABEL_KEYS]
        if unknown:
            st.warning(t("ui.check.still_unknown", what=", ".join(unknown)))
        if reading.values.get("all_sections"):
            st.warning(t("ui.check.many_sections", sections=", ".join(reading.values["all_sections"])))
        return st.checkbox(t("ui.check.box"), key="f_checked")


def undertrial_form():
    st.header(t("ui.form.header"))

    col1, col2 = st.columns([1, 2])
    law = col1.selectbox(t("fact.law"), ["IPC", "BNS"], key="f_law")
    section = col2.text_input(t("ui.form.section"), placeholder=t("ui.form.section_example"), key="f_section")

    offence_date = st.date_input(t("fact.offence_date"), format="DD/MM/YYYY", key="f_offence_date",
                                 min_value=date(1990, 1, 1), max_value=date.today(),
                                 help=t("ui.form.offence_date_help"))
    custody_began = st.date_input(t("fact.custody_began"), format="DD/MM/YYYY", key="f_custody",
                                  min_value=date(1990, 1, 1), max_value=date.today())
    today = st.date_input(t("fact.today"), format="DD/MM/YYYY", key="f_today")

    never_convicted = st.checkbox(t("ui.form.never"), key="f_never")
    other_cases = st.checkbox(t("ui.form.other"), key="f_other")
    many_sections = st.checkbox(t("ui.form.many"), key="f_many")
    delay_days = st.number_input(t("ui.form.delay"), min_value=0, step=1, key="f_delay")

    if not section.strip():
        st.info(t("ui.form.type_section"))
        return

    matches = section479.find_offences(law, section)
    if not matches:
        st.warning(t("ui.form.not_in_table", law=law, section=section))
        return

    if len(matches) > 1:
        labels = [f"BNS {o.bns_section} / IPC {o.ipc_section}: {o.offence}" for o in matches]
        picked = st.radio(t("ui.form.which_offence"), labels, key="f_offence_pick")
        if picked not in labels:
            picked = labels[0]
        offence = matches[labels.index(picked)]
    else:
        offence = matches[0]

    question_answered = False
    answer = ""
    if offence.ask_to_decide:
        st.markdown(f"**{t('ui.form.deciding_question')}** {offence.ask_to_decide}")
        if offence.notes:
            st.caption(offence.notes)
        answer = st.text_input(t("ui.form.answer_empty"), max_chars=200,
                               placeholder=t("ui.form.answer_example"), key="f_answer")
        confirmed = st.checkbox(t("ui.form.confirm_row"), key="f_confirm")
        question_answered = bool(answer.strip()) and confirmed
        if not question_answered:
            st.caption(t("ui.form.until_answered"))

    if not checked_by_volunteer():
        st.info(t("ui.check.tick_first"))
        return

    if custody_began is None:
        st.info(t("ui.form.pick_custody"))
        return

    try:
        result = section479.calculate(
            offence,
            custody_began=custody_began,
            today=today,
            never_convicted=never_convicted,
            other_cases_pending=other_cases,
            more_than_one_section=many_sections,
            question_answered=question_answered,
            delay_days_by_accused=int(delay_days),
            offence_date=offence_date,
        )
    except section479.InputError as err:
        st.error(t(err.key))
        return
    except ValueError as err:
        st.error(str(err))
        return

    show_result(result)

    if result.applies:
        draft_section(
            dict(
                law_typed=law,
                section_typed=section,
                custody_began=custody_began,
                today=today,
                never_convicted=never_convicted,
                other_cases_pending=other_cases,
                more_than_one_section=many_sections,
                question_answered=question_answered,
                delay_days_by_accused=int(delay_days),
                offence_name=offence.offence,
                offence_date=offence_date,
                answer=answer.strip(),
            ),
            result,
        )


def draft_section(known: dict, result: section479.Result):
    st.divider()
    st.subheader(t("ui.draft.title"))
    if known["offence_date"] is None:
        st.info(t("ui.draft.need_offence_date"))
        return
    lawyer = st.radio(t("ui.draft.lawyer_question"), drafts.LAWYER_OPTIONS, key="f_lawyer",
                      format_func=option_text("lawyer."))
    if lawyer is None:
        st.info(t("ui.draft.answer_first"))
        return
    draft_lang = draft_language_choice("f_draft_lang")
    facts = drafts.UndertrialFacts(lawyer=lawyer, **known)
    ai_info = ai_info_for_audit()
    ai_model = ai_info["model"] if ai_info else None
    signature = json.dumps({**facts.to_dict(), "ai_model": ai_model, "lang": draft_lang}, sort_keys=True)

    if st.button(t("ui.draft.make"), type="primary"):
        st.session_state["draft"] = {"sig": signature, "text": drafts.make_undertrial_draft(
            facts, result, ai_model=ai_model, code=draft_lang)}

    draft = st.session_state.get("draft")
    if not draft or draft["sig"] != signature:
        return  # no draft yet, or the facts changed since it was made

    if lawyer == "None":
        st.caption(t("ui.draft.dlsa_added"))
    if draft_lang == "hi":
        st.caption(t("ui.hindi_label_note"))
    st.code(draft["text"], language=None, wrap_lines=True)
    st.caption(t("ui.draft.blanks"))

    sent = st.session_state.get("sent")
    report_problem_box("draft", "Draft on New case",
                       sent["id"] if sent and sent["sig"] == signature else None)
    if sent and sent["sig"] == signature:
        st.success(t("ui.sent", case_id=sent["id"]))
    elif st.button(t("ui.send_to_supervisor")):
        try:
            case_id = store.submit(draft["text"], facts, ai=ai_info, draft_lang=draft_lang)
        except ValueError as err:
            st.error(str(err))
            return
        st.session_state["sent"] = {"sig": signature, "id": case_id}
        st.rerun()


def show_result(result: section479.Result):
    o = result.offence
    st.divider()
    st.subheader(t("ui.result.title"))
    st.markdown(
        f"- **{t('ui.result.offence')}** {o.offence}\n"
        f"- **{t('ui.result.bns')}** {o.bns_section}\n"
        f"- **{t('ui.result.ipc')}** {o.ipc_section}\n"
        f"- **{t('ui.result.maximum')}** "
        + (t("ui.result.maximum_value", months=result.maximum.months, section=result.maximum.section)
           if result.maximum.months is not None else result.maximum.value)
    )
    reason = section479.maximum_reason(result.maximum, code())
    if reason:
        st.caption(reason + (f"  \n{result.maximum.source_line}" if result.maximum.source_line else ""))

    reasons = section479.texts(result, code())
    if not result.applies:
        for r in reasons:
            st.error(r)
    else:
        if result.lawyer_check:
            st.warning(t("ui.result.lawyer_check"))
        for m in (result.one_third, result.one_half):
            name = t(m.key) if m.key else m.name
            note = t(m.note_key) if m.note_key else m.note
            if m.when is None:
                st.markdown(f"**{name}:** {t('ui.result.not_available')} {note}")
                continue
            status = t("ui.result.reached") if m.reached else t("ui.result.not_reached")
            st.markdown(f"**{name}** ({t('ui.result.months', months=section479.format_months(m.months))}): "
                        f"{show_date(m.when)} — {status}")
            if note:
                st.caption(note)
        for r in reasons:
            st.caption(r)

    st.info(t("s479.not_automatic"))

    src = section479.knowledge_source("How to work out the Section 479 dates")
    st.caption(
        f"Source: {src['source']} — {src['link']}  \n"
        f"{t('ui.result.table_source')} {o.source_url}  \n"
        f"{t('ui.result.checked')} {src.get('checked', 'not stated')}"
    )


# ---------- other screens ----------

STATUS_KEYS = {store.WAITING: "ui.status.waiting", store.APPROVED: "ui.status.approved",
               store.SENT_BACK: "ui.status.sent_back"}
STEP_ICONS = {timeline.TO_DO: "⬜", timeline.DONE: "✅", timeline.NOT_NEEDED: "➖"}


def step_title(s: timeline.Step) -> str:
    """Fixed steps (Section 479, DLSA) in the chosen language; summary steps as they were written."""
    if code() == "en":
        return s.title
    return lang.strings(code()).get(f"step.{s.id}") or lang.strings(code()).get(f"next:{s.title}") or s.title


def step_label(s: timeline.Step) -> str:
    if not s.due:
        return ""
    if s.eligibility_date:
        return t("tl.eligibility")
    if s.kind == timeline.LEGAL:
        return t("tl.legal")
    return t("tl.entered") if s.kind == timeline.ENTERED else t("tl.suggested")


def step_due_text(s: timeline.Step) -> str:
    return " — " + t("tl.due", date=show_date(s.due_date()), label=step_label(s)) if s.due else ""


def due_this_week_box():
    st.subheader(t("ui.cases.due_this_week"))
    items = timeline.due_this_week(date.today())
    if not items:
        st.caption(t("ui.cases.nothing_due"))
    for case_id, s, state in items:
        line = f"**{show_date(s.due_date())}** · {t('ui.case')} {case_id} · {step_title(s)} ({step_label(s)})"
        if state == timeline.OVERDUE:
            st.error(t("tl.overdue") + " · " + line)
        elif state == timeline.ELIGIBILITY:
            st.warning(line)
        else:
            st.info(line)


def save_step(case_id: str):
    get = st.session_state.get
    step_id, action = get(f"tl-step-{case_id}"), get(f"tl-action-{case_id}")
    when, by = get(f"tl-date-{case_id}") or date.today(), get(f"tl-by-{case_id}", "")
    try:
        if action == "Mark done":
            details = {}
            if step_id == "dlsa-lawyer":
                meeting = get(f"tl-meeting-{case_id}")
                details = {"first meeting": meeting.isoformat() if meeting else "not yet",
                           "documents handed over": "yes" if get(f"tl-docs-{case_id}") else "no"}
            timeline.mark_done(case_id, step_id, when, by, details)
        elif action == "Not needed":
            timeline.mark_not_needed(case_id, step_id, by)
        elif action == "Set date":
            timeline.set_due(case_id, step_id, when, by)
        elif action == "Undo (back to to do)":
            timeline.reopen(case_id, step_id, by)
        else:
            raise ValueError(t("tl.choose"))
    except ValueError as err:
        st.session_state[f"tl-msg-{case_id}"] = ("error", str(err))
        return
    st.session_state[f"tl-msg-{case_id}"] = ("ok", t("tl.saved"))
    st.session_state[f"tl-step-{case_id}"] = None


def timeline_box(case_id: str):
    record = timeline.load(case_id)
    if not record:
        st.caption(t("tl.none"))
        return
    steps = timeline.steps_of(record)
    today = date.today()
    with st.expander(t("tl.title"), expanded=True):
        nxt = timeline.next_due(steps, today)
        if nxt:
            text = f"**{t('tl.next')}** {step_title(nxt)}{step_due_text(nxt)}"
            (st.error if timeline.is_overdue(nxt, today) else st.success)(text)
        for s in timeline.ordered(steps):
            line = f"{STEP_ICONS[s.status]} **{step_title(s)}**{step_due_text(s)}"
            if s.status == timeline.DONE:
                line += " — " + t("tl.done")
                line += f" {t('tl.on')} {show_date(date.fromisoformat(s.done_on))}" if s.done_on else ""
                line += f" {t('tl.by')} {s.done_by}" if s.done_by else ""
                if s.details:
                    line += " (" + "; ".join(f"{k}: {v}" for k, v in s.details.items()) + ")"
            elif s.status == timeline.NOT_NEEDED:
                line += " — " + t("tl.not_needed")
            if timeline.is_overdue(s, today):
                st.error(t("tl.overdue") + " · " + line)
            elif timeline.is_reached(s, today):
                st.warning(t("tl.reached", date=show_date(s.due_date())) + f" · {line}")
            else:
                st.markdown(line)
            note = lang.strings(code()).get(f"step_note.{s.id}") if code() != "en" else None
            notes = [n for n in (note or s.note, s.source_line) if n]
            if notes:
                st.caption("  \n".join(notes))

        st.markdown(f"**{t('tl.update')}**")
        by_id = {s.id: s for s in steps}
        step_id = st.selectbox(t("tl.step"), list(by_id), index=None, key=f"tl-step-{case_id}",
                               format_func=lambda i: f"{step_title(by_id[i])} ({t('tl.status.' + by_id[i].status)})")
        if step_id:
            step = by_id[step_id]
            if step.status == timeline.TO_DO:
                actions = ["Mark done", "Not needed"] + (["Set date"] if step.due_editable else [])
            else:
                actions = ["Undo (back to to do)"]
            action = st.radio(t("tl.what_happened"), actions, index=None, horizontal=True,
                              key=f"tl-action-{case_id}", format_func=option_text("tl.action."))
            if action in ("Mark done", "Set date"):
                st.date_input(t("tl.date_done") if action == "Mark done" else t("tl.date_follow_up"),
                              value=date.today(), format="DD/MM/YYYY", key=f"tl-date-{case_id}")
            if action == "Mark done" and step_id == "dlsa-lawyer":
                st.date_input(t("tl.first_meeting"), value=None, format="DD/MM/YYYY", key=f"tl-meeting-{case_id}")
                st.checkbox(t("tl.documents_handed"), key=f"tl-docs-{case_id}")
            st.text_input(t("tl.done_by"), max_chars=60, key=f"tl-by-{case_id}")
            st.button(t("tl.save"), key=f"tl-save-{case_id}", on_click=save_step, args=(case_id,))
        msg = st.session_state.pop(f"tl-msg-{case_id}", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


def my_cases_screen():
    st.title(t("ui.cases.title"))
    due_this_week_box()
    cases = store.list_cases()
    if not cases:
        st.info(t("ui.cases.none"))
        return
    for c in cases:
        with st.container(border=True):
            st.markdown(f"**{t('ui.case_title', case_id=c['id'])}** · {case_type_label(c['case_type'])}  \n"
                        f"{t(STATUS_KEYS[c['status']])}")
            if c["status"] == store.SENT_BACK:
                st.warning(t("ui.cases.reason", reason=c["reason"]))
                fix_and_resend(c["id"])
            if c["status"] == store.APPROVED:
                timeline_box(c["id"])
                with st.expander(t("ui.cases.case_file")):
                    st.markdown(c["file"].read_text(encoding="utf-8"))
                draft_file = c["file"].parent.parent / "drafts" / c["file"].name
                if draft_file.exists():
                    with st.expander(t("ui.cases.approved_draft")):
                        st.code(draft_file.read_text(encoding="utf-8"), language=None, wrap_lines=True)
            report_problem_box(f"case-{c['id']}", "My cases", c["id"])


def fix_and_resend(case_id: str):
    flag = f"fixing-{case_id}"
    if not st.session_state.get(flag):
        if st.button(t("ui.cases.fix"), key=f"fix-{case_id}"):
            st.session_state[flag] = True
            st.rerun()
        return
    record = store.get_pending(case_id)
    fixed = st.text_area(t("ui.cases.fix_label"), value=record["draft"], height=500, key=f"fixtext-{case_id}")
    st.caption(t("ui.cases.fix_caption"))
    col1, col2 = st.columns(2)
    if col1.button(t("ui.cases.resend"), type="primary", key=f"resend-{case_id}"):
        try:
            store.resend(case_id, fixed)
        except ValueError as err:
            st.error(str(err))
            return
        st.session_state[flag] = False
        st.rerun()
    if col2.button(t("ui.cancel"), key=f"cancel-{case_id}"):
        st.session_state[flag] = False
        st.rerun()


def learn_screen():
    st.title(t("ui.learn.title"))
    st.info(t("ui.learn.soon"))


def supervisor_password() -> str:
    """Read the supervisor password from an environment variable or Streamlit secrets.
    It is never written in the code."""
    if os.environ.get("SUPERVISOR_PASSWORD"):
        return os.environ["SUPERVISOR_PASSWORD"]
    try:
        return st.secrets.get("SUPERVISOR_PASSWORD", "")
    except Exception:  # no secrets file
        return ""


def supervisor_screen():
    st.title(t("ui.sup.title"))
    expected = supervisor_password()
    if not expected:
        st.warning(t("ui.sup.no_password"))
        return
    if not st.session_state.get("supervisor_ok"):
        typed = st.text_input(t("ui.sup.password"), type="password")
        if st.button(t("ui.sup.sign_in")):
            if hmac.compare_digest(typed, expected):
                st.session_state["supervisor_ok"] = True
                st.rerun()
            else:
                st.error(t("ui.sup.wrong"))
        return
    top1, top2 = st.columns([3, 1])
    top1.success(t("ui.sup.signed_in"))
    if top2.button(t("ui.sup.sign_out")):
        st.session_state["supervisor_ok"] = False
        st.rerun()

    flash = st.session_state.pop("supervisor_flash", None)
    if flash:
        st.success(flash)

    waiting = store.list_pending()
    if not waiting:
        st.info(t("ui.sup.none_waiting"))
    else:
        st.subheader(t("ui.sup.waiting", n=len(waiting)))
        for record in waiting:
            review_one(record)

    st.subheader(t("ui.sup.problems"))
    problems = audit.list_problems()
    if not problems:
        st.caption(t("ui.sup.no_problems"))
    for p in problems:
        st.markdown(f"- **{p['time'].replace('T', ' ')}** · {t('ui.case')} {p['case_id']} · {p['where']}: {p['text']}"
                    + (f" _({t('ui.sup.removed')} {p['removed']})_" if p.get("removed") else ""))

    st.subheader(t("ui.sup.audit_all"))
    records = audit.list_records()
    if not records:
        st.caption(t("ui.sup.no_audit"))
    for r in records:
        with st.expander(t("ui.sup.audit_row", case_id=r["case_id"], model=r["model"], last=r["events"][-1]["event"])):
            st.markdown(audit.describe(r))


def review_one(record: dict):
    case_id = record["id"]
    with st.expander(t("ui.sup.case_row", case_id=case_id, kind=case_type_label(record["case_type"]),
                       sent=record["submitted"].replace("T", " ")), expanded=True):
        for h in record.get("history", []):
            st.caption(t("ui.sup.resent", when=h["resent"].replace("T", " "), reason=h["sent_back_reason"]))
        st.code(record["draft"], language=None, wrap_lines=True)
        audit_record = audit.read_record(case_id)
        with st.expander(t("ui.sup.audit_one")):
            st.markdown(audit.describe(audit_record) if audit_record else t("ui.sup.no_audit_one"))
        action = st.radio(t("ui.sup.decision"), ["Approve", "Edit then Approve", "Reject with a reason"],
                          index=None, horizontal=True, key=f"action-{case_id}", format_func=option_text("sup."))
        try:
            if action == "Approve":
                if st.button(t("ui.sup.approve_save"), type="primary", key=f"approve-{case_id}"):
                    store.approve(case_id)
                    st.session_state["supervisor_flash"] = t("ui.sup.approved", case_id=case_id)
                    st.rerun()
            elif action == "Edit then Approve":
                edited = st.text_area(t("ui.sup.edit"), value=record["draft"], height=500, key=f"edit-{case_id}")
                st.caption(t("ui.sup.no_personal"))
                if st.button(t("ui.sup.save_approve"), type="primary", key=f"edit-approve-{case_id}"):
                    store.approve(case_id, edited_text=edited)
                    st.session_state["supervisor_flash"] = t("ui.sup.edited_approved", case_id=case_id)
                    st.rerun()
            elif action == "Reject with a reason":
                reason = st.text_area(t("ui.sup.reason"), key=f"reason-{case_id}")
                if st.button(t("ui.sup.send_back"), key=f"reject-{case_id}"):
                    store.reject(case_id, reason)
                    st.session_state["supervisor_flash"] = t("ui.sup.sent_back", case_id=case_id)
                    st.rerun()
        except ValueError as err:
            st.error(str(err))


# ---------- navigation ----------

SCREENS = {
    "New case": new_case_screen,
    "My cases": my_cases_screen,
    "Learn": learn_screen,
    "Supervisor": supervisor_screen,
}

st.sidebar.title(t("ui.app_title"))
choice = st.sidebar.radio(t("ui.go_to"), list(SCREENS), format_func=option_text("screen."), key="screen")
st.sidebar.markdown("---")
st.sidebar.markdown(f"**{t('ui.sidebar.danger')}**  \n{t('ui.sidebar.helpline')}")
language_switch()
SCREENS[choice]()
