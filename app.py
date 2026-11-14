"""Legal aid agent: Streamlit web app.

Run with:  streamlit run app.py

All visible text comes from i18n/<language>.json through t("key"). Widget keys and the values
the code checks (for example "Yes", "Undertrial", "None") stay in English; only what is shown
is translated.
"""

import contextlib
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from datetime import date, timedelta

import streamlit as st
import streamlit.components.v1 as components

import audit
import casework
import consistency
import document
import drafts
import evaluation
import impact
import general
import guides
import home
import intake
import lang
import practice
import bhashini
import llm
import multilingual
import ledger
import readiness
import research
import sarvam
import section479
import signin_guard
import storage
import store
import timeline
import tracker
import ui

st.set_page_config(page_title=lang.t("app.name", st.session_state.get("ui_lang", lang.DEFAULT)),
                   page_icon=str(ui.FAVICON_FILE), layout="wide", initial_sidebar_state="collapsed")
# The first screen: Home for everyone. The tests start on "New case" (set in tests/conftest.py).
START_SCREEN = os.environ.get("RAAHI_START_SCREEN", "Home")

# Look and feel: .streamlit/config.toml (colours, fonts) plus a small stylesheet (assets/app.css).
st.markdown(ui.style(), unsafe_allow_html=True)


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
KEEP_ON_LANGUAGE_SWITCH = ("doc-st-", "close-reason-", "ev-method", "evs-accepted", "ho-how-", "ho-by-", "case_type", "screen", "f_lawyer", "f_draft_lang", "g_draft_lang", "f_offence_pick",
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
    st.radio(LANGUAGE_LABEL, list(lang.LANGUAGES), format_func=lambda c: "EN" if c == "en" else lang.LANGUAGES[c],
             horizontal=True, key="ui_lang", on_change=keep_choices, label_visibility="collapsed")
    if lang.is_machine_translated(code()):
        st.caption(":material/info: " + t("ui.machine_note"))


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
    "f_answer": "", "f_confirm": False, "f_lawyer": None, "f_checked": False, "f_offence_month": None,
    "f_calc_sig": None, "f_confirmed": set(),
}
FACT_TO_KEY = {
    "law": "f_law", "section": "f_section", "offence_date": "f_offence_date",
    "custody_began": "f_custody", "today": "f_today", "never_convicted": "f_never",
    "other_cases_pending": "f_other", "more_than_one_section": "f_many",
    "delay_days_by_accused": "f_delay", "answer": "f_answer", "lawyer": "f_lawyer",
    "offence_month": "f_offence_month",
}
FACT_LABEL_KEYS = ["custody_began", "offence_date", "offence_month", "today", "section", "law", "more_than_one_section",
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
    if not ai or not ai.get("model"):
        return None
    reading = ai["reading"]
    return {"model": ai["model"], "read_at": ai["read_at"], "extracted": dict(reading.values),
            "not_accepted": sorted({d.split(":")[0] for d in reading.dropped})}


def page_title(text: str, helplines: bool = True):
    """A page heading with the two tap-to-call helplines right under it (the Home page style). Sign-in
    pages show the helplines in the card instead."""
    with st.container(key="page-head", gap=None):  # its own space below the logo bar
        st.title(text)
        if helplines:
            st.markdown(ui.page_helplines(t("safety.bar112"), t("safety.bar15100")), unsafe_allow_html=True)


def practice_hint():
    """Only for a Practice Clinic (CLINIC_NAME contains "Practice"): where the practice passcodes are."""
    if "practice" in (storage.setting("CLINIC_NAME") or "").casefold():
        st.caption(t("signin.practice_hint"))


def signin_columns(who: str):
    """A sign-in page's wide card (laptop): the form on the left (returned), and on the right what the page
    is for and the helplines. On a phone the two stack, full width."""
    with st.container(key="signin-wide"):
        form, side = st.columns([3, 2], gap="large")
    side.markdown(ui.signin_side(t("signin.title"), [t(f"signin.{who}{i}") for i in (1, 2, 3)], t("signin.help"),
                                 t("safety.bar112"), t("safety.bar15100")), unsafe_allow_html=True)
    return form


def new_case_screen():
    open_by_code()
    page_title(t("screen.New case") if st.session_state.get("case_id") else t("ui.new_case.title"))
    with st.container(key="nc-top", horizontal=True, vertical_alignment="center"):
        with st.container(key="worker-bar", gap="small"):  # one card: who, Sign out, camp, Continue a case
            volunteer_line(card=True)
            continue_box("new")
        with st.container(key="nc-side"):  # laptop: today's camp and a tip beside the card
            st.markdown(new_case_side(), unsafe_allow_html=True)
    msg = st.session_state.pop("case-msg", None)
    if msg:
        st.error(msg[1])
    done_id = intake_done_here()
    if done_id:  # intake finished: a clean done card; the case itself folds away below it
        intake_done_card(done_id)
    with (st.expander(t("intake.show_case"), expanded=False) if done_id else contextlib.nullcontext()):
        case_flow()


def intake_done_here() -> str:
    """The case whose intake was finished in this session (after sending), or ""."""
    sent = st.session_state.get("sent")
    case_id = (sent or {}).get("id") or st.session_state.get("gen_sent") or ""
    if not case_id:
        return ""
    try:
        return case_id if (tracker.load(case_id) or {}).get("intake_finished") else ""
    except (tracker.TrackerError, storage.StorageError):
        return ""


def intake_done_card(case_id: str):
    record = tracker.load(case_id) or {}
    with st.container(border=True, key="done-card"):
        due = (record.get("next") or {}).get("due")  # one line: who has it, and by when
        st.success(t("intake.done_card_due", case_id=case_id, due=show_date(date.fromisoformat(due))) if due
                   else t("intake.done_card", case_id=case_id), icon=":material/task_alt:")
        with st.container(horizontal=True, gap="small"):
            next_action(t("intake.next_case"), key="done-next", icon=":material/note_add:", on_click=start_case)
            st.button(t("intake.open_tracker"), key="done-tracker", icon=":material/list_alt:",
                      on_click=go, args=("My cases",))


def case_flow():
    current_case_panel()

    with st.container(key="nc-kind"):
        st.markdown(ui.step_heading("category", t("ui.new_case.kind")), unsafe_allow_html=True)
    case_type = st.radio(t("ui.new_case.kind"), CASE_TYPES, horizontal=True, key="case_type",
                         format_func=option_text("case_type."), label_visibility="collapsed",
                         captions=[t("case_type.cap.any"), t("case_type.cap.479")], width="stretch")
    if case_type == ANY_CASE:
        general_screen()
    else:
        init_form()
        notes_box()
        if not conflicts_block(st.session_state.get("case_id")):  # contradictions first: no dates until resolved
            if not ask_missing_facts():  # while missing facts are asked one at a time, the form waits
                undertrial_form()
    sent = st.session_state.get("sent") if case_type != ANY_CASE else None
    case_id = sent["id"] if sent else st.session_state.get("gen_sent")
    if case_id and not intake_done_here():
        finish_intake_box(case_id)  # the end of the flow: after the draft was sent
    report_problem_box("new-case", "New case", case_id)


def finish_intake_box(case_id: str):
    """"Finish intake" once the draft is sent (and the next step, once it is finished)."""
    record = tracker.load(case_id) or {}
    if not record.get("intake_finished"):
        next_action(t("intake.finish"), key="intake-finish", icon=":material/task_alt:",
                    on_click=finish_intake, args=(case_id,))
    elif record.get("next"):
        n = record["next"]
        st.success(t("intake.done", step=next_step_words(n["step"], None),
                     due=show_date(date.fromisoformat(n["due"])) if n.get("due") else "-"), icon=":material/task_alt:")


# ----- voice: "Speak the story" -----

def mic_key(audio_key: str) -> str:
    """The recorder's own key. "Record again" gives the recorder a new key, so it starts empty."""
    n = st.session_state.get(f"{audio_key}-round", 0)
    return audio_key if not n else f"{audio_key}{n}"


def recording(audio_key: str):
    return st.session_state.get(mic_key(audio_key))


def record_again(audio_key: str):
    st.session_state.pop(mic_key(audio_key), None)
    st.session_state[f"{audio_key}-round"] = st.session_state.get(f"{audio_key}-round", 0) + 1
    for suffix in ("-msg", "-converted", "-pending"):
        st.session_state.pop(f"{audio_key}{suffix}", None)


def recording_digest(audio_key: str) -> str:
    recording = st.session_state.get(mic_key(audio_key))
    return hashlib.sha256(recording.getvalue()).hexdigest()[:16] if recording is not None else ""


def recording_stopped(audio_key: str):
    """Runs when a recording stops: nothing is sent yet; "Turn speech into text" does that."""
    st.session_state.pop(f"{audio_key}-msg", None)


def convert_recording(audio_key: str):
    """"Turn speech into text": the work runs on this run, just before the story box is drawn (so the
    progress can be shown: "part 2 of 4")."""
    if recording(audio_key) is not None:
        st.session_state[f"{audio_key}-pending"] = True


def run_pending_voice(audio_key: str, target_key: str):
    """Call before the story box is drawn. The recording goes to Sarvam AI (Gemini as the backup) only
    to become text; it is never saved. The text goes through the privacy filter, then into the box."""
    if not st.session_state.pop(f"{audio_key}-pending", False):
        return
    audio = recording(audio_key)
    if audio is None:
        return
    shown = st.empty()

    def progress(n: int, total: int):
        shown.info(t("ui.voice.backup_working") if total == 0 else
                   t("ui.voice.part", n=n, total=total) if total > 1 else t("ui.voice.working"),
                   icon=":material/graphic_eq:")
    progress(1, 1)
    try:
        language = st.session_state.get(NOTES_LANGUAGE_KEYS.get(target_key, "")) or code()
        transcript = multilingual.speech_to_text(audio.getvalue(),
                                                 getattr(audio, "type", None) or "audio/wav", language, progress)
    except (llm.AIUnavailable, bhashini.BhashiniUnavailable):
        shown.empty()
        st.session_state[f"{audio_key}-msg"] = ("error", f"{t('ui.voice.failed')} {t('ui.voice.type_instead')}")
        return
    shown.empty()
    st.session_state[f"{audio_key}-converted"] = recording_digest(audio_key)  # this recording is done
    if not transcript.text:
        st.session_state[f"{audio_key}-msg"] = ("error", t("ui.voice.nothing_heard"))
        return
    before = st.session_state.get(target_key, "").rstrip()
    st.session_state[target_key] = (before + "\n" if before else "") + transcript.text
    if target_key in NOTES_LANGUAGE_KEYS:
        detect_notes_language(target_key)
    msg = t("ui.voice.done")
    if transcript.backup:
        msg = t("ui.voice.backup_used") + " " + msg
    if transcript.removed:
        msg += " " + t("ui.voice.removed", what=", ".join(f"{n} × {k}" for k, n in transcript.removed.items()))
    st.session_state[f"{audio_key}-msg"] = ("ok", msg)


def voice_box(audio_key: str, target_key: str):
    """"Speak the story": one tap on the mic starts recording (with a timer), one tap stops it; then
    "Turn speech into text" puts the text in the story box. No dropdown to open first."""
    st.session_state.pop(f"{audio_key}-open", None)
    with st.container(key=f"{audio_key}-box"):
        if not (sarvam.configured() or llm.gemini_available()):  # Sarvam, or Gemini as the backup (never Groq)
            st.info(t("ui.voice.no_ai"))
            return
        st.audio_input(t("ui.voice.title"), key=mic_key(audio_key), on_change=recording_stopped, args=(audio_key,))
        # While recording, the label says so (Streamlit's recorder shows the timer and the stop button)
        st.markdown(f"<style>.st-key-{audio_key}-box [data-testid=\"stAudioInput\"]:has(button[aria-label=\"Stop recording\"])"
                    f" [data-testid=\"stWidgetLabel\"] p::after {{ content: \" \\2014  {css_text(t('ui.voice.recording'))}\"; "
                    f"color: var(--red); font-weight: 700; }}</style>", unsafe_allow_html=True)
        # Both buttons always under the recorder, side by side; a greyed-out one says why
        has_recording = recording(audio_key) is not None
        new = has_recording and st.session_state.get(f"{audio_key}-converted") != recording_digest(audio_key)
        with st.container(horizontal=True, gap="small", key=f"{audio_key}-actions"):
            st.button(t("ui.voice.again"), key=f"{audio_key}-again", icon=":material/restart_alt:",
                      disabled=not has_recording, on_click=record_again, args=(audio_key,))
            (next_action if new else lambda label, **kw: st.button(label, type="secondary", **kw))(
                t("ui.voice.convert"), key=f"{audio_key}-convert", icon=":material/text_fields:", disabled=not new,
                on_click=convert_recording, args=(audio_key,))
        if not has_recording:
            why_disabled(t("why.record_first"))
        elif not new:
            why_disabled(t("why.converted"))
        st.caption(t("ui.voice.warning") + " " + t("ui.voice.caption"))
        msg = st.session_state.pop(f"{audio_key}-msg", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


def css_text(text: str) -> str:
    """Text safe inside a CSS content: "..." string."""
    return "".join(c if c.isalnum() or c in " .,:;!?…-" else f"\\{ord(c):x} " for c in text)


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


NOTES_LANGUAGE_KEYS = {"g_notes": "g_notes_lang", "f_notes": "f_notes_lang"}


def notes_language_choice(key: str):
    """The language of the notes: the volunteer chooses it. The app may suggest one from the text
    ("Use हिंदी"), but never sets it by itself; the notes are read only once a language is chosen."""
    options = multilingual.note_languages()
    st.selectbox(t("ui.lang.notes_language"), list(options), format_func=options.get, key=key, index=None,
                 placeholder=t("ui.lang.choose"), on_change=lambda: st.session_state.update({f"{key}-chosen": True}))
    suggested = st.session_state.get(f"{key}-suggested")
    if suggested in options and suggested == st.session_state.get(key) and not st.session_state.get(f"{key}-chosen"):
        st.caption(t("ui.lang.detected", language=options[suggested]))  # pre-selected; change it if wrong
    elif suggested in options and suggested != st.session_state.get(key):
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key=f"{key}-suggest"):
            st.caption(t("ui.lang.suggested", language=options[suggested]))
            st.button(t("ui.lang.use", language=options[suggested]), key=f"{key}-use", type="tertiary",
                      on_click=lambda: st.session_state.update({key: suggested, f"{key}-chosen": True}))


def no_drafts_waiting_text() -> str:
    """Why no draft is waiting, with live counts: "No drafts sent for review yet. 3 cases are still at
    intake." (or how many were sent back or approved)."""
    statuses = [r["status"] for r in tracker.rows()]
    intake = sum(s in (tracker.INTAKE, tracker.INTAKE_DONE) for s in statuses)
    back = statuses.count(store.SENT_BACK)
    decided = sum(s in tracker.APPROVED_STATUSES + (tracker.CHANGED, tracker.CLOSED) for s in statuses)
    if not statuses:
        return t("none_waiting.no_cases")
    parts = [t("none_waiting.lead_never" if not (back or decided) else "none_waiting.lead")]
    if intake:
        parts.append(t("none_waiting.intake", n=intake))
    if back:
        parts.append(t("none_waiting.sent_back", n=back))
    if decided:
        parts.append(t("none_waiting.decided", n=decided))
    return " ".join(parts)


def sent_status_line(case_id: str) -> str:
    """"Sent on 12 November 2026 · Waiting for review" once a case's draft was sent (any later stage too)."""
    if not case_id:
        return ""
    try:
        status = tracker.status_of(case_id)
        record = audit.read_record(case_id)
    except (ValueError, tracker.TrackerError, storage.StorageError):
        return ""
    if status in (tracker.INTAKE, tracker.INTAKE_DONE) or not record:
        return ""
    sent_on = audit.summary_row(record)["sent_on"][:10]
    if not sent_on:
        return ""
    line = t("send.status", on=show_date(date.fromisoformat(sent_on)), status=status_text(status))
    if status == store.SENT_BACK:  # the volunteer sees why, on the case itself
        reason = sent_back_reason(case_id)
        if reason:
            line += " · " + t("ui.cases.reason", reason=reason)
    return line


def update_letter_and_drafts(facts_sig: str, letter_sig, points: int):
    """"Update the letter and drafts": the letter first (when one is wanted), then the drafts."""
    if letter_sig:
        st.session_state["g_letter_sig"] = letter_sig
        log_agent("letter drafted", f"from {points} ticked research points" if points
                  else "facts only (no research point ticked)")
    st.session_state["g_drafts_sig"] = facts_sig
    log_agent("drafts made", "case summary; free legal aid application if needed")


def next_action(label: str, key: str, form: bool = False, **kw):
    """The step's next action: its one filled button (the others are outlined). On phones it is pinned to
    the bottom of the screen as "Next: <action>". Never two on one screen: a second one is outlined."""
    press = st.form_submit_button if form else st.button
    if st.session_state.get("_next_shown"):
        return press(label, key=key, type="secondary", **kw)
    st.session_state["_next_shown"] = True
    with st.container(key="next-action", horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f'<p class="next-label">{html.escape(t("ui.next_bar"))}</p>', unsafe_allow_html=True)
        return press(label, key=key, type="primary", **kw)


def step_button(label: str, key: str, **kw):
    """A step 3 button: filled only when it is the next action (worked out once, in general_summary)."""
    if st.session_state.get("_next_key") == key:
        return next_action(label, key, **kw)
    return st.button(label, key=key, type="secondary", **kw)


def why_disabled(text: str, red: bool = False):
    """One line under a disabled button saying why it can't be pressed yet."""
    st.markdown(f'<p class="why-off{" red" if red else ""}">{html.escape(text)}</p>', unsafe_allow_html=True)


def detect_notes_language(text_key: str = "g_notes"):
    """Suggest the story's language (English, Hindi or Hinglish) from its text and pre-select it, unless
    the volunteer already chose one; the volunteer can change it."""
    key = NOTES_LANGUAGE_KEYS[text_key]
    found = multilingual.detect_language(st.session_state.get(text_key) or "")
    if found and found in multilingual.note_languages():
        st.session_state[f"{key}-suggested"] = found
        if not st.session_state.get(f"{key}-chosen"):
            st.session_state[key] = found


def ensure_notes_language(text_key: str):
    """At "Read": the language chosen, or else the suggested one, or else the screen's language."""
    key = NOTES_LANGUAGE_KEYS[text_key]
    if not st.session_state.get(key):
        detect_notes_language(text_key)
    if not st.session_state.get(key):
        st.session_state[key] = code() if code() in multilingual.note_languages() else "en"


def language_name(language: str) -> str:
    return multilingual.note_languages().get(language, language)


def prepare_notes(text_key: str, error_key: str):
    """Filter, and translate to English with Bhashini if needed. None (with an error shown) if it can't."""
    language = st.session_state.get(NOTES_LANGUAGE_KEYS[text_key]) or "en"
    try:
        return multilingual.prepare(st.session_state.get(text_key, ""), language)
    except bhashini.BhashiniUnavailable as err:
        st.session_state[error_key] = t("ui.lang.bhashini_down", language=language_name(language)) + f" ({err})"
        return None


def show_translation_note(translated_from, translation):
    if translated_from:
        st.info(t("ui.lang.translated_note", language=language_name(translated_from)))
        with st.expander(t("ui.lang.show_translation")):
            st.text(translation)


def read_general():
    """Runs when "Read the story" is clicked."""
    st.session_state.pop("gen_error", None)
    prepared = prepare_notes("g_notes", "gen_error")
    if prepared is None:
        return
    case_id = st.session_state.get("case_id")
    record = tracker.load(case_id) if case_id else None
    try:
        extra = {"known": tracker.known(record)} if record and record.get("facts") else {}  # continuing a case
        notes_reading = llm.read_general_notes(prepared.text, output_lang=code() if code() in ("en", "hi") else "en",
                                               **extra)
    except llm.AIUnavailable as err:
        # The AI gave up (after its retries): the question form opens without it, and the story stays
        # in its box, so nothing is lost.
        start_general_without_ai()
        st.session_state["gen_error"] = t("ui.ai_busy") if err.busy else str(err)
        st.session_state["gen_busy"] = err.busy
        return
    st.session_state.pop("gen_busy", None)
    reading = general.check_general_answer(notes_reading.answer, notes_reading.notes_sent,
                                           code() if code() in ("en", "hi") else "en")
    removed = dict(prepared.removed)
    for kind, n in notes_reading.removed.items():
        removed[kind] = removed.get(kind, 0) + n
    answers = []
    # Only a story already read in THIS session and then edited counts as a correction; a story from another
    # visit or volunteer (a continued case) still shows a contradiction to resolve
    reread = bool((st.session_state.get("gen") or {}).get("read_here")) and bool(st.session_state.get("case_id"))
    try:
        case_id = ensure_case(general.CASE_TYPE)
        # Read again after an edit in this session: a newer value (a corrected date) replaces the older one
        tracker.merge_facts(case_id, reading.facts, who(), "story read by AI, checked by code", replace=reread)
        if reread:  # edited and read again: the new reading replaces the earlier one (no old and new side by side)
            before = tracker.load(case_id) or {}
            tracker.replace_summary(case_id, reading.what_happened, reading.issues, reading.documents_held,
                                    general.answers_still_apply([tuple(a) for a in before.get("answers", [])], reading),
                                    who(), ai_model=notes_reading.model)
        else:
            tracker.add_summary(case_id, reading.what_happened, reading.issues, reading.documents_held, who(),
                                ai_model=notes_reading.model)
        record = tracker.load(case_id)
        # The case so far plus the new story; known facts (earlier values while a contradiction is open)
        reading.what_happened = list(record["summary"])
        reading.issues = [tuple(i) for i in record["issues"]]
        reading.documents_held = list(record["documents_held"])
        answers = [tuple(a) for a in record.get("answers", [])]
        asked = [q for q, _ in answers]
        reading.questions = [q for q in reading.questions  # never ask again what was already answered
                             if not any(q == a or general.same_question(q, a) for a in asked)]
        known_values = tracker.known_for_form(record)
    except (tracker.TrackerError, storage.StorageError) as err:
        tracker_error(err)
        known_values = {}
    fixes = (st.session_state.get("gen") or {}).get("fixes") if reread else None  # typed by hand: kept
    _start_general(reading, notes_reading.model, removed)
    if fixes:
        st.session_state["gen"]["fixes"] = fixes
    st.session_state["g_notes_read"] = st.session_state.get("g_notes", "")  # what was last read
    log_agent("story read", f"model {notes_reading.model}; removed before sending: "
              + (", ".join(f"{n} × {k}" for k, n in removed.items()) or "nothing")
              + f"; {len(reading.questions)} questions planned")
    st.session_state["gen"]["read_here"] = True  # read in this session (an edit and re-read is a correction)
    st.session_state["gen"]["facts"].update(known_values)
    st.session_state["gen"].update(translated_from=prepared.translated_from, translation=prepared.text,
                                   answers=answers)


def start_general_without_ai():
    text = st.session_state.get("g_manual", "")
    reading = general.GeneralReading(
        what_happened=[general.clean(x) for x in re.split(r"(?<=[.!?।])\s+", text) if x.strip()][:6],
        issues=[("other", t("ui.general.problem_described"))])
    st.session_state.pop("gen_error", None)
    try:
        case_id = ensure_case(general.CASE_TYPE)
        tracker.add_summary(case_id, reading.what_happened, [], [], who())
        record = tracker.load(case_id)
        reading.what_happened = list(record["summary"])
        known_values = tracker.known_for_form(record)
    except (tracker.TrackerError, storage.StorageError) as err:
        tracker_error(err)
        known_values = {}
    _start_general(reading, None, {})
    st.session_state["gen"]["facts"].update(known_values)


def clear_general():
    for key in ["gen", "gen_error", "gen_busy", "g_notes", "g_manual", "g_checked", "gen_sent"]:
        st.session_state.pop(key, None)


def open_section479():
    """Hand the same story to the undertrial reader, so the Section 479 form is filled in."""
    st.session_state["case_type"] = "Undertrial"
    st.session_state["f_notes"] = st.session_state.get("g_notes", "")
    st.session_state["f_notes_lang"] = st.session_state.get("g_notes_lang")  # the language already confirmed
    read_notes()


def general_question(gen):
    """The next question to ask: the AI's questions first (most important first), then only
    the facts the free legal aid check still needs."""
    if gen["done"]:
        return None
    questions = gen["reading"].questions
    plan = elig_plan(gen)
    if gen["q_index"] < len(questions):
        return ("ai", gen["q_index"], questions[gen["q_index"]])
    if legal_aid_still_open(gen) and "legal_aid" not in gen.get("elig_asked", []):
        if "legal_aid" not in plan:
            plan.insert(0, "legal_aid")  # needed after all (the count grows, and says so by its new total)
        return ("legal_aid", "legal_aid", t("elig.q.legal_aid"))
    missing = [m for m in general.check_eligibility(gen["facts"]).missing
               if m not in gen["skipped"] and m not in LEGAL_AID_ONE_SCREEN]
    if missing:
        if missing[0] not in plan:
            plan.append(missing[0])
        return ("eligibility", missing[0], t(f"elig.q.{missing[0]}"))
    if state_still_needed(gen):  # research and free legal aid both depend on the state: always asked
        if "state" not in plan:
            plan.append("state")
        return ("eligibility", "state", t("elig.q.state"))
    # Free legal aid is decided before every planned question was asked: say so; never move on silently
    if not_needed(gen) and not gen.get("elig_ack"):
        return ("not_needed", None, "")
    return None


def state_still_needed(gen) -> bool:
    """The story did not give the state, and it was not answered or skipped yet."""
    return not gen["facts"].get("state") and "state" not in gen["skipped"]


def elig_plan(gen) -> list:
    """The free legal aid questions planned when the questions start (and the state, if the story did not
    give it): fixed, so the count stays right."""
    if gen.get("elig_plan") is None:
        missing = [m for m in general.check_eligibility(gen["facts"]).missing if m not in gen["skipped"]]
        plan = (["legal_aid"] if any(m in LEGAL_AID_ONE_SCREEN for m in missing) else []) + \
               [m for m in missing if m not in LEGAL_AID_ONE_SCREEN and m != "state"]
        gen["elig_plan"] = plan + (["state"] if state_still_needed(gen) else [])
    return gen["elig_plan"]


# The free legal aid questions, on one screen ("which of these apply?"): it counts as one question
LEGAL_AID_GROUPS = ["in_custody", "woman", "under_18", "sc_st", "disability"]
LEGAL_AID_ONE_SCREEN = LEGAL_AID_GROUPS + ["annual_income"]


def legal_aid_still_open(gen) -> list:
    """The groups (and the income) the free legal aid check still needs, not yet answered or skipped."""
    return [m for m in general.check_eligibility(gen["facts"]).missing
            if m in LEGAL_AID_ONE_SCREEN and m not in gen["skipped"]]


def not_needed(gen) -> list:
    asked = set(gen.get("elig_asked", [])) | set(gen["skipped"])
    return [m for m in elig_plan(gen) if m not in asked and not (m == "state" and gen["facts"].get("state"))]


def question_position(gen, kind: str, ref) -> tuple:
    """(n, total) for "Question n of total": the AI's questions, then the planned free legal aid questions.
    The total is fixed when the questions start."""
    ai_total = len(gen["reading"].questions)
    plan = elig_plan(gen)
    total = ai_total + len(plan)
    done = set(gen.get("elig_asked", [])) | set(gen["skipped"])
    n = ref + 1 if kind == "ai" else ai_total + len([m for m in plan if m in done]) + 1
    return n, max(total, n)


def continue_after_not_needed():
    st.session_state["gen"]["elig_ack"] = True


def why_asked(gen, kind: str, ref, text: str) -> str:
    """Why a question is asked: fixed text for the app's own questions; for the AI's, the AI's reason
    (already checked by plain code to contain no names), or a plain line when it gave none."""
    if kind == "eligibility":
        return t(f"whyq.elig.{ref}")
    same = lambda key: text in (lang.t(key, "en"), lang.t(key, "hi"))  # noqa: E731
    if same("q.person"):
        return t("whyq.person")
    if same("q.outcome"):
        return t("whyq.outcome")
    if text.startswith((lang.t("q.year_start", "en"), lang.t("q.year_start", "hi"))):
        return t("whyq.year")
    return gen["reading"].question_reasons.get(text) or t("whyq.ai_default")


def why_asked_line(reason: str):
    st.markdown(f'<p class="why-asked"><b>{html.escape(t("whyq.label"))}</b> {html.escape(reason)}</p>',
                unsafe_allow_html=True)


def legal_aid_screen(gen, last: bool):
    """"Free legal aid: which of these apply to the person?": Yes / No / Don't know for each group the story
    doesn't already answer; the income box only while none is Yes. One screen, one question in the count."""
    open_items = legal_aid_still_open(gen)
    groups = [m for m in LEGAL_AID_GROUPS if m in open_items]
    with st.container(border=True, key="legal-aid-screen"):
        st.markdown(f"**{t('elig.q.legal_aid')}**")
        why_asked_line(t("whyq.legal_aid"))
        for m in groups:
            st.radio(t(f"elig.q.{m}"), ["Yes", "No", "Don't know"], index=None, key=f"la-{m}", horizontal=True,
                     format_func=option_text("opt."), help=t(f"whyq.elig.{m}"))
        any_yes = any(st.session_state.get(f"la-{m}") == "Yes" for m in groups)
        if "annual_income" in open_items and not any_yes:  # income matters only when no group applies
            st.markdown(f"**{t('elig.q.annual_income')}**")
            col1, col2 = st.columns(2)
            col1.number_input(t("ui.general.amount"), min_value=0, step=500, value=None, key="la-income")
            col2.radio(t("ui.general.per"), ["per month", "per year"], index=None, key="la-income-per",
                       horizontal=True, format_func=option_text("opt."))
        with st.container(horizontal=True, gap="small", key="la-actions"):
            next_action(t("ui.see_summary") if last else t("ui.next"), key="la-next", icon=":material/arrow_forward:",
                        on_click=answer_legal_aid, args=(groups, "annual_income" in open_items))
            st.button(t("ui.general.skip_rest"), key="gskip-all", type="tertiary", on_click=skip_general_questions)


def answer_legal_aid(groups: list, income_asked: bool):
    gen = st.session_state["gen"]
    get = st.session_state.get
    answered = {}
    for m in groups:
        choice = get(f"la-{m}")
        if choice in ("Yes", "No"):
            gen["facts"][m] = answered[m] = choice == "Yes"
        else:
            gen["skipped"].add(m)  # "Don't know" (or left blank): not guessed
    if income_asked and not any(answered.values()):
        amount, per = get("la-income"), get("la-income-per")
        if amount is not None and per:
            gen["facts"]["annual_income"] = answered["annual_income"] = int(amount) * (12 if per == "per month" else 1)
        else:
            gen["skipped"].add("annual_income")
    gen.setdefault("elig_asked", []).append("legal_aid")
    log_agent("question asked", f"{lang.t('elig.q.legal_aid', 'en')} ({len(answered)} answered)")
    if answered and st.session_state.get("case_id"):
        merge_into_case(st.session_state["case_id"], answered, "answer to a question")


def answer_general(kind: str, ref, skip: bool = False):
    gen = st.session_state["gen"]
    get = st.session_state.get
    if kind == "ai":
        question = gen["reading"].questions[ref]
        text = (get(f"gq-{ref}") or "").strip()
        gen["answers"] = [(q, a) for q, a in gen["answers"] if q != question]
        gen["unanswered"] = [q for q in gen["unanswered"] if q != question]
        if skip:
            gen["unanswered"].append(question)
            log_agent("question asked", f"{question} (don't know)")
        elif text:
            log_agent("question asked", f"{question} (answered)")
            gen["answers"].append((question, text))
            if st.session_state.get("case_id"):
                try:
                    tracker.add_answers(st.session_state["case_id"], [(question, text)], who())
                except (tracker.TrackerError, storage.StorageError) as err:
                    tracker_error(err)
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
    if skip or value is not None:
        log_agent("question asked", f"{lang.t(f'elig.q.{fact}', 'en')} ({'not sure' if skip else 'answered'})")
        gen["elig_done"] = gen.get("elig_done", 0) + 1
        gen.setdefault("elig_asked", []).append(fact)
    if skip:
        gen["skipped"].add(fact)
    elif value is not None:
        gen["facts"][fact] = value
        if st.session_state.get("case_id"):
            merge_into_case(st.session_state["case_id"], {fact: value}, "answer to a question")


def skip_general_questions():
    gen = st.session_state["gen"]
    gen["unanswered"] += gen["reading"].questions[gen["q_index"]:]
    gen["q_index"] = len(gen["reading"].questions)
    gen["done"] = True


URGENT_KEYS = {general.CALL_112: "safety.call112", general.CALL_1930: "safety.call1930"}


GENERAL_FLOW = ["flow.g.1", "flow.g.2", "flow.g.3", "flow.g.4"]


def general_step(gen) -> int:
    """1 Tell the story -> 2 Questions -> 3 Summary and checklist -> 4 Send for review."""
    if not gen:
        return 1
    if st.session_state.get("g_story_open"):
        return 1
    if general_question(gen):
        return 2
    return 4 if st.session_state.get("g_checked") else 3


FLOW_ICONS = ["edit_note", "quiz", "description", "send"]


def flow_title(n: int):
    """The step's header band: its number in a circle, its name and its state (Now / Done with a tick / Not yet), the
    one title per step (the phone progress line does not repeat it)."""
    current = st.session_state.get("_flow_step", n)
    state = "done" if n < current else "now" if n == current else "next"
    st.markdown(ui.step_band(n, t(GENERAL_FLOW[n - 1]), state, t(f"flow.state.{state}")), unsafe_allow_html=True)


def back_to_story():
    st.session_state["g_story_open"] = True


def close_story():
    st.session_state["g_story_open"] = False


def back_to_questions():
    """Reopen the questions with the answers already given filled in (nothing is lost)."""
    gen = st.session_state["gen"]
    answers = dict(gen["answers"])
    for i, question in enumerate(gen["reading"].questions):
        if question in answers:
            st.session_state[f"gq-{i}"] = answers[question]
    gen["unanswered"] = []
    gen["q_index"], gen["done"], gen["elig_ack"] = 0, False, False


def restore_held_story():
    """A story typed on Home goes back into the story box after the clinic sign-in, with its language.
    It is set again in the same run that draws the box: a value set several runs earlier (before the
    sign-in screen) does not reach a box drawn for the first time. Kept only in this browser session."""
    held = st.session_state.pop("held_story", None)
    if not held:
        return
    current = (st.session_state.get("g_notes") or "").strip()
    if not current or current == held["text"].strip():
        st.session_state["g_notes"] = held["text"]
    if held.get("lang"):
        st.session_state["g_notes_lang-suggested"] = held["lang"]  # pre-selected; the volunteer can change it
        st.session_state.setdefault("g_notes_lang", held["lang"])


def general_screen():
    restore_held_story()
    gen = st.session_state.get("gen")
    step = general_step(gen)
    st.session_state["_flow_step"] = step
    st.markdown(ui.stepper([t(k) for k in GENERAL_FLOW], step, t("ui.step_of")), unsafe_allow_html=True)
    if gen:  # urgent actions always at the top
        for action in general.urgent_actions(gen["facts"], gen["reading"].unconfirmed_yes):
            st.error(f"## {t(URGENT_KEYS[action])}", icon=":material/emergency:")
    blocked = conflicts_block(st.session_state.get("case_id")) if gen else False

    if gen is None or st.session_state.get("g_story_open"):
        flow_title(1)
    story_label = t("ui.general.story_box") if gen is None else ":material/check_circle: " + t("ui.general.story_done")
    with st.expander(story_label, expanded=gen is None or bool(st.session_state.get("g_story_open"))):
        with st.container(key="names-warning-long"):
            st.warning(t("ui.general.names_warning"))
        with st.container(key="names-warning-short"):  # phones: the same rule, short
            st.warning(t("ui.general.names_warning_short"))
        if llm.available():
            run_pending_voice("g_audio", "g_notes")  # a recording just stopped: its text goes into the box
            st.text_area(t("ui.general.story_label"), key="g_notes", height=220,
                         placeholder=t("ui.general.story_placeholder"), on_change=detect_notes_language)
            notes_language_choice("g_notes_lang")
            voice_box("g_audio", "g_notes")
            col1, col2 = st.columns(2)
            busy = bool(st.session_state.get("g_reading"))
            empty = not (st.session_state.get("g_notes") or "").strip()
            read_before = st.session_state.get("g_notes_read")
            changed = bool(gen) and read_before is not None and \
                " ".join((st.session_state.get("g_notes") or "").split()) != " ".join(read_before.split())
            if changed:  # the story box differs from what was last read
                st.warning(t("ui.general.story_changed"), icon=":material/edit_note:")
            with col1:
                (next_action if not gen or changed else lambda label, **kw: st.button(label, type="secondary", **kw))(
                    t("ui.general.read"), key="g-read", disabled=busy or empty,
                    on_click=lambda: (ensure_notes_language("g_notes"), st.session_state.update(g_reading=True)))
            if empty and not busy:
                why_disabled(t("why.story_first"))
            if gen:
                col2.button(t("ui.general.clear"), on_click=clear_general)
                if st.session_state.get("g_story_open"):
                    st.button(t("ui.next"), key="g-story-continue", on_click=close_story, icon=":material/arrow_forward:")
        else:
            st.info(t("ui.general.no_ai"))
        if st.session_state.get("g_reading"):  # step two: read, with the message on screen, then redraw
            with st.spinner(t("ui.reading_wait"), show_time=True):
                read_general()
            st.session_state["g_reading"] = False
            st.rerun()
        if not llm.available() or st.session_state.get("gen_error"):
            st.text_area(t("ui.general.manual_label"), key="g_manual", height=120)
            st.button(t("ui.general.start_without_ai"), on_click=start_general_without_ai)
    if st.session_state.get("gen_busy") and st.session_state.get("gen_error"):
        st.warning(f"**{st.session_state['gen_error']}** {t('ui.ai_busy_more')}", icon=":material/hourglass_top:")
    elif st.session_state.get("gen_error"):
        st.error(st.session_state["gen_error"] + " " + t("ui.general.type_instead"))
    if not gen:
        return

    if gen["removed"]:
        st.caption(t("ui.removed_before_sending") + ", ".join(f"{n} × {k}" for k, n in gen["removed"].items()))
    show_translation_note(gen.get("translated_from"), gen.get("translation", ""))
    if blocked:
        return  # "Cannot conclude yet" until a volunteer chooses which value is right

    question = general_question(gen)
    if question and question[0] == "not_needed":
        flow_title(2)
        left = not_needed(gen)
        eligibility = general.check_eligibility(gen["facts"])
        st.info(t("ui.q_not_needed", n=len(left), reason=eligibility_text(eligibility)), icon=":material/task_alt:")
        st.markdown("\n".join(f"- {t(f'elig.q.{m}')}" for m in left))
        next_action(t("ui.q_continue"), key="q-not-needed-go", icon=":material/arrow_forward:",
                    on_click=continue_after_not_needed)
        st.button(t("ui.back_story"), key="g-back-story", type="tertiary", icon=":material/arrow_back:",
                  on_click=back_to_story)
        return
    if question and question[0] == "legal_aid":
        flow_title(2)
        n, total = question_position(gen, "legal_aid", "legal_aid")
        st.markdown(f'<p class="q-count">{html.escape(t("ui.q_of", n=n, total=total))}</p>', unsafe_allow_html=True)
        legal_aid_screen(gen, last=n >= total)
        st.button(t("ui.back_story"), key="g-back-story", type="tertiary", icon=":material/arrow_back:",
                  on_click=back_to_story)
        return
    if question:
        kind, ref, text = question
        flow_title(2)
        n, total = question_position(gen, kind, ref)
        st.markdown(f'<p class="q-count">{html.escape(t("ui.q_of", n=n, total=total))}</p>', unsafe_allow_html=True)
        with st.form(key=f"gform-{kind}-{ref}", enter_to_submit=True, border=True):
            st.markdown(f"**{text}**")
            why_asked_line(why_asked(gen, kind, ref, text))
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
            with st.container(horizontal=True, gap="small", key="q-actions"):
                # the first button is the one Enter presses
                next_action(t("ui.see_summary") if n >= total else t("ui.next"), key=f"gnext-{kind}-{ref}", form=True,
                            icon=":material/arrow_forward:", on_click=answer_general, args=(kind, ref))
                st.form_submit_button(t("ui.dont_know"), key=f"gskip-{kind}-{ref}", on_click=answer_general,
                                      args=(kind, ref, True))
                st.form_submit_button(t("ui.general.skip_rest"), key="gskip-all", type="tertiary",
                                      on_click=skip_general_questions)
        st.button(t("ui.back_story"), key="g-back-story", type="tertiary", icon=":material/arrow_back:",
                  on_click=back_to_story)
        return

    general_summary(gen)


DRAFT_LANGUAGES = {"en": "English", "hi": lang.NATIVE_NAMES["hi"]}  # drafts for the DLSA or a court: only these


def draft_language_choice(key: str) -> str:
    st.session_state.setdefault(key, code() if code() in DRAFT_LANGUAGES else "en")
    return st.radio(t("ui.draft_language"), list(DRAFT_LANGUAGES), format_func=DRAFT_LANGUAGES.get,
                    horizontal=True, key=key)


def make_reading_copy(key: str, text: str):
    try:
        copy = multilingual.reading_copy(text, code())
    except bhashini.BhashiniUnavailable as err:
        st.session_state[f"rc-{key}"] = ("error", t("ui.reading.down") + f" ({err})")
        return
    st.session_state[f"rc-{key}"] = ("ok", copy.text, copy.kept_in_english)


def reading_copy_box(key: str, text: str):
    """In a machine-translated language: a reading copy of legal text, never saved or sent."""
    if not lang.is_machine_translated(code()):
        return
    with st.expander(t("ui.reading.title", language=lang.LANGUAGES.get(code(), code()))):
        st.caption(multilingual.READING_COPY_LABEL)
        st.button(t("ui.reading.make"), key=f"rc-go-{key}", on_click=make_reading_copy, args=(key, text))
        result = st.session_state.get(f"rc-{key}")
        if result and result[0] == "error":
            st.error(result[1])
        elif result:
            if result[2]:
                st.warning(t("ui.reading.kept", n=result[2]))
            st.code(result[1], language=None, wrap_lines=True)


def apply_fixes(gen, facts):
    """What the volunteer fixed on the spot in the checklist (step 3) goes into the case before the drafts."""
    fix = gen.setdefault("fixes", {})
    if fix.get("person"):
        facts.person = fix["person"]
    if fix.get("outcome"):
        facts.outcome = fix["outcome"]
    dates = fix.get("dates", {})
    facts.timeline = [(dates.get(w) or w, x) for w, x in facts.timeline]
    facts.coming_dates = [(dates.get(w) or w, x) for w, x in facts.coming_dates]
    # Documents, as marked in the checklist: "Has it", "Still to get" or "Can't get" (with a reason)
    status = fix.get("doc_status", {})
    held = [d for d in facts.documents_held + fix.get("documents", []) if status.get(d, {}).get("status", "has") == "has"]
    held += [d for d, s in status.items() if s.get("status") == "has"]
    facts.documents_held = list(dict.fromkeys(held))
    facts.documents_cannot = {d: s.get("reason", "") for d, s in status.items()
                              if s.get("status") == "cannot" and s.get("reason")}
    return facts


DOC_CHOICES = ["has", "to_get", "cannot"]


def doc_key(doc: str) -> str:
    return hashlib.sha256(doc.encode("utf-8")).hexdigest()[:10]


def save_doc_status(doc: str):
    """A document marked in the checklist: kept with the case's fixes (the one place documents are listed)."""
    k = doc_key(doc)
    choice = st.session_state.get(f"doc-st-{k}")
    reason = tracker.clean_text(st.session_state.get(f"doc-why-{k}") or "", 120) if choice == "cannot" else ""
    st.session_state["gen"].setdefault("fixes", {}).setdefault("doc_status", {})[doc] = {"status": choice,
                                                                                         "reason": reason}


def documents_rows(g, approved):
    """Each document for this case with "Has it" / "Still to get" / "Can't get" (with a reason)."""
    docs = casework.document_checklist(g, approved, code())
    held = {d.casefold() for d in g.documents_held}
    with st.container(key="doc-list"):
        if not docs:
            st.caption(t("cw.nothing_more"))
        for doc in docs:
            k = doc_key(doc)
            if f"doc-st-{k}" not in st.session_state:
                st.session_state[f"doc-st-{k}"] = ("has" if doc.casefold() in held else
                                                   "cannot" if doc in g.documents_cannot else "to_get")
            st.radio(doc, DOC_CHOICES, key=f"doc-st-{k}", horizontal=True, on_change=save_doc_status, args=(doc,),
                     format_func=option_text("docs."), help=casework.DOC_HELP.get(doc))  # the long wording: ⓘ
            if st.session_state.get(f"doc-st-{k}") == "cannot":
                st.session_state.setdefault(f"doc-why-{k}", g.documents_cannot.get(doc, ""))
                st.text_input(t("docs.why"), key=f"doc-why-{k}", max_chars=120, on_change=save_doc_status, args=(doc,))
                if not (st.session_state.get(f"doc-why-{k}") or "").strip():
                    st.caption(t("docs.why_needed"))


def research_status(case_id, record) -> str:
    """"approved", "waiting", "failed" or "not started" for this case's research."""
    briefs = research.for_case(case_id) if case_id else []
    if research.approved_points(case_id) if case_id else []:
        return "approved"
    if any(r["status"] == research.WAITING for r in briefs):
        return "waiting"
    if (record or {}).get("research_runs"):
        return "failed" if (record["research_runs"][-1].get("result") == "failed") else "approved"
    return "not started"


def auto_research(case_id: str, issue: str, state: str):
    """Research runs once per case, by itself, after the questions (not again on page reloads).
    Only the state and the issue in plain words are sent; never if a name from the story is in it."""
    notes = st.session_state.get("g_notes", "") or ""
    if research.names_in(issue, notes) or general.possible_names(issue, notes):
        tracker.note_research_run(case_id, who(), "failed")
        return
    try:
        record = research.run(case_id, state, issue, who())
        result = "waiting" if record["points"] else "failed"
    except research.ResearchFailed:
        result = "failed"
    except (tracker.TrackerError, storage.StorageError, ValueError):
        result = "failed"
    try:
        tracker.note_research_run(case_id, who(), result)
    except (tracker.TrackerError, storage.StorageError):
        pass


def research_again(case_id: str, issue: str, state: str):
    st.session_state["rs-again"] = (case_id, issue, state)


def general_summary(gen):
    reading = gen["reading"]
    eligibility = general.check_eligibility(gen["facts"])
    still_to_ask = gen["unanswered"] + [general.ELIGIBILITY_QUESTIONS[m] for m in eligibility.missing]
    facts = apply_fixes(gen, general.build_facts(reading, gen["answers"], still_to_ask, gen["facts"], date.today()))
    problems = consistency.general_problems(facts, gen.get("translation", ""))
    if problems:
        cannot_conclude(problems)
        return

    categories = [c for c, _ in reading.issues]
    if "arrest_or_custody" in categories:
        st.info(t("ui.general.custody_info"))
        st.button(t("ui.general.open_479"), on_click=open_section479, disabled=not llm.available())
        if not llm.available():
            why_disabled(t("why.no_ai"))
    if "online_or_financial_fraud" in categories:
        st.info(t("ui.general.cyber_info"))

    flow_title(3)
    if gen["reading"].questions or gen["answers"]:
        st.button(t("ui.back_questions"), key="g-back-questions", type="tertiary", icon=":material/arrow_back:",
                  on_click=back_to_questions)

    # Research: when our files don't cover a problem, only when the volunteer presses "Run research"
    case_id = st.session_state.get("case_id")
    state = gen["facts"].get("state")
    try:
        facts.research = research.items_for_summary(case_id, state, [n for _, n in facts.issues] or
                                                    ["the problem described"])
    except storage.StorageError:
        facts.research = []
    uncovered = general.uncovered_issues(facts)
    record = tracker.load(case_id) if case_id else None
    again = st.session_state.pop("rs-again", None) or st.session_state.pop("rs-run", None)
    research_now = None  # research runs last, in its own box, after the cards and drafts are on screen
    if again and uncovered and state and (llm.gemini_available() or llm.tavily_key()):
        case_id = case_id or ensure_case(general.CASE_TYPE)
        research_now = (case_id, again[1] if again[1] else uncovered[0], state)
    status = research_status(case_id, record) if (uncovered or facts.research) else "none"
    # research not run yet is not a failure: the next steps then say the problem is not in our files yet
    facts.research_state = {"not started": "none" if not uncovered else "not started"}.get(status, status)

    draft_lang = draft_language_choice("g_draft_lang")
    if draft_lang == "hi":
        st.caption(t("ui.hindi_label_note"))
    kind = casework.problem_type(facts)
    missing_years = casework.missing_years(facts)
    approved_now = research.approved_points(case_id) if case_id else []
    facts.documents_to_get = [d for d in casework.document_checklist(facts, approved_now, code())
                              if d not in facts.documents_held and d not in facts.documents_cannot]
    app_items = readiness.case_items(facts, eligibility, kind, missing_years, cannot_marks("g"),
                                     documents_done=casework.documents_done(facts, approved_now, code()))
    items = readiness.with_ticks(app_items, volunteer_ticks(app_items))  # the volunteer decides
    send_reason = tracker.clean_text(st.session_state.get("g_send_reason") or "", 200)
    approved = research.approved_points(case_id) if case_id else []
    issue = (uncovered[0] if uncovered else "; ".join(n for _, n in facts.issues)) or t("ui.general.problem_described")

    waiting_rs = research.waiting_for_case(case_id) if not approved else None
    facts.research_pending = len([p for p in (waiting_rs or {}).get("points", []) if p.get("kind") != "letter"])
    rs_ticks, rs_reasons = research_ticks(waiting_rs)
    letter_points = approved or research.points_for_letter(waiting_rs, rs_ticks)
    # Nothing is drafted by itself: "Make the drafts" (summary and DLSA application) and "Draft the letter"
    # (from the ticked points, or facts only). A change to what a draft is made from clears it until the
    # button is pressed again.
    facts_sig = json.dumps([facts.to_dict(), [(i.key, i.status, i.note) for i in items], draft_lang,
                            eligibility.status], default=str, sort_keys=True)
    letter_wanted = bool(uncovered or letter_points)
    research_done = status in ("waiting", "approved", "failed") or bool(approved)
    letter_sig = json.dumps([facts_sig, sorted(rs_ticks.items()), [p.get("id") or p.get("text") for p in approved]],
                            default=str, sort_keys=True)
    drafts_made = st.session_state.get("g_drafts_sig") == facts_sig
    letter_made = letter_wanted and st.session_state.get("g_letter_sig") == letter_sig
    documents = []
    if drafts_made:
        documents.append((t("cw.doc_summary"), readiness.add_gaps_to_draft(
            general.make_summary_draft(facts, gen["model"], draft_lang), items, draft_lang, send_reason)))
    if letter_made and letter_points:  # from the volunteer's ticked points (or the approved ones)
        documents.append((t("cw.doc_letter") if approved else t("cw.doc_letter_draft"),
                          casework.complaint_letter(facts, letter_points, issue, gen["model"], draft_lang)))
    elif letter_made:  # no point ticked (or research failed): a facts-only request letter
        documents.append((t("cw.doc_letter_facts"), casework.facts_only_letter(facts, issue, gen["model"], draft_lang)))
    if drafts_made and eligibility.status == "eligible":
        documents.append((t("cw.doc_dlsa"), casework.dlsa_application(facts, eligibility, issue, gen["model"],
                                                                       draft_lang)))
    documents = [(title, st.session_state.get(f"doc-edit-{i}", text)) for i, (title, text) in enumerate(documents)]
    letter_state = {"wanted": letter_wanted, "made": letter_made, "research_done": research_done,
                    "sig": letter_sig, "changed": bool(st.session_state.get("g_letter_sig")) and not letter_made,
                    "points": sum(1 for p in letter_points if p.get("kind") != "letter")}
    can_search = llm.gemini_available() or llm.tavily_key()
    sent_already = bool(st.session_state.get("gen_sent") or sent_status_line(case_id))
    drafts_changed = bool(st.session_state.get("g_drafts_sig")) and not drafts_made or \
        bool(st.session_state.get("g_letter_sig")) and letter_wanted and research_done and not letter_made
    st.session_state["_next_key"] = (
        None if sent_already else  # then "Finish intake" is the next action
        "update-drafts" if drafts_changed else
        "rs-run-go" if uncovered and status == "not started" and state and can_search and not research_now else
        "letter-go" if letter_wanted and research_done and not letter_made else
        "drafts-go" if not drafts_made else "send-g")

    col_cards, col_check = st.columns([3, 2], gap="medium")
    with col_cards:
        case_cards(facts, eligibility, approved, kind, draft_lang)
    with col_check, st.container(key="check-col", border=True):  # its own box; laptop: a line between the columns
        fix_checklist(app_items, facts, eligibility, kind, missing_years, approved, gen)
    research_slot = st.container(key="research-slot")
    with research_slot:
        research_panel(facts, uncovered, "loading" if research_now else status, case_id, state, waiting_rs,
                       letter_state)
    with st.container(border=True, key="drafts-box"):  # its own box, heading in the same style
        drafts_panel(documents, "loading" if research_now else status, uncovered, facts_sig, drafts_made)
    entries = ledger.general(facts, reading.facts, eligibility, ai_checked=bool(gen["model"]))
    ledger_box(entries)
    if case_id:
        try:
            agent_did_card(audit.read_record(case_id), "step3")
        except storage.StorageError:
            pass
    packet = casework.bundle(documents) if documents else ""
    if documents:
        reading_copy_box("summary", documents[0][1])
    names = general.possible_names(packet, st.session_state.get("g_notes", ""), facts.facts.get("state") or "")
    if names:
        st.warning(t("ui.general.possible_names", names=", ".join(names)))
    in_story = [n for n in general.names_in_story(st.session_state.get("g_notes", ""), facts.facts.get("state") or "")
                if n not in names]
    if in_story:  # a name in the story that did not reach the drafts: the volunteer still checks
        st.warning(t("ui.names_in_story", names=", ".join(in_story)), icon=":material/person_off:")

    flow_title(4)
    sent = st.session_state.get("gen_sent")
    status_line = sent_status_line(sent or st.session_state.get("case_id"))
    if sent or status_line:
        st.success((t("ui.sent", case_id=sent) + "  \n" if sent else "") + status_line,  # "Finish intake" follows
                   icon=":material/send:")
        return
    with st.container(border=True, key="send-card"):  # the send section, its reason boxes inside the card
        unticked = readiness.gaps(items)
        if unticked:  # sending with unticked items needs a short reason; the supervisor sees both
            st.warning(t("ready.vol_unticked", items="; ".join(i.label(code()) for i in unticked)), icon=":material/rule:")
            st.text_input(t("ready.send_reason"), key="g_send_reason", max_chars=200)
        left_out = [pid for pid, keep in rs_ticks.items() if not keep]
        no_reason = [pid for pid in left_out if not rs_reasons.get(pid)]
        if left_out and waiting_rs:  # a box to type in, always: per point (its own words), or one for all
            points = {p["id"]: p for p in waiting_rs["points"]}
            for pid in no_reason:
                st.markdown(f'<p class="left-out-point">{html.escape(t("rs.left_out_point", text=short(points[pid]["text"], 120)))}</p>',
                            unsafe_allow_html=True)
                left_out_reason_choice(waiting_rs, points[pid], "rsvs")
            if no_reason or st.session_state.get("g_rs_all_reason"):
                st.text_input(t("rs.left_out_all"), key="g_rs_all_reason", max_chars=200)
        checked = st.checkbox(t("ui.general.checked_no_names") + REQUIRED, key="g_checked")
        required_legend()
        label = f"{t('ui.send_to_supervisor')} \u2014 " + (
            t("rs.button_reasons_missing", n=len(no_reason)) if no_reason else
            t("ready.button_unticked", n=len(unticked)) if unticked else t("ready.button_ready"))
        not_made = not drafts_made or (letter_wanted and research_done and not letter_made)
        # Exactly why it can't be sent yet, one line each, in red under the button
        if drafts_changed:  # made once, then something changed: one line and one button that redoes both
            why_disabled(t("why.send.changed"), red=True)
            step_button(t("cw.update_drafts"), key="update-drafts", icon=":material/refresh:",
                        on_click=update_letter_and_drafts, args=(facts_sig, letter_sig if letter_wanted and research_done
                                                                 else None, letter_state.get("points", 0)))
        reasons = ([t("why.send.drafts")] if not drafts_made and not drafts_changed else []) + \
            ([t("why.send.letter")] if letter_wanted and research_done and not letter_made and not drafts_changed
             else []) + \
            ([t("why.send.research")] if research_now else []) + \
            ([t("why.send.left_out")] if no_reason else []) + \
            ([t("why.send.reason")] if unticked and not send_reason else []) + \
            ([t("why.send.checked")] if not checked else [])
        clicked = step_button(label, key="send-g", disabled=bool(reasons), icon=":material/send:")
        for why in reasons:
            why_disabled(why, red=True)
        if clicked:
            ai = None
            if gen["model"]:
                ai = {"model": gen["model"], "read_at": gen["read_at"], "extracted": dict(reading.facts),
                      "not_accepted": sorted(set(reading.dropped))}
            try:
                case_id = ensure_case(general.CASE_TYPE)
                case_id = store.submit(packet, facts, ai=ai, draft_lang=draft_lang,
                                       readiness=readiness_rows(items) + ([{"key": "send_reason", "status": "note",
                                                                            "note": send_reason}] if unticked else []),
                                       ledger=[e.as_dict() for e in entries], case_id=case_id, by=who())
                tracker.confirm_facts(case_id, gen["facts"], who())
                if waiting_rs:  # every point goes to the supervisor, with which ones the volunteer left out and why
                    research.volunteer_review(waiting_rs["id"], rs_ticks, rs_reasons, who())
            except (ValueError, storage.StorageError, research.ResearchFailed) as err:
                st.error(str(err))
                return
            st.session_state["gen_sent"] = case_id
            finish_agent_session(case_id, packet)
            st.rerun()
    if research_now:  # everything else is already on screen; the research box shows its own progress
        with research_slot:
            with st.spinner(t("rs.working"), show_time=True):
                auto_research(*research_now)
        st.rerun()


def case_cards(g, eligibility, approved, kind, code_, case_for=None):
    """At a glance, Facts, Timeline, Documents, Free legal aid, For the lawyer, Next steps (with dates).
    Labels in a narrow grey column; lists as bullets; dates, amounts and urgency in bold."""
    e = html.escape
    rich = document.inline_html  # escaped, with dates, amounts and urgent words in bold

    def kv(label, value_html):
        return f'<span class="k">{e(label)}</span>{value_html}'

    def bullets(items, ordered=False):
        tag = "ol" if ordered else "ul"
        return f'<{tag} class="bl">' + "".join(f"<li>{i}</li>" for i in items) + f"</{tag}>"

    today = date.fromisoformat(g.today)
    u = casework.urgency(g, today, code_)
    glance = [kv(t("cw.g_problem"), rich("; ".join(n for _, n in g.issues) or t("cw.not_stated"))),
              kv(t("cw.g_wants"), rich(casework.wants_text(g.outcome) or t("cw.not_stated"))),
              kv(t("cw.g_how_long"), rich(casework.duration_text(g, today, code_) or t("cw.not_known_yet"))),
              kv(t("cw.g_urgency"), f'<b class="{"urgent" if u.level != "normal" else ""}">{e(" ".join(u.reasons))}</b>'
                 if u.level != "normal" else rich(" ".join(u.reasons)))]
    st.markdown(ui.info_card(t("cw.glance"), glance, "glance" + (" urgent" if u.level != "normal" else ""), "bolt"),
                unsafe_allow_html=True)
    rows = [kv(t("cw.person"), rich(g.person or t("cw.person_not_stated")))]
    if g.facts.get("state"):
        rows.append(kv(t("rs.state"), rich(g.facts["state"])))
    if g.what_happened:
        rows.append(bullets([rich(x) for x in g.what_happened]))
    st.markdown(ui.info_card(t("cw.facts"), rows, icon_name="description"), unsafe_allow_html=True)
    if g.timeline or g.coming_dates:
        tl = [f'<b>{e(w)}</b> \u2014 {rich(x)}' for w, x in g.timeline + g.coming_dates]
        tl += [f'<span class="miss">{e(t("cw.year_missing"))}: {e(w)}</span>' for w, _ in casework.missing_years(g)]
        st.markdown(ui.info_card(t("cw.timeline"), [bullets(tl)], icon_name="calendar_month"), unsafe_allow_html=True)
    # (Documents are in the readiness checklist, one row each: the one place they are listed.)
    aid = [rich(eligibility_text(eligibility)),
           *[f'<span class="src">{document.linked_html(s)}</span>' for s in eligibility.sources[:1]]]
    st.markdown(ui.info_card(t("sum.legal_aid_short"), aid, icon_name="balance"), unsafe_allow_html=True)
    flags = casework.lawyer_flags(g, code_)
    if flags:
        st.markdown(ui.info_card(t("cw.for_lawyer"), [bullets([rich(f) for f in flags])], "lawyer", "gavel"),
                    unsafe_allow_html=True)
    case_id = st.session_state.get("case_id") if case_for is None else case_for
    try:
        approved_case = bool(case_id) and tracker.status_of(case_id) in tracker.APPROVED_STATUSES
    except (tracker.TrackerError, storage.StorageError):
        approved_case = False
    steps = casework.next_steps(g, eligibility, general._approved_points(g), g.research_state, today, code_,
                                case_approved=approved_case)
    srows = []
    for s in steps:  # plain text; only the date in bold ("... or call 15100 — by 20 November 2026")
        body = s.text.rstrip()
        text = html.escape(body)
        if s.due:
            text = f'{html.escape(body.rstrip(".।"))} — {t("cw.by_bold", date="<b>" + html.escape(show_date(s.due)) + "</b>")}'
        if s.done:
            text = f'<span class="step-done">{ui.icon("check_circle")}</span> {text}'
        srows.append(text + (f'<span class="src">{document.linked_html(s.source)}</span>' if s.source else ""))
    note = f'<p class="card-note">{html.escape(t("cw.dates_note"))}</p>' if any(s.due for s in steps) else ""
    st.markdown(ui.info_card(t("cw.next_steps"), [note + bullets(srows, ordered=True)], icon_name="checklist"),
                unsafe_allow_html=True)


def eligibility_text(eligibility) -> str:
    return general.eligibility_text(eligibility, code()) if code() != "en" else eligibility.reason


def choose_research_state():
    """The state chosen in the research box: saved like the checklist's State (the same saved value).
    Research then runs when the volunteer presses "Run research"."""
    state = st.session_state.get("rs-state")
    if state:
        save_fix("g", "state", state)


def save_fix(gen_key: str, field: str, value):
    gen = st.session_state["gen"]
    fixes = gen.setdefault("fixes", {})
    if field == "dates":
        fixes.setdefault("dates", {}).update(value)
    elif field == "documents":
        fixes["documents"] = list(value)
    elif field in ("person", "outcome"):
        fixes[field] = tracker.clean_text(value, 200)
    else:  # a fact (state, yes/no facts, the reference number yes/no)
        gen["facts"][field] = value
        case_id = st.session_state.get("case_id")
        if case_id:
            merge_into_case(case_id, {field: value}, "fixed in the checklist")


def volunteer_ticks(items) -> dict:
    """{item key: ticked}. The app pre-ticks what it found, until the volunteer ticks or unticks an item;
    from then on the volunteer's choice stays."""
    ticks = {}
    for item in items:
        key = f"tick-{item.key}"
        if not st.session_state.get(f"{key}-touched"):
            st.session_state[key] = item.status == readiness.PRESENT
        ticks[item.key] = bool(st.session_state.get(key))
    return ticks


def tick_why(item, g, eligibility) -> str:
    """Why the app pre-ticked an item (or what is missing)."""
    if item.key == "case_documents":  # done when nothing is "still to get"
        return t("ready.why.docs_count", has=len(g.documents_held), get=len(g.documents_to_get or []),
                 cannot=len(g.documents_cannot))
    if item.key == "case_questions" and item.status not in (readiness.PRESENT, readiness.CANNOT) and g.still_to_ask:
        return t("ready.why.case_questions_open", n=len(g.still_to_ask))  # "Don't know" answers: ask next visit
    if item.status != readiness.PRESENT:
        return t("ready.why.missing") if item.status != readiness.CANNOT else item.note
    if item.key == "case_legal_aid":
        return t("ready.why.case_legal_aid", reason=eligibility_text(eligibility))
    key = f"ready.why.{item.key}"
    return t(key) if key in lang.strings("en") else t("ready.why.answered")


def fix_checklist(items, g, eligibility, kind, missing_years, approved, gen):
    """A real checklist: a tick box per item, pre-ticked by the app with the reason; the volunteer can
    tick or untick anything. Items not done yet can be fixed right here."""
    st.markdown(f"**{t('ready.title')}**")
    required_legend()
    st.caption(t("ready.ticks_caption"))
    for item in items:
        key = f"tick-{item.key}"
        if item.key == "case_documents":  # the documents part: its own block, a line above and below
            st.markdown(f'<div class="doc-block-top">{html.escape(t("cw.documents"))}</div>', unsafe_allow_html=True)
        st.checkbox(item.label(code()) + REQUIRED, key=key,
                    on_change=lambda k=key: st.session_state.update({f"{k}-touched": True}))
        st.markdown(f'<p class="tick-why">{html.escape(tick_why(item, g, eligibility))}</p>', unsafe_allow_html=True)
        if item.key == "case_documents":  # the documents themselves, here and nowhere else
            documents_rows(g, approved)
            st.markdown('<div class="doc-block-end"></div>', unsafe_allow_html=True)
            continue
        done = item.status == readiness.PRESENT
        if done or item.status == readiness.CANNOT or st.session_state.get(key):
            continue
        how = readiness.FIXES.get(item.key)
        k = f"fix-{item.key}"
        with st.container(key=f"fixbox-{item.key}"):
            if how == "text":
                field = "person" if item.key == "case_person" else "outcome"
                st.text_input(item.label(code()), key=k, max_chars=200, label_visibility="collapsed",
                              placeholder=t(f"q.{field}") if field == "outcome" else t("q.person"))
                st.button(t("ready.fix_save"), key=f"{k}-go", on_click=lambda f=field, kk=k: save_fix(
                    "g", f, st.session_state.get(kk) or ""))
            elif how == "state":
                st.selectbox(item.label(code()), general.state_names(), index=None, key=k,
                             label_visibility="collapsed")
                st.button(t("ready.fix_save"), key=f"{k}-go", on_click=lambda kk=k: save_fix(
                    "g", "state", st.session_state.get(kk)) if st.session_state.get(kk) else None)
            elif how == "dates":
                for n, (when, what) in enumerate(missing_years):
                    st.text_input(t("ready.fix_full_date", when=when, what=what), key=f"{k}-{n}", max_chars=40,
                                  placeholder="15 March 2026")
                st.button(t("ready.fix_save"), key=f"{k}-go", on_click=lambda kk=k, mm=list(missing_years): save_fix(
                    "g", "dates", {w: (st.session_state.get(f"{kk}-{i}") or "").strip()
                                   for i, (w, _) in enumerate(mm) if (st.session_state.get(f"{kk}-{i}") or "").strip()}))
            elif how == "yesno":
                fact = {"case_reference": "has_reference_number", "case_danger": "danger_now",
                        "case_custody": "in_custody", "case_1930": "called_1930"}[item.key]
                st.radio(item.label(code()), [True, False], index=None, key=k, horizontal=True,
                         label_visibility="collapsed", format_func=lambda v: t("ed.yes") if v else t("ed.no"),
                         on_change=lambda f=fact, kk=k: save_fix("g", f, st.session_state.get(kk)))
            elif how == "documents":
                needed, _ = casework.documents_needed(g, approved, code())
                st.multiselect(t("ready.fix_docs"), needed, key=k, label_visibility="collapsed",
                               placeholder=t("ready.fix_docs"))
                st.button(t("ready.fix_save"), key=f"{k}-go", on_click=lambda kk=k: save_fix(
                    "g", "documents", st.session_state.get(kk) or []))
            elif how == "eligibility":
                for m in eligibility.missing:
                    if m in ("state", "annual_income"):
                        continue
                    st.radio(t(f"elig.q.{m}"), [True, False], index=None, key=f"{k}-{m}", horizontal=True,
                             format_func=lambda v: t("ed.yes") if v else t("ed.no"),
                             on_change=lambda f=m, kk=f"{k}-{m}": save_fix("g", f, st.session_state.get(kk)))
            elif how == "back":
                st.button(t("ready.fix_back"), key=f"{k}-go", type="tertiary", on_click=back_to_questions)
            if item.key == "case_documents":  # "Can't get this" stays for documents
                st.caption(t("ready.cannot_help"))
                if st.checkbox(t("ready.cannot_box"), key=f"cant-g-{item.key}"):
                    st.text_input(t("ready.reason"), max_chars=120, key=f"cantr-g-{item.key}")


LEFT_OUT_CHOICES = ["not_about", "looks_wrong", "repeats", "other"]


def left_out_reason_choice(record: dict, p: dict, prefix: str):
    """Why a research point was left out: a quick choice; "Other" opens a short text box."""
    rid, pid = record["id"], p["id"]
    if st.session_state.get(f"rsvr-{rid}-{pid}"):  # a reason already given (a point naming a replaced law)
        st.caption(t("rs.left_out_given", reason=st.session_state[f"rsvr-{rid}-{pid}"]))
        return
    st.radio(t("rs.left_out_reason"), LEFT_OUT_CHOICES, index=None, horizontal=True, key=f"{prefix}-{rid}-{pid}",
             format_func=lambda c: t(f"rs.why_left.{c}"))
    if st.session_state.get(f"{prefix}-{rid}-{pid}") == "other":
        st.text_input(t("rs.why_left.other_text"), key=f"{prefix}t-{rid}-{pid}", max_chars=200)


def left_out_reason(rid: str, pid: str) -> str:
    """The reason for leaving a point out, from whichever box the volunteer used (research card or Send box)."""
    get = st.session_state.get
    if (get(f"rsvr-{rid}-{pid}") or "").strip():
        return get(f"rsvr-{rid}-{pid}").strip()
    for prefix in ("rsvc", "rsvs"):
        choice = get(f"{prefix}-{rid}-{pid}")
        if choice == "other":
            text = (get(f"{prefix}t-{rid}-{pid}") or "").strip()
            if text:
                return text
        elif choice:
            return t(f"rs.why_left.{choice}")
    return ""


def research_ticks(record) -> tuple:
    """({point id: ticked}, {point id: reason}) from the volunteer's tick boxes (pre-ticked except points
    naming a replaced law)."""
    if not record:
        return {}, {}
    ticks, reasons = {}, {}
    for p in record["points"]:
        if p.get("kind") == "letter":
            continue
        key = f"rsv-{record['id']}-{p['id']}"
        st.session_state.setdefault(key, research.default_keep(p))
        if not research.default_keep(p):
            st.session_state.setdefault(f"rsvr-{record['id']}-{p['id']}", t("rs.left_replaced"))
        ticks[p["id"]] = bool(st.session_state[key])
        reasons[p["id"]] = left_out_reason(record["id"], p["id"])
    all_reason = (st.session_state.get("g_rs_all_reason") or "").strip()  # "Send anyway: one reason for all"
    if all_reason:
        for pid, keep in ticks.items():
            if not keep and not reasons.get(pid):
                reasons[pid] = all_reason
    return ticks, reasons


def research_points_for_volunteer(record: dict):
    """Each point with its source links, the label, the warnings, and a tick box: unticked points stay
    out of the letter (with a short reason). The volunteer cannot add or edit a legal point."""
    st.warning(t("rs.volunteer_label"), icon=":material/pending:")
    st.caption(t("rs.volunteer_caption"))
    for p in record["points"]:
        if p.get("kind") == "letter":
            continue
        key = f"rsv-{record['id']}-{p['id']}"
        with st.container(border=True, key=f"rsp-{record['id']}-{p['id']}"):
            st.checkbox(f"{research.KINDS[p['kind']]}: {p['text']}", key=key)
            st.markdown("  \n".join(f":material/link: [{html.escape(label)}]({url})" for label, url in research.source_labels(p["sources"])))
            for w in p.get("warnings", []):
                (st.error if w["kind"] == "replaced" else st.warning)(
                    warning_text(w), icon=":material/gavel:" if w["kind"] == "replaced" else ":material/rule:")
            if not st.session_state.get(key):  # left out: why, right under the point (a quick choice)
                left_out_reason_choice(record, p, "rsvc")


def research_panel(g, uncovered, status, case_id, state, waiting_rs=None, letter=None):
    letter = letter or {}
    if not uncovered and status in ("none", "not started") and not letter.get("wanted"):
        return
    with st.container(border=True, key="research-panel"):
        st.markdown(ui.step_heading("travel_explore", t("rs.title")), unsafe_allow_html=True)
        can_search = llm.gemini_available() or llm.tavily_key()
        msg = {"approved": "rs.status_approved", "failed": "rs.failed",
               "not started": "rs.need_state" if not state else ("rs.ready_to_run" if can_search
                                                                 else "rs.status_not_started")}.get(status)
        if status == "loading":
            st.caption(t("rs.loading_caption"))
            return
        if waiting_rs:
            research_points_for_volunteer(waiting_rs)
            ticked = any(st.session_state.get(f"rsv-{waiting_rs['id']}-{p['id']}") for p in waiting_rs["points"]
                         if p.get("kind") != "letter")
            if letter.get("made"):
                st.success(t("rs.letter_drafted" if ticked else "rs.letter_facts_only"), icon=":material/task_alt:")
            else:
                st.caption(t("rs.tick_then_draft"))
        elif msg:
            (st.error if status == "failed" else st.info)(t(msg), icon=":material/travel_explore:")
        if not state and status == "not started":  # choose it here: saved to the case (the same value as the checklist)
            st.selectbox(t("rs.choose_state"), general.state_names(), index=None, key="rs-state",
                         placeholder=t("rs.choose_state_placeholder"), on_change=choose_research_state)
        with st.container(horizontal=True, gap="small", key="research-actions"):
            if uncovered and status == "not started":
                step_button(t("rs.run"), key="rs-run-go", icon=":material/travel_explore:",
                          disabled=not (state and can_search),
                          on_click=lambda: st.session_state.update({"rs-run": (case_id, uncovered[0], state)}))
            elif uncovered and state and case_id:
                st.button(t("rs.again"), key="rs-again-go", icon=":material/refresh:", disabled=not can_search,
                          on_click=research_again, args=(case_id, uncovered[0], state))
            if letter.get("wanted"):  # the letter, from the ticked points (or facts only), when asked for
                step_button(t("cw.letter_go"), key="letter-go",
                            icon=":material/edit_document:", disabled=not letter.get("research_done"),
                            on_click=lambda s=letter.get("sig"), n=letter.get("points", 0): (
                                st.session_state.update(g_letter_sig=s),
                                log_agent("letter drafted", f"from {n} ticked research points" if n
                                          else "facts only (no research point ticked)")))
            if status != "approved":  # research failed or the problem isn't covered: two free helplines
                nyaya_setu_button()
        if uncovered and status == "not started" and not state:
            why_disabled(t("why.state_first"))
        elif uncovered and not can_search:
            why_disabled(t("why.no_search"))
        if letter.get("wanted") and not letter.get("research_done"):
            why_disabled(t("cw.letter_after_research"))
        elif letter.get("changed"):
            st.info(t("cw.letter_changed"), icon=":material/edit_note:")


NYAYA_SETU_URL = "https://wa.me/917217711814"  # opens WhatsApp only; the story is never pre-filled


def nyaya_setu_button():
    st.link_button(t("rs.nyaya_setu"), NYAYA_SETU_URL, icon=":material/chat:")


def drafts_panel(documents, status, uncovered, facts_sig="", drafts_made=True):
    """Each draft as a readable letter, with Edit and Download; the plain text to copy below it. The
    summary and the DLSA application are made only when "Make the drafts" is pressed."""
    st.markdown(ui.step_heading("description", t("cw.drafts")), unsafe_allow_html=True)  # like Research and Send
    st.caption(t("cw.drafts_caption"))
    if not drafts_made:
        if st.session_state.get("g_drafts_sig"):
            st.info(t("cw.drafts_changed"), icon=":material/edit_note:")
        step_button(t("cw.make_drafts"), key="drafts-go", icon=":material/description:",
                    on_click=lambda: (st.session_state.update(g_drafts_sig=facts_sig),
                                      log_agent("drafts made", "case summary; free legal aid application if needed")))
    if uncovered and status == "loading":  # only while research is still running
        st.info(t("cw.letter_waiting"), icon=":material/hourglass_top:")
    for i, (title, text) in enumerate(documents):
        with st.container(border=True, key=f"draft-{i}"):
            st.markdown(f'<div class="draft-head"><h4>{html.escape(title)}</h4></div>', unsafe_allow_html=True)
            if st.session_state.get(f"doc-editing-{i}"):
                st.text_area(t("cw.edit_label"), value=text, key=f"doc-area-{i}", height=420)
                with st.container(horizontal=True, gap="small"):
                    st.button(t("ed.save"), key=f"doc-save-{i}", type="primary", on_click=save_doc_edit, args=(i,))
                    st.button(t("ui.cancel"), key=f"doc-cancel-{i}",
                              on_click=lambda n=i: st.session_state.update({f"doc-editing-{n}": False}))
            else:
                document_view(text, f"doc-{i}", title, edit_key=f"doc-editing-{i}")


@st.cache_data(show_spinner=False, max_entries=60)
def docx_bytes(text: str, title: str) -> bytes:
    return document.to_docx(text, title)


@st.cache_data(show_spinner=False, max_entries=60)
def pdf_bytes(text: str, title: str) -> bytes:
    return document.to_pdf(text, title)


def file_name(title: str, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower() or "draft"
    return f"{base[:40]}-{date.today():%Y-%m-%d}.{ext}"


def copy_button(text: str, key: str):
    """"Copy text": the draft's text onto the clipboard (works inside the app's frame on phones too)."""
    label, done = html.escape(t("cw.copy")), html.escape(t("cw.copied"))
    components.html(
        f"""<style>html,body{{margin:0;padding:0;overflow:hidden}}</style>
        <button id="b" style="font:500 15px 'Noto Sans','Noto Sans Devanagari',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
        color:#13213B;background:#fff;border:1px solid #DCD5C6;border-radius:999px;padding:0 12px;cursor:pointer;
        height:40px;width:100%;white-space:nowrap">{label}</button><textarea id="t" style="position:absolute;left:-9999px">{html.escape(text)}</textarea>
        <script>
        const b=document.getElementById('b'), x=document.getElementById('t');
        b.onclick=async()=>{{try{{await navigator.clipboard.writeText(x.value);}}catch(e){{x.select();document.execCommand('copy');}}
          b.textContent='{done}'; setTimeout(()=>b.textContent='{label}',2000);}};
        </script>""", height=40)


def document_view(text: str, key: str, title: str, edit_key: str = ""):
    """A draft as a page preview, with Edit (when allowed), Copy text, Word and PDF."""
    st.session_state.setdefault("shown_drafts", []).append(text)  # this run's drafts (read by the tests)
    st.markdown(document.to_html(text), unsafe_allow_html=True)
    with st.container(horizontal=True, gap="small", vertical_alignment="center", key=f"{key}-actions"):
        if edit_key:
            st.button(t("cw.edit"), key=f"{key}-edit", icon=":material/edit:",
                      on_click=lambda: st.session_state.update({edit_key: True}))
        st.download_button(t("cw.word_short"), docx_bytes(text, title), file_name=file_name(title, "docx"),
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           key=f"{key}-docx", icon=":material/description:")
        st.download_button(t("cw.pdf"), pdf_bytes(text, title), file_name=file_name(title, "pdf"),
                           mime="application/pdf", key=f"{key}-pdf", icon=":material/picture_as_pdf:")
        with st.container(key=f"{key}-copy"):
            copy_button(text, key)


def save_doc_edit(i: int):
    text = (st.session_state.get(f"doc-area-{i}") or "").replace("\r\n", "\n")
    if not text.startswith(drafts.DRAFT_HEADER):
        text = drafts.DRAFT_HEADER + "\n\n" + text
    st.session_state[f"doc-edit-{i}"] = text
    st.session_state[f"doc-editing-{i}"] = False


# ----- "Research this issue": for problems our files don't cover -----

def run_research(issues: list):
    get = st.session_state.get
    issue = (get("rs-issue") or "").strip()
    state = get("rs-state")
    if not state:
        st.session_state["rs-msg"] = ("error", t("rs.need_state"))
        return
    notes = get("g_notes", "") or ""
    names = list(dict.fromkeys(general.possible_names(issue, notes) + research.names_in(issue, notes)))
    if names:
        st.session_state["rs-msg"] = ("error", t("rs.name_found", names=", ".join(names)))
        return
    try:
        case_id = ensure_case(general.CASE_TYPE)
        with st.spinner(t("rs.working")):
            record = research.run(case_id, state, issue, who())
    except research.ResearchFailed:
        st.session_state["rs-msg"] = ("error", t("rs.failed"))
        return
    except (tracker.TrackerError, storage.StorageError, ValueError) as err:
        st.session_state["rs-msg"] = ("error", f"{err} {t('rs.failed')}")
        return
    st.session_state["rs-msg"] = ("ok", t("rs.sent", kept=len(record["points"]), dropped=len(record["dropped"])))


def research_box(uncovered: list, state):
    """Shown when the summary says "not covered by our verified files"."""
    with st.container(border=True, key="research-box"):
        st.markdown(f"**{t('rs.title')}**")
        st.caption(t("rs.caption"))
        case_id = st.session_state.get("case_id")
        for r in (research.for_case(case_id) if case_id else []):
            if r["status"] == research.WAITING:
                st.info(t("rs.pending", issue=r["issue"], on=show_stamp(r["asked_at"][:10])), icon=":material/hourglass_top:")
        st.session_state.setdefault("rs-issue", uncovered[0])
        st.session_state.setdefault("rs-state", state if state in general.state_names() else None)
        c1, c2 = st.columns([2, 1])
        c1.text_input(t("rs.issue"), key="rs-issue", max_chars=300)
        c2.selectbox(t("rs.state"), general.state_names(), index=None, key="rs-state")
        st.button(t("rs.button"), key="rs-go", type="primary", icon=":material/travel_explore:",
                  on_click=run_research, args=(uncovered,), disabled=not llm.gemini_available())  # research needs Google Search (Gemini)
        if not llm.gemini_available():
            why_disabled(t("why.no_search"))
        msg = st.session_state.pop("rs-msg", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


# ----- the undertrial notes -----

def show_value(value) -> str:
    if isinstance(value, bool):
        return t("yes") if value else t("no")
    if isinstance(value, date):
        return show_date(value)
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value):  # a month: "May 2024"
        return show_date(date.fromisoformat(value + "-01")).split(" ", 1)[1]  # "1 May 2024" -> "May 2024"
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
    prepared = prepare_notes("f_notes", "ai_error")
    if prepared is None:
        return
    try:
        notes_reading = llm.read_undertrial_notes(prepared.text)
    except llm.AIUnavailable as err:
        st.session_state["ai_error"] = t("ui.ai_busy") if err.busy else str(err)  # the form below stays open
        return
    reading = intake.check_ai_answer(notes_reading.answer, notes_reading.notes_sent)
    removed = dict(prepared.removed)
    for kind, n in notes_reading.removed.items():
        removed[kind] = removed.get(kind, 0) + n
    for key, value in FORM_DEFAULTS.items():  # start from an empty form
        st.session_state[key] = value
    st.session_state["f_today"] = date.today()
    values = dict(reading.values)
    try:
        case_id = ensure_case("Undertrial")
        tracker.merge_facts(case_id, reading.values, who(), "notes read by AI, checked by code")
        record = tracker.load(case_id)
        tracker.add_summary(case_id, [], [], [], who(), ai_model=notes_reading.model)
        values.update(tracker.known_for_form(record))  # earlier values stay while a contradiction is open
    except (tracker.TrackerError, storage.StorageError) as err:
        tracker_error(err)
    st.session_state["ai"] = {"reading": reading, "removed": removed, "skipped": set(),
                              "values": values, "model": notes_reading.model,
                              "read_at": audit.now(), "translated_from": prepared.translated_from,
                              "translation": prepared.text}
    st.session_state.pop("draft", None)
    if not intake.missing_facts(values):
        apply_to_form(values)


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
        notes_language_choice("f_notes_lang")
        run_pending_voice("f_audio", "f_notes")
        voice_box("f_audio", "f_notes")
        st.text_area(t("ui.notes.label"), key="f_notes", height=220, placeholder=t("ui.notes.placeholder"),
                     on_change=lambda: detect_notes_language("f_notes"))
        col1, col2 = st.columns(2)
        busy = bool(st.session_state.get("f_reading"))
        empty = not (st.session_state.get("f_notes") or "").strip()
        with col1:
            (next_action if not ai else lambda label, **kw: st.button(label, type="secondary", **kw))(
                t("ui.notes.read"), key="f-read", disabled=busy or empty,
                on_click=lambda: (ensure_notes_language("f_notes"), st.session_state.update(f_reading=True)))
        if empty and not busy:
            why_disabled(t("why.notes_first"))
        if ai:
            col2.button(t("ui.notes.clear"), on_click=clear_notes)
        if busy:
            with st.spinner(t("ui.reading_wait"), show_time=True):
                read_notes()
            st.session_state["f_reading"] = False
            st.rerun()
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
        if st.session_state.get("case_id"):
            merge_into_case(st.session_state["case_id"],
                            {f: ai["values"][f] for f in (fact, "law", "more_than_one_section") if f in ai["values"]},
                            "answer to a question")
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
    show_translation_note(ai.get("translated_from"), ai.get("translation", ""))
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
        why_asked_line(t(f"whyq.f.{fact}"))
        if fact in ai["reading"].notes_say:
            st.caption(t("ui.missing.notes_say", quote=ai["reading"].notes_say[fact]))
        question_widget(fact)
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            next_action(t("ui.next"), key=f"next-{fact}", on_click=answer_fact, args=(fact,))
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

def remember_confirmation(fact: str):
    confirmed = set(st.session_state.get("f_confirmed") or set())
    (confirmed.add if st.session_state.get(f"confirm-{fact}") else confirmed.discard)(fact)
    st.session_state["f_confirmed"] = confirmed


def calculate_card(used: dict, offence, signature: str):
    """The fields the dates will be worked out from, an Edit button and "Calculate the dates"."""
    def yes_no(v):
        return t("yes") if v else t("no")
    when = show_value(used["offence_date"]) if used["offence_date"] else (
        show_value(used["offence_month"]) if used["offence_month"] else t("calc.not_given"))
    rows = [(t("fact.section"), f"{used['law']} {used['section']} ({offence.offence})"),
            (t("fact.offence_date"), when),
            (t("fact.custody_began"), show_value(used["custody_began"]) if used["custody_began"] else t("calc.not_given")),
            (t("fact.today"), show_value(used["today"]) if used["today"] else t("calc.not_given")),
            (t("fact.never_convicted"), yes_no(used["never_convicted"])),
            (t("fact.other_cases_pending"), yes_no(used["other_cases_pending"])),
            (t("fact.more_than_one_section"), yes_no(used["more_than_one_section"])),
            (t("fact.delay_days_by_accused"), str(used["delay_days_by_accused"]))]
    if offence.ask_to_decide:
        rows.append((t("fact.answer"), used["answer"] or t("calc.not_given")))
    with st.container(border=True, key="f-calc-card"):
        st.markdown(f"**{t('calc.title')}**")
        st.markdown("\n".join(f"- {html.escape(k)}: **{html.escape(str(v))}**" for k, v in rows))
        with st.container(horizontal=True, gap="small", key="f-calc-actions"):
            (next_action if st.session_state.get("f_calc_sig") != signature else
             lambda label, **kw: st.button(label, type="secondary", **kw))(
                t("calc.go"), key="f-calc", icon=":material/calculate:",
                on_click=lambda: st.session_state.update(f_calc_sig=signature))
            st.button(t("calc.edit"), key="f-edit", icon=":material/edit:",
                      on_click=lambda: st.session_state.update(f_checked=False, f_calc_sig=None))


def checked_by_volunteer() -> bool:
    """After an AI reading, the volunteer must check every field before the calculator runs."""
    ai = st.session_state.get("ai")
    if not ai:
        return True
    reading = ai["reading"]
    show_translation_note(ai.get("translated_from"), ai.get("translation", ""))
    with st.container(border=True):
        st.markdown(f"**{t('ui.check.title')}**")
        if ai["removed"]:  # also when no question was asked
            st.caption(t("ui.removed_before_sending") + ", ".join(f"{n} × {k}" for k, n in ai["removed"].items()))
        in_story = general.names_in_story(st.session_state.get("f_notes", ""))
        if in_story:
            st.warning(t("ui.names_in_story", names=", ".join(in_story)), icon=":material/person_off:")
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


def cannot_conclude(problems) -> None:
    """Show why the agent will not conclude yet, and what is needed."""
    for p in problems:
        params = dict(p.params)
        if "fact" in params:
            params["fact"] = fact_label(params["fact"])
        st.error(t("abstain.title", reason=t("abstain." + p.reason, **params)))
        st.caption(t("abstain.needed." + p.needed))
        if p.confirm_fact:  # kept in "f_confirmed": the box itself is not drawn once the problem is settled
            st.checkbox(t("abstain.confirm_box", fact=fact_label(p.confirm_fact), form=p.params["form"]),
                        key=f"confirm-{p.confirm_fact}", on_change=remember_confirmation, args=(p.confirm_fact,))


def undertrial_form():
    st.header(t("ui.form.header"))
    st.info(t("ui.form.aid_note"))

    col1, col2 = st.columns([1, 2])
    law = col1.selectbox(t("fact.law"), ["IPC", "BNS"], key="f_law")
    section = col2.text_input(t("ui.form.section"), placeholder=t("ui.form.section_example"), key="f_section")

    offence_date = st.date_input(t("fact.offence_date"), format="DD/MM/YYYY", key="f_offence_date",
                                 min_value=date(1990, 1, 1), max_value=date.today(),
                                 help=t("ui.form.offence_date_help"))
    month = st.session_state.get("f_offence_month") if offence_date is None else None
    if month:  # the notes give only the month and year
        st.caption(t("ui.form.month_decides", month=show_value(month)))  # the month and year decide the law
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

    # Safe abstention: contradictions or missing key facts stop here.
    ai_state = st.session_state.get("ai")
    form = {"custody_began": custody_began, "offence_date": offence_date, "today": today, "law": law,
            "section": section.strip(), "never_convicted": never_convicted, "other_cases_pending": other_cases,
            "delay_days_by_accused": int(delay_days), "answer": answer.strip(),
            "lawyer": st.session_state.get("f_lawyer")}
    confirmed = set(st.session_state.get("f_confirmed") or set())  # the volunteer's "the form is right"
    problems = consistency.undertrial_problems(
        form, dict(ai_state["reading"].values) if ai_state else {},
        ai_state.get("translation", "") if ai_state else "", confirmed)
    if problems:
        cannot_conclude(problems)
        return

    # The facts that will be used, with Edit; the dates appear only after "Calculate the dates", and any
    # change to a field clears them until it is pressed again.
    used = {**{k: v for k, v in form.items() if k != "lawyer"},  # the lawyer is asked later, for the draft
            "offence": offence.offence, "offence_month": month, "more_than_one_section": many_sections,
            "question_answered": question_answered}
    signature = json.dumps(used, default=str, sort_keys=True)
    calculate_card(used, offence, signature)
    if st.session_state.get("f_calc_sig") != signature:
        if st.session_state.get("f_calc_sig"):
            st.info(t("calc.changed"), icon=":material/edit_note:")
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
            offence_month=month,
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
                offence_month=month,
                answer=answer.strip(),
            ),
            result,
        )


# ----- readiness checklist -----

def case_details_box(prefix: str) -> dict:
    """Optional case numbers and places (never personal details), filled into the draft's blanks."""
    with st.expander(t("ready.details_title"), expanded=True):
        col1, col2 = st.columns(2)
        values = {}
        for i, field in enumerate(readiness.DETAIL_FIELDS):
            values[field] = (col1 if i % 2 == 0 else col2).text_input(t(f"ready.detail.{field}"), max_chars=60,
                                                                    key=f"{prefix}-detail-{field}")
    return values


def cannot_marks(prefix: str) -> dict:
    """{item key: reason} for fields the volunteer marked "cannot obtain" (with a reason)."""
    marks = {}
    for key, value in st.session_state.items():
        if isinstance(key, str) and key.startswith(f"cant-{prefix}-") and value:
            item = key[len(f"cant-{prefix}-"):]
            reason = (st.session_state.get(f"cantr-{prefix}-{item}") or "").strip()
            if reason:
                marks[item] = reason
    return marks


REQUIRED = " :red[\\*]"  # the small red asterisk after every label needed before sending (one rule, every case type)


def required_legend():
    """"* needed before sending", in red: at the top of every checklist and in the Send box."""
    st.markdown(f'<p class="req-legend">* {html.escape(t("ready.needed_legend"))}</p>', unsafe_allow_html=True)


def checklist_box(items, prefix: str):
    st.markdown(f"**{t('ready.title')}**")
    required_legend()
    icons = {readiness.PRESENT: ":material/check_circle:", readiness.MISSING: ":material/cancel:",
             readiness.UNCERTAIN: ":material/help:", readiness.CANNOT: ":material/block:"}
    for item in items:
        st.markdown(f"{icons[item.status]} {item.label(code())}{REQUIRED}: {t('ready.status.' + item.status)}"
                    + (f" \u2014 {item.note}" if item.note else ""))
        if item.status in (readiness.MISSING, readiness.UNCERTAIN, readiness.CANNOT):
            if st.checkbox(t("ready.cannot_box"), key=f"cant-{prefix}-{item.key}"):
                st.text_input(t("ready.reason"), max_chars=120, key=f"cantr-{prefix}-{item.key}")


LEDGER_ICONS = {ledger.TOLD: ":material/record_voice_over:", ledger.AI_CHECKED: ":material/fact_check:",
                ledger.CALCULATED: ":material/calculate:", ledger.VERIFIED: ":material/menu_book:",
                ledger.UNRESOLVED: ":material/help:", ledger.PRECAUTION: ":material/warning:",
                ledger.RESEARCH: ":material/travel_explore:", ledger.RESEARCH_APPROVED: ":material/verified:"}


def ledger_box(entries, expanded=False):
    """Where each fact comes from, for the volunteer and the supervisor."""
    open_points = ledger.unresolved([e if isinstance(e, ledger.Entry) else ledger.Entry(**e) for e in entries])
    for p in open_points:  # each open legal point as a question for the lawyer
        issue = p.value if p.fact == "ledger.issue" else f"{t(p.fact)} ({p.value})"
        st.warning(t("ledger.question_for_lawyer", issue=issue), icon=":material/gavel:")
    with st.expander(f"{t('ui.details')}: {t('ledger.title')}", expanded=expanded):
        for e in entries:
            e = e if isinstance(e, ledger.Entry) else ledger.Entry(**e)
            st.markdown(f"{LEDGER_ICONS[e.source]} **{t(e.fact)}:** {e.value} \u2014 _{t('ledger.source.' + e.source)}_")
            if e.source_line:
                st.caption(e.source_line)


def readiness_rows(items) -> list:
    return [{"key": i.key, "status": i.status, "note": i.note} for i in items]


def send_label(items) -> str:
    return f"{t('ui.send_to_supervisor')} \u2014 {readiness.button_label(items, code())}"


def draft_section(known: dict, result: section479.Result):
    st.divider()
    st.subheader(t("ui.draft.title"))
    if known["offence_date"] is None and not section479.month_law_date(known.get("offence_month")):
        st.info(t("ui.draft.need_offence_date"))
        return
    lawyer = st.radio(t("ui.draft.lawyer_question"), drafts.LAWYER_OPTIONS, key="f_lawyer",
                      format_func=option_text("lawyer."))
    if lawyer is None:
        st.info(t("ui.draft.answer_first"))
        return
    draft_lang = draft_language_choice("f_draft_lang")
    details = case_details_box("f")
    facts = drafts.UndertrialFacts(lawyer=lawyer, **known)
    ai_info = ai_info_for_audit()
    ai_model = ai_info["model"] if ai_info else None
    signature = json.dumps({**facts.to_dict(), "ai_model": ai_model, "lang": draft_lang}, sort_keys=True)

    if st.button(t("ui.draft.make"), type="primary"):
        st.session_state["draft"] = {"sig": signature}
    draft = st.session_state.get("draft")
    if not draft or draft["sig"] != signature:
        return  # no draft yet, or the facts changed since it was made

    # The draft is rebuilt on every change, so case details and "cannot obtain" marks show at once.
    skipped = st.session_state.get("ai", {}).get("skipped", set()) if st.session_state.get("ai") else set()
    marks = cannot_marks("f")
    items = readiness.section479_items(facts, result, details, skipped, marks)
    if lawyer == "None":
        items += readiness.dlsa_items(details, marks)
    text = drafts.make_undertrial_draft(facts, result, ai_model=ai_model, code=draft_lang)
    text = readiness.add_gaps_to_draft(readiness.fill_details(text, details, draft_lang), items, draft_lang)
    draft["text"] = text

    if lawyer == "None":
        st.caption(t("ui.draft.dlsa_added"))
    if draft_lang == "hi":
        st.caption(t("ui.hindi_label_note"))
    col_draft, col_check = st.columns([3, 2])
    with col_draft:
        document_view(text, "f-draft", t("ui.draft.title"))
    with col_check:
        checklist_box(items, "f")
    ai_state = st.session_state.get("ai")
    entries = ledger.undertrial(facts, result, dict(ai_state["values"]) if ai_state else {},
                                ai_checked=bool(ai_state) and bool(st.session_state.get("f_checked")))
    if ai_state:  # only what the AI itself read counts as "read from notes by AI"
        read = ai_state["reading"].values
        for e in entries:
            fact = e.fact.split(".", 1)[1]
            if e.source == ledger.AI_CHECKED and fact not in read:
                e.source = ledger.TOLD
    ledger_box(entries)
    reading_copy_box("draft", text)
    st.caption(t("ui.draft.blanks"))

    sent = st.session_state.get("sent")
    if sent and sent["sig"] == signature:
        st.success(t("ui.sent", case_id=sent["id"]))
        line = sent_status_line(sent["id"])
        if line:
            st.markdown(f'<p class="sent-status">{html.escape(line)}</p>', unsafe_allow_html=True)
    elif st.button(send_label(items), key="send-f"):
        try:
            case_id = ensure_case("Undertrial")
            case_id = store.submit(text, facts, ai=ai_info, draft_lang=draft_lang, readiness=readiness_rows(items),
                                   ledger=[e.as_dict() for e in entries], case_id=case_id, by=who())
            tracker.confirm_facts(case_id, {
                "law": facts.law_typed, "section": facts.section_typed, "custody_began": facts.custody_began,
                "offence_date": facts.offence_date, "never_convicted": facts.never_convicted,
                "other_cases_pending": facts.other_cases_pending, "more_than_one_section": facts.more_than_one_section,
                "delay_days_by_accused": facts.delay_days_by_accused, "lawyer": facts.lawyer,
                "answer": facts.answer or None}, who())
        except (ValueError, storage.StorageError) as err:
            st.error(str(err))
            return
        st.session_state["sent"] = {"sig": signature, "id": case_id}
        finish_agent_session(case_id, text)
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
STEP_ICONS = {timeline.TO_DO: ":material/check_box_outline_blank:", timeline.DONE: ":material/check_box:",
              timeline.NOT_NEEDED: ":material/remove:"}


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
    today = date.today()
    items = timeline.due_this_week(today)
    # cases with a due date but no timeline yet (sent or intake finished): due within 7 days, inclusive
    with_steps = {c for c, _, _ in items}
    pending = [r for r in tracker.rows(today=today) if r["due"] and not r["step"] and r["id"] not in with_steps
               and r["status"] != tracker.CLOSED and date.fromisoformat(r["due"]) <= today + timedelta(days=7)]
    if not items and not pending:
        st.caption(t("ui.cases.nothing_due"))
    for r in sorted(pending, key=lambda r: r["due"]):
        line = f"**{show_date(date.fromisoformat(r['due']))}** · {t('ui.case')} {r['id']} · {next_step_text(r)}"
        if r["overdue"]:
            st.error(t("tl.overdue") + " · " + line)
        else:
            st.info(line)
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


def save_handoff(case_id: str, kind: str):
    get = st.session_state.get
    try:
        if kind == "submitted":
            timeline.record_submission(case_id, get(f"ho-who-{case_id}", ""), get(f"ho-date-{case_id}") or date.today(),
                                       get(f"ho-how-{case_id}") or "")
        else:
            timeline.record_acknowledgement(case_id, get(f"ho-by-{case_id}") or "", get(f"ho-adate-{case_id}") or date.today(),
                                            get(f"ho-ref-{case_id}", ""), get(f"ho-rec-{case_id}", ""))
    except ValueError as err:
        st.session_state[f"ho-msg-{case_id}"] = ("error", str(err))
        return
    st.session_state[f"ho-msg-{case_id}"] = ("ok", t("handoff.saved"))


def handoff_box(case_id: str):
    """Ready -> Approved -> Submitted by an authorised worker -> Acknowledged. A draft is not a filing."""
    record = timeline.load(case_id)
    if record is None:
        return
    current = timeline.stage(record)
    order = ["ready", timeline.APPROVED_STAGE, timeline.SUBMITTED_STAGE, timeline.ACKNOWLEDGED_STAGE]
    reached = order.index(current)
    st.markdown(" \u2192 ".join((":material/check_circle: " if i <= reached else ":material/radio_button_unchecked: ")
                                 + t(f"handoff.stage.{s}")
                                  for i, s in enumerate(order)))
    st.caption(t("handoff.not_filing"))
    handoff = record.get("handoff", {})
    if handoff.get("submitted"):
        sub = handoff["submitted"]
        st.markdown(t("handoff.submitted_line", on=show_date(date.fromisoformat(sub["on"])), by=sub["by"],
                      how=t("handoff.how." + sub["how"])))
    if handoff.get("acknowledged"):
        ack = handoff["acknowledged"]
        st.markdown(t("handoff.ack_line", on=show_date(date.fromisoformat(ack["on"])), by=t("handoff.by." + ack["by"]),
                      ref=f" ({ack['reference']})" if ack.get("reference") else ""))
    if current == timeline.APPROVED_STAGE:
        with st.expander(t("handoff.record_submission")):
            st.text_input(t("handoff.who"), max_chars=60, key=f"ho-who-{case_id}")
            st.date_input(t("handoff.date"), value=date.today(), format="DD/MM/YYYY", key=f"ho-date-{case_id}")
            st.radio(t("handoff.how"), timeline.HANDOFF_METHODS, index=None, horizontal=True, key=f"ho-how-{case_id}",
                     format_func=option_text("handoff.how."))
            st.button(t("handoff.record_submission"), key=f"ho-save-{case_id}", on_click=save_handoff,
                      args=(case_id, "submitted"))
    elif current == timeline.SUBMITTED_STAGE:
        with st.expander(t("handoff.record_ack")):
            st.radio(t("handoff.by_whom"), timeline.ACKNOWLEDGED_BY, index=None, horizontal=True, key=f"ho-by-{case_id}",
                     format_func=option_text("handoff.by."))
            st.date_input(t("handoff.date"), value=date.today(), format="DD/MM/YYYY", key=f"ho-adate-{case_id}")
            st.text_input(t("handoff.reference"), max_chars=60, key=f"ho-ref-{case_id}")
            st.text_input(t("handoff.recorded_by"), max_chars=60, key=f"ho-rec-{case_id}")
            st.button(t("handoff.record_ack"), key=f"ho-ack-{case_id}", on_click=save_handoff,
                      args=(case_id, "acknowledged"))
    msg = st.session_state.pop(f"ho-msg-{case_id}", None)
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])


def continue_from_tracker(case_id: str):
    record = tracker.load(case_id)
    if record:
        open_existing(record)
        go("New case")


def tracker_filters(rows: list) -> list:
    """Filters: status, camp, volunteer, and hide "intake not finished"."""
    c1, c2, c3 = st.columns(3)
    status = c1.selectbox(t("tr.filter.status"), [None] + tracker.STATUSES, key="tr-status",
                          format_func=lambda s: t("tr.all") if s is None else status_text(s))
    camps = sorted({r["camp"] for r in rows if r["camp"]})
    camp = c2.selectbox(t("tr.filter.camp"), [None] + camps, key="tr-camp",
                        format_func=lambda c: t("tr.all") if c is None else c)
    names = sorted({n for r in rows for n in r["volunteers"]})
    volunteer = c3.selectbox(t("tr.filter.volunteer"), [None] + names, key="tr-volunteer",
                             format_func=lambda n: t("tr.all") if n is None else n)
    hide = st.checkbox(t("tr.hide_intake"), key="tr-hide-intake")
    return tracker.filter_rows(rows, status=status, camp=camp, volunteer=volunteer, hide_intake=hide)


def sent_back_reason(case_id: str) -> str:
    """The supervisor's reason for sending a case's drafts back ("" if none)."""
    try:
        return store.get_pending(case_id).get("reason") or ""
    except (ValueError, storage.StorageError):
        return ""


def tracker_table(rows: list):
    table = [{"case": r["id"], "code": r["code"], "status": status_chip(r["status"]),
              "next": " · ".join(x for x in (next_step_text(r), t("ui.cases.reason", reason=sent_back_reason(r["id"]))
                                             if r["status"] == store.SENT_BACK and sent_back_reason(r["id"]) else "") if x),
              "due": (show_date(date.fromisoformat(r["due"])) if r["due"] else ""),
              "overdue": r["overdue"], "camp": r["camp"], "who": r["last_by"]} for r in rows]
    headers = {k: t(f"tr.col.{k}") for k in ("case", "code", "status", "next", "due", "camp", "who")}
    st.markdown(ui.tracker_table(table, headers, t("tr.overdue")), unsafe_allow_html=True)


def my_cases_screen():
    """The clinic's case tracker: every case with status, next step and due date (overdue in red),
    filters, and each case's file, visit log, slip and progress."""
    page_title(t("ui.cases.title"))
    volunteer_line()
    msg = st.session_state.pop("case-msg", None)
    if msg:
        st.error(msg[1])
    try:
        rows = tracker.rows()
    except storage.StorageError as err:
        st.error(str(err))
        return
    if not rows:
        st.info(t("ui.cases.none"))
        return
    shown = tracker_filters(rows)
    st.caption(t("tr.count", shown=len(shown), total=len(rows)))
    tracker_table(shown)
    due_this_week_box()
    approved_text = {c["id"]: c.get("text", "") for c in store.list_cases() if c["status"] == store.APPROVED}
    for row in shown:
        tracker_card(row, approved_text)


def toggle_open(case_id: str):
    toggle(f"open-{case_id}")
    if not st.session_state.get(f"open-{case_id}"):
        st.session_state[f"editing-{case_id}"] = False


def tracker_card(row: dict, approved_text: dict):
    """One case on the tracker: number, type, code and status; the next step; Open case / Edit case."""
    e = html.escape
    case_id = row["id"]
    record = tracker.load(case_id)
    is_open = bool(st.session_state.get(f"open-{case_id}"))
    with st.container(key=f"case-card-{case_id}"):
        head = f"<b>{e(t('ui.case_title', case_id=case_id))}</b>"
        if row["case_type"]:
            head += f" · {e(case_type_label(row['case_type']))}"
        if row["code"]:
            head += f" · {e(t('slip.code'))} {e(row['code'])}"
        sub = e(next_step_text(row)) if row["next_step"] else ""
        if row["status"] == store.SENT_BACK:  # the supervisor's reason, on the card itself
            reason = sent_back_reason(case_id)
            if reason:
                sub = (sub + " · " if sub else "") + f'<span class="sent-back">{e(t("ui.cases.reason", reason=reason))}</span>'
        if row["due"]:
            due = e(show_date(date.fromisoformat(row["due"])))
            sub += (f' · <span class="overdue">{e(t("tr.overdue"))} · {due}</span>' if row["overdue"]
                    else f" · {e(t('cf.due', due=due))}")
        st.markdown(f'<div class="case-head">{head} {status_chip(row["status"])}</div>'
                    + (f'<div class="case-sub">{sub}</div>' if sub else ""), unsafe_allow_html=True)
        closed = row["status"] == tracker.CLOSED  # read-only until the supervisor reopens it
        if closed and record and record.get("closed"):
            st.caption(closed_line(record["closed"]))
        with st.container(horizontal=True, gap="small"):
            st.button(t("tr.close") if is_open else t("tr.open"), key=f"tr-open-{case_id}",
                      icon=":material/close:" if is_open else ":material/folder_open:",
                      type="secondary" if is_open else "primary", on_click=toggle_open, args=(case_id,))
            if record and not closed:
                st.button(t("tr.edit"), key=f"tr-edit-{case_id}", icon=":material/edit:", on_click=start_edit,
                          args=(case_id,))
            if row["status"] == tracker.INTAKE:
                st.button(t("tr.continue"), key=f"tr-cont-{case_id}", icon=":material/arrow_forward:",
                          on_click=continue_from_tracker, args=(case_id,))
        if row["status"] == store.SENT_BACK:
            st.warning(t("ui.cases.reason", reason=store.get_pending(case_id).get("reason", "")))
            fix_and_resend(case_id)
        if record and closed and is_open:
            case_file_view(case_id, record, editable=False)
        elif record and (is_open or st.session_state.get(f"editing-{case_id}")):
            case_file_or_edit(case_id, record, edit_button=False)  # "Edit case" is already on the card
            slip_box(record)
            visit_form(case_id)
            camp_form(case_id, record)
        if is_open and case_id in approved_text and not closed:
            handoff_box(case_id)
            timeline_box(case_id)
        if is_open and case_id in approved_text:
            with st.expander(t("ui.cases.case_file")):
                st.markdown(approved_text[case_id])
            approved = store.approved_draft(case_id)
            if approved:
                with st.expander(t("ui.cases.approved_draft")):
                    for n, part in enumerate(casework.split_bundle(approved)):
                        document_view(part.strip(), f"appr-{case_id}-{n}", t("ui.cases.approved_draft"))
        if is_open:
            report_problem_box(f"case-{case_id}", "My cases", case_id)


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
            store.resend(case_id, fixed, by=who())
        except ValueError as err:
            st.error(str(err))
            return
        st.session_state[flag] = False
        st.rerun()
    if col2.button(t("ui.cancel"), key=f"cancel-{case_id}"):
        st.session_state[flag] = False
        st.rerun()


# ---------- evaluation (practice only) ----------

def finish_agent_session(case_id: str, draft: str):
    """If an evaluation session "with the agent" is running, sending to the supervisor stops its clock."""
    sid = st.session_state.get("eval_session")
    if not sid:
        return
    try:
        session = evaluation.load(sid)
        if session["method"] == evaluation.WITH_AGENT and not session["finished"]:
            evaluation.finish(sid, {"agent_case": case_id, "draft": draft})
            st.session_state.pop("eval_session", None)
    except ValueError:
        st.session_state.pop("eval_session", None)


def start_eval():
    try:
        session = evaluation.start(st.session_state.get("ev-case"), st.session_state.get("ev-method") or "",
                                   st.session_state.get("ev-volunteer", ""))
    except ValueError as err:
        st.session_state["ev-msg"] = ("error", str(err))
        return
    st.session_state["eval_session"] = session["session_id"]


def finish_eval():
    sid = st.session_state.get("eval_session")
    session = evaluation.load(sid)
    c = evaluation.case(session["case"])
    if session["method"] == evaluation.BY_HAND:
        answers = {name: st.session_state.get(f"ev-field-{i}", "") for i, name in enumerate(c["required"])}
        answers["notes"] = st.session_state.get("ev-notes", "")
    else:
        answers = {"agent_case": "", "draft": "(finished without sending to the supervisor)"}
    done = evaluation.finish(sid, answers)
    st.session_state.pop("eval_session", None)
    st.session_state["ev-msg"] = ("ok", t("eval.finished", minutes=evaluation.minutes(done)))


def cancel_eval():
    st.session_state.pop("eval_session", None)


def evaluation_box():
    """The trainers' timing tool (practice cases by hand or with the agent), on the Supervisor page."""
    with st.expander(t("eval.trainers"), icon=":material/timer:",
                     expanded=bool(st.session_state.get("eval_session") or st.session_state.get("ev-msg"))):
        evaluation_panel()


def evaluation_panel():
    msg = st.session_state.pop("ev-msg", None)
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])
    sid = st.session_state.get("eval_session")
    if not sid:
        cases = {c["id"]: f"{c['id']} \u00b7 {c['title']} ({c['category']})" for c in evaluation.cases()}
        st.selectbox(t("eval.case"), list(cases), format_func=cases.get, key="ev-case")
        st.radio(t("eval.method"), evaluation.METHODS, index=None, key="ev-method", format_func=option_text("eval.method."))
        st.text_input(t("eval.volunteer"), max_chars=40, key="ev-volunteer")
        st.button(t("eval.start"), type="primary", on_click=start_eval)
        return
    session = evaluation.load(sid)
    c = evaluation.case(session["case"])
    st.info(t("eval.active", sid=sid, case=c["id"], method=t("eval.method." + session["method"]),
              started=show_stamp(session["started"])))
    st.markdown(f"**{t('eval.story')}**")
    st.code(c["story"], language=None, wrap_lines=True)
    if session["method"] == evaluation.BY_HAND:
        st.caption(t("eval.by_hand_help"))
        for i, name in enumerate(c["required"]):
            st.text_input(name, key=f"ev-field-{i}")
        st.text_area(t("eval.notes"), key="ev-notes", height=150)
    else:
        st.info(t("eval.agent_help", workflow={"Any case": t(f"case_type.{ANY_CASE}"),
                                               "Section 479 aid": t("case_type.Undertrial")}.get(c["workflow"], c["workflow"])))
    col1, col2 = st.columns(2)
    col1.button(t("eval.finish"), type="primary", on_click=finish_eval)
    col2.button(t("eval.cancel"), on_click=cancel_eval)


def save_eval_score():
    get = st.session_state.get
    try:
        evaluation.score(get("evs-session"), get("evs-reviewer", ""), int(get("evs-correct") or 0),
                         int(get("evs-errors") or 0), int(get("evs-corrections") or 0), get("evs-accepted") == "Yes")
    except ValueError as err:
        st.session_state["evs-msg"] = ("error", str(err))
        return
    st.session_state["evs-msg"] = ("ok", t("eval.saved"))


def evaluation_scoring_box():
    """Reviewer scoring form on the Supervisor screen (practice data only) and the raw-count export."""
    finished = evaluation.sessions(finished_only=True)
    if not finished:  # nothing to score yet: the section is not shown (no empty box)
        return
    with st.expander(t("eval.score_title")):
        labels = {s["session_id"]: f"{s['session_id']} \u00b7 {s['case']} \u00b7 {s['method']} \u00b7 {s['volunteer']}"
                  for s in finished}
        sid = st.selectbox(t("eval.session"), list(labels), format_func=labels.get, key="evs-session")
        session = evaluation.load(sid)
        c = evaluation.case(session["case"])
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**{t('eval.answer_key')}**")
            st.markdown("\n".join(f"- {k}: {v}" for k, v in c["required"].items()))
            st.markdown(f"_{t('eval.must_not')}_ " + "; ".join(c["must_not"]))
        with col2:
            st.markdown(f"**{t('eval.submission')}**")
            st.code("\n".join(f"{k}: {v}" for k, v in session["submission"].items()), language=None, wrap_lines=True)
        st.text_input(t("eval.reviewer"), max_chars=40, key="evs-reviewer")
        st.number_input(t("eval.fields_correct", total=len(c["required"])), min_value=0,
                        max_value=len(c["required"]), step=1, key="evs-correct")
        st.number_input(t("eval.material_errors"), min_value=0, step=1, key="evs-errors")
        st.number_input(t("eval.major_corrections"), min_value=0, step=1, key="evs-corrections")
        st.radio(t("eval.accepted"), ["Yes", "No"], index=None, horizontal=True, key="evs-accepted",
                 format_func=option_text("opt."))
        st.button(t("eval.save_score"), on_click=save_eval_score, key="evs-save")
        msg = st.session_state.pop("evs-msg", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])
        st.download_button(t("eval.export"), evaluation.export_csv(), file_name="evaluation_raw_counts.csv",
                           mime="text/csv", key="evs-export")


def save_impact():
    get = st.session_state.get
    try:
        impact.log(get("imp-case") or "", get("imp-partner", ""), bool(get("imp-permission")),
                   get("imp-ref", ""), get("imp-feedback", ""))
    except ValueError as err:
        st.session_state["imp-msg"] = ("error", str(err))
        return
    st.session_state["imp-msg"] = ("ok", t("imp.saved"))


def impact_box():
    with st.expander(t("imp.title")):
        practice = impact.practice_case_ids()
        cases = [c["id"] for c in store.list_cases() if c["status"] == store.APPROVED and c["id"] not in practice]
        st.selectbox(t("imp.case"), cases, index=None, key="imp-case")
        st.text_input(t("imp.partner"), max_chars=100, key="imp-partner")
        st.checkbox(t("imp.permission"), key="imp-permission")
        st.text_input(t("imp.permission_ref"), max_chars=100, key="imp-ref")
        st.text_area(t("imp.feedback"), max_chars=300, key="imp-feedback", height=80)
        st.button(t("imp.save"), key="imp-save", on_click=save_impact)
        msg = st.session_state.pop("imp-msg", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])
        st.caption(t("imp.count", n=len(impact.entries())))
        st.download_button(t("imp.export"), impact.export_csv(), file_name="impact_log.csv", mime="text/csv",
                           key="imp-export")


def open_guide(key: str):
    """Open one guide on the Learn page (from its card there, or its "Open Learn" button on Home)."""
    st.session_state.update(screen="Learn", learn_guide=key, menu_open=False)


def learn_screen():
    """The guides from learner/ as cards (a guide that is not fully accurate yet says "Coming soon"), and
    the open guide below them: what you will be able to do, the key idea, a worked example, practice
    cases and a five-question check with instant feedback. Every source is a clickable link."""
    page_title(t("ui.learn.title"))
    wanted = st.query_params.get("guide", "")
    if "learn_guide" not in st.session_state and guides.by_key(wanted):
        st.session_state["learn_guide"] = wanted  # reopened from the page address
    current = st.session_state.get("learn_guide")
    st.caption(t("learn.intro"))
    st.info(t("learn.not_reviewed"), icon=":material/info:")
    guide = guides.by_key(current or "")
    if guide and guides.content(guide.key).ready:  # the open guide first, so it is seen at once
        if st.query_params.get("guide") != guide.key:
            st.query_params["guide"] = guide.key
        st.button(t("learn.back"), key="learn-back-top", icon=":material/arrow_back:", type="tertiary",
                  on_click=close_guide)
        show_guide(guide)
        st.button(t("learn.back"), key="learn-back-end", icon=":material/arrow_back:", type="tertiary",
                  on_click=close_guide)
        return
    with st.container(key="learnlinks"):
        cols = st.columns(len(guides.GUIDES) + 1, gap="medium")
        for col, g in zip(cols, guides.GUIDES):
            with col.container(key=f"learn-card-{g.key}"):
                ready = guides.content(g.key).ready
                st.markdown(ui.guide_card(g.icon, t(f"home.learn{g.number}"), t(f"home.learn{g.number}_p"),
                                          "" if ready else t("learn.coming_soon")), unsafe_allow_html=True)
                if ready:
                    st.button(t("learn.open"), key=f"guide-{g.key}", icon=":material/menu_book:",
                              type="primary" if g.key == current else "secondary", on_click=open_guide, args=(g.key,))
        with cols[-1].container(key="learn-card-more"):
            st.markdown(ui.guide_card("more_horiz", t("learn.more_title"),
                                      t("learn.more_topics", topics=", ".join(t(f"learn.topic.{i}") for i in range(1, 5))),
                                      t("learn.coming_soon")), unsafe_allow_html=True)
    st.button(t("practice.go"), key="learn-practice", icon=":material/quiz:", on_click=go, args=("Practice",))


def close_guide():
    st.session_state.pop("learn_guide", None)
    if "guide" in st.query_params:
        del st.query_params["guide"]


def source_html(source) -> str:
    """"Source: <the Act or section, linked>" from a guide's source: the Act/section as the guide writes it,
    linked to the first knowledge/ entry's official page; other pages it names follow as "also" links."""
    e = html.escape
    links = []
    for _, link in source.links():
        if link and link not in links:
            links.append(link)
    name = e(source.text)
    if links:
        name = f'<a href="{e(links[0])}" target="_blank" rel="noopener noreferrer">{name}</a>'
    others = ", ".join(f'<a href="{e(l)}" target="_blank" rel="noopener noreferrer">{e(research.host(l) or l)}</a>'
                       for l in links[1:])
    extra = f" · {e(t('learn.also'))}: {others}" if others else ""  # "also" only when something follows
    return f'<p class="learn-src">{e(t("learn.source"))} {name}{extra}</p>'


def show_point(n, point):
    st.markdown(f'<div class="learn-point"><p><b>{n}.</b> {html.escape(point.text)}</p>{source_html(point.source)}</div>',
                unsafe_allow_html=True)


def quiz_block(guide, prefix: str) -> tuple:
    """The five-question check: choose an option and the feedback shows at once (right or wrong, why,
    then the Act or section, linked). Returns (answered, right)."""
    content = guides.content(guide.key)
    answered = right = 0
    for n, q in enumerate(content.quiz, 1):
        with st.container(border=True, key=f"{prefix}-q-{guide.key}-{n}"):
            letters = [letter for letter, _ in q.options]
            texts = dict(q.options)
            choice = st.radio(f"{n}\\. {q.text}", letters, index=None, key=f"{prefix}-{guide.key}-{n}",  # "1." kept
                              format_func=lambda letter, d=texts: f"{letter}) {d[letter]}")
            ok = guides.check_answer(q, choice)
            if ok is None:
                continue
            answered += 1
            right += bool(ok)
            if ok:
                st.success(f"**{t('learn.right')}** {q.why}", icon=":material/check_circle:")
            else:
                st.error(f"**{t('learn.wrong', answer=q.answer + ') ' + texts[q.answer])}** {q.why}",
                         icon=":material/cancel:")
            st.markdown(source_html(q.source), unsafe_allow_html=True)
    return answered, right


def practice_cases(guide, prefix: str):
    """Each case's core facts up front; the model answer in its own collapsible section."""
    for i, case in enumerate(guides.content(guide.key).practice, 1):
        with st.container(border=True, key=f"{prefix}-case-{guide.key}-{i}"):
            st.markdown(f"**{html.escape(t('learn.case_n', n=i))}: {html.escape(case.title)}**")
            st.markdown(f"*{t('learn.core_facts')}*  \n" + "\n".join(f"- {html.escape(f)}" for f in case.facts),
                        unsafe_allow_html=True)
            with st.expander(t("learn.model_answer")):
                for line in case.answer:
                    src = source_html(line.source) if line.source.refs else ""
                    st.markdown(f'<div class="learn-point"><p>• {html.escape(line.text)}</p>{src}</div>',
                                unsafe_allow_html=True)


def show_guide(guide):
    content = guides.content(guide.key)
    with st.container(key="guide-page", border=True):
        st.markdown(f"## {ui.icon(guide.icon)} {html.escape(t(f'home.learn{guide.number}'))}", unsafe_allow_html=True)
        if code() != "en":
            st.caption(t("learn.english_only"))
        st.markdown(f"#### {t('learn.able')}")
        st.markdown("\n".join(f"- {html.escape(o)}" for o in content.outcomes))
        st.markdown(f"#### {t('learn.key_idea')}")
        for n, p in enumerate(content.points, 1):
            show_point(n, p)
        st.markdown(f"#### {t('learn.example')}")
        st.markdown(f'<p class="learn-intro">{html.escape(content.example_intro)}</p>', unsafe_allow_html=True)
        for n, step in enumerate(content.steps, 1):
            show_point(t("learn.step_n", n=n), step)
        st.markdown(f"#### {t('learn.try_it')}")
        practice_cases(guide, "learn")
        st.markdown(f"#### {t('learn.check', n=len(content.quiz))}")
        st.caption(t("learn.check_caption"))
        quiz_block(guide, "learn")


def practice_screen():
    """"Practice: test yourself": every ready guide's check and practice cases, with a score. Public, like
    Learn (no passcode). The score is only in this browser session; nothing is saved."""
    page_title(t("practice.title"))
    st.caption(t("practice.caption"))
    score = st.empty()
    total_answered = total_right = total = 0
    for g in guides.ready_guides():
        content = guides.content(g.key)
        total += len(content.quiz)
        st.markdown(f"### {ui.icon(g.icon)} {html.escape(t(f'home.learn{g.number}'))}", unsafe_allow_html=True)
        answered, right = quiz_block(g, "prac")
        total_answered += answered
        total_right += right
        st.markdown(f"#### {t('learn.try_it')}")
        practice_cases(g, "prac")
    score.markdown(f'<p class="practice-score">{html.escape(t("practice.score", right=total_right, answered=total_answered, total=total))}</p>',
                   unsafe_allow_html=True)

def supervisor_password() -> str:
    """Read the supervisor password from an environment variable or Streamlit secrets.
    It is never written in the code."""
    # storage.setting: the environment, .env or the host's secret settings (never the real secrets in tests)
    return storage.setting("SUPERVISOR_PASSWORD")


SUPERVISOR_ACTOR = "Supervisor"  # the name saved with actions when the supervisor signed in without one


def is_supervisor_password(typed: str) -> bool:
    """True if typed is the supervisor password (spaces copied in by mistake around it are ignored)."""
    expected = supervisor_password().strip()
    return bool(expected) and hmac.compare_digest((typed or "").strip().encode(), expected.encode())


SUPERVISOR_IDLE_SECONDS = 30 * 60  # shared computers at camps: sign the supervisor out after 30 idle minutes


def guard_keys(kind: str) -> list:
    """Who the wrong-password count is for: this browser session and (as a second check) its network
    address, so reloading the page does not start the count again."""
    session = st.session_state.setdefault("_session_key", secrets.token_hex(8))
    try:
        ip = st.context.ip_address
    except Exception:
        ip = None
    return [f"{kind}:session:{session}"] + ([f"ip:{kind}:{ip}"] if ip else [])


def locked_message(kind: str) -> str:
    """"Too many tries; wait 5 minutes" while this sign-in is locked ("" when it is not)."""
    return t("gate.too_many") if signin_guard.seconds_locked(guard_keys(kind)) else ""


def supervisor_sign_in():
    """Runs when the supervisor clicks Sign in. The supervisor password alone opens the supervisor
    screen (the name is asked next) and the clinic's other screens for this session."""
    keys = guard_keys("supervisor")
    if signin_guard.seconds_locked(keys):
        st.session_state["sup-msg"] = t("gate.too_many")
        return
    if not is_supervisor_password(st.session_state.get("sup-pass") or ""):
        signin_guard.failed(keys)
        st.session_state["sup-msg"] = t("gate.too_many") if signin_guard.seconds_locked(keys) else t("ui.sup.wrong")
        return
    signin_guard.succeeded(keys)
    st.session_state.update(supervisor_ok=True, sup_last_active=time.time(), **{"sup-pass": ""})
    st.session_state.pop("supervisor_name", None)  # asked next, every time
    if not st.session_state.get("clinic_ok"):  # clinic access came with the supervisor sign-in
        st.session_state.update(clinic_ok=True, clinic_via_supervisor=True)
        if not (st.session_state.get("volunteer") or "").strip():
            st.session_state["volunteer"] = SUPERVISOR_ACTOR  # until the name is given


def supervisor_name_given():
    """Runs when the supervisor types their name or initials after the password."""
    name = tracker.clean_text(st.session_state.get("sup-name") or "", 40)
    if not name:
        st.session_state["sup-msg"] = t("gate.need_name")
        return
    st.session_state.update(supervisor_name=name, sup_last_active=time.time())
    if st.session_state.get("clinic_via_supervisor"):
        st.session_state["volunteer"] = name  # what they do on other screens is saved with their name too


def supervisor_name() -> str:
    return st.session_state.get("supervisor_name") or ""


def supervisor_sign_out():
    st.session_state["supervisor_ok"] = False
    for key in ("supervisor_name", "sup_last_active"):
        st.session_state.pop(key, None)
    if st.session_state.pop("clinic_via_supervisor", False):  # the clinic access ends with it
        for key in ("clinic_ok", "volunteer", "case_id"):
            st.session_state.pop(key, None)


def supervisor_idle_check():
    """At the start of every run: a supervisor idle for 30 minutes is signed out; any other run counts
    as activity. (The timer below makes the screen check by itself, even if nobody touches it.)"""
    if not st.session_state.get("supervisor_ok"):
        return
    now = time.time()
    if now - st.session_state.get("sup_last_active", now) > SUPERVISOR_IDLE_SECONDS:
        supervisor_sign_out()
        st.session_state["sup-msg-info"] = t("ui.sup.idle_out")
    else:
        st.session_state["sup_last_active"] = now


@st.fragment(run_every=60)
def supervisor_idle_timer():
    """Once a minute, without counting as activity: if the supervisor has been idle for 30 minutes,
    run the whole page again, which signs them out and hides the supervisor screen."""
    last = st.session_state.get("sup_last_active")
    if st.session_state.get("supervisor_ok") and last and time.time() - last > SUPERVISOR_IDLE_SECONDS:
        st.rerun(scope="app")


def supervisor_screen():
    if not supervisor_password():
        page_title(t("ui.sup.sign_in_title"))
        st.warning(t("ui.sup.no_password"))
        return
    if not st.session_state.get("supervisor_ok"):
        # Only the supervisor password: no clinic passcode and no name
        page_title(t("ui.sup.sign_in_title"), helplines=False)
        info = st.session_state.pop("sup-msg-info", None)
        if info:
            st.info(info, icon=":material/timer:")
        with signin_columns("s"), st.container(key="signin-card"):
            practice_hint()
            with st.form("sup-form", enter_to_submit=True, border=False):  # Enter signs in
                st.text_input(t("ui.sup.password"), type="password", key="sup-pass")
                st.form_submit_button(t("ui.sup.sign_in"), type="primary", key="sup-go", on_click=supervisor_sign_in)
            msg = st.session_state.pop("sup-msg", None) or locked_message("supervisor")
            if msg:
                st.error(msg)
        return
    if not supervisor_name():
        # After the password: the supervisor's name or initials, saved with every decision
        page_title(t("ui.sup.sign_in_title"), helplines=False)
        with signin_columns("s"), st.container(key="signin-card"):
            with st.form("sup-name-form", enter_to_submit=True, border=False):
                st.text_input(t("gate.name"), key="sup-name", max_chars=40, help=t("ui.sup.name_help"))
                st.form_submit_button(t("ui.next"), type="primary", key="sup-name-go", on_click=supervisor_name_given)
            msg = st.session_state.pop("sup-msg", None)
            if msg:
                st.error(msg)
            st.button(t("ui.sup.sign_out"), key="sup-out", type="tertiary", on_click=supervisor_sign_out)
        return
    page_title(t("ui.sup.title"))
    top1, top2 = st.columns([3, 1])
    top1.success(t("ui.sup.signed_in_as", name=supervisor_name()))
    top2.button(t("ui.sup.sign_out"), type="primary", icon=":material/logout:", key="sup-out",  # navy, filled
                on_click=supervisor_sign_out)

    flash = st.session_state.pop("supervisor_flash", None)
    if flash:
        st.success(flash)
    already = st.session_state.pop("supervisor_flash_info", None)
    if already:
        st.info(already, icon=":material/info:")

    # 1. Waiting for you: a compact list; one case open below it, in three steps
    rows = waiting_rows()
    if not rows:
        st.info(no_drafts_waiting_text(), icon=":material/inbox:")
    else:
        st.subheader(t("ui.sup.waiting", n=len(rows)))
        # two fixed areas, made first and in this order: the list, then the open case (its cards can only
        # ever be drawn in the second, never inside a list row)
        list_area, case_area = st.container(key="sup-list-area"), st.container(key="sup-case-area")
        with list_area:
            current = waiting_list(rows)
        if current:
            with case_area:
                review_open_case(next(r for r in rows if r["id"] == current))
    changed_after_approval_box()

    # 2. All cases (audit records), folded
    with st.expander(t("ui.sup.audit_all_fold"), icon=":material/table_view:"):
        audit_records_box(heading=False)

    # 3. Tools, folded
    with st.expander(t("ui.sup.tools"), icon=":material/build:"):
        research_review_box()
        knowledge_added_box()
        delete_case_box()
        evaluation_box()
        evaluation_scoring_box()
        impact_box()
        problems_box()
        if practice.is_practice():  # never shown (or usable) in a real clinic
            practice_reset_box()


def practice_reset_box():
    """Practice Clinic only: put every practice case back to how it was when the snapshot was taken."""
    st.markdown(f"#### {html.escape(t('pr.title'))}")
    manifest = practice.latest()
    if not manifest:
        st.caption(t("pr.no_snapshot"))
        return
    when = show_stamp(manifest["taken_at"])
    st.caption(t("pr.caption", when=when, n=sum(manifest.get("counts", {}).values())))
    resets = manifest.get("resets") or []
    if resets:
        st.caption(t("pr.last_reset", when=show_stamp(resets[-1]["at"]), by=resets[-1]["by"]))
    if not st.session_state.get("pr-confirm"):
        st.button(t("pr.button"), key="pr-start", icon=":material/restart_alt:",
                  on_click=lambda: st.session_state.update({"pr-confirm": True}))
        return
    st.warning(t("pr.confirm", when=when), icon=":material/warning:")
    with st.container(horizontal=True, gap="small", key="pr-buttons"):
        st.button(t("pr.yes"), key="pr-yes", type="primary", on_click=reset_practice_clinic)
        st.button(t("pr.cancel"), key="pr-cancel", on_click=lambda: st.session_state.update({"pr-confirm": False}))


def reset_practice_clinic():
    st.session_state["pr-confirm"] = False
    try:
        practice.reset(supervisor_name())
    except (practice.PracticeError, storage.StorageError, ValueError) as err:
        st.session_state["supervisor_flash"] = str(err)
        return
    st.session_state.pop("sup-open", None)
    st.session_state["supervisor_flash_info"] = t("pr.done", when=show_stamp(practice.latest()["taken_at"]),
                                                  by=supervisor_name())


def problems_box():
    st.markdown(f"#### {html.escape(t('ui.sup.problems'))}")
    problems = audit.list_problems()
    if not problems:
        st.caption(t("ui.sup.no_problems"))
    else:
        st.markdown(problems_summary(problems))
        with st.expander(t("ui.sup.problems_details", n=len(problems))):
            for p in problems:
                st.markdown(f"- **{show_stamp(p['time'])}** · {t('ui.case')} {p['case_id']} · {p['where']}: "
                            f"{p['text']}" + (f" _({t('ui.sup.removed')} {p['removed']})_" if p.get("removed") else ""))


AUDIT_COLUMNS = [("code", "aud.code"), ("case_type", "aud.case_type"), ("status", "aud.status"),
                 ("sent_by", "aud.sent_by"), ("sent_on", "aud.sent_on"), ("decision_by", "aud.decision_by"),
                 ("decision_on", "aud.decision_on"), ("ai_used", "aud.ai_used"), ("last_step", "aud.last_step")]
HISTORY_COLUMNS = [("time", "aud.time"), ("event", "aud.event"), ("by", "aud.by"), ("details", "aud.details")]
STATUS_COLOURS = {"intake": ("#EEE9DF", "#4B5563"), "waiting": ("#E0F2FE", "#0C4A6E"),
                  "sent back": ("#FEF3C7", "#78350F"), "approved": ("#DCFCE7", "#14532D"),
                  "closed": ("#E0E7FF", "#312E81"), "deleted": ("#E5E7EB", "#374151")}  # the app's chip colours; intake in progress grey


def audit_records() -> dict:
    """Every case: its audit record, or (opened in the tracker, nothing recorded yet) "case opened"."""
    records = {r["case_id"]: r for r in audit.list_records()}
    for r in tracker.all_records():
        records.setdefault(r["id"], audit.opened_record(r))
    return records


def audit_rows(records: dict = None) -> list:
    """One row per case, with the case code, type and the AI that read the story from the tracker."""
    records = records if records is not None else audit_records()
    tracked = {r["id"]: r for r in tracker.all_records()}
    pending = {r["id"]: r for r in storage.all_json("pending") if store.ID_PATTERN.match(r.get("id", ""))}
    rows = []
    for case_id, record in records.items():
        known = tracked.get(case_id) or {}
        kind = (pending.get(case_id) or {}).get("case_type") or known.get("case_type", "")
        row = audit.summary_row(record, known.get("code", ""), kind, known.get("ai_model", ""))
        row["case_type"] = case_type_label(row["case_type"]) if row["case_type"] else "-"
        row["status_label"] = t(f"aud.st.{row['status']}")
        rows.append(row)
    return rows


def shown_table(rows: list, columns: list):
    """A table of rows with translated headings; the status column as coloured chips."""
    import pandas as pd
    def cell(r, k):
        if k == "status":
            return r["status_label"]
        if k == "ai_used":  # the plain name on screen; the CSV keeps the raw id
            return llm.display_model(r.get(k, "")) or r.get(k, "")
        return r.get(k, "")
    frame = pd.DataFrame([{t(h): cell(r, k) for k, h in columns} for r in rows], columns=[t(h) for _, h in columns])
    if any(k == "status" for k, _ in columns) and rows:
        colours = {t(f"aud.st.{s}"): c for s, c in STATUS_COLOURS.items()}
        frame = frame.style.map(lambda v: (f"background-color: {colours[v][0]}; color: {colours[v][1]}; "
                                           "font-weight: 600") if v in colours else "", subset=[t("aud.status")])
    return frame


def open_audit_row():
    """Clicking a row of the audit table opens that case's history below it; a case waiting for review
    also jumps to its review box further down the page."""
    selection = (st.session_state.get("aud-table") or {}).get("selection", {})
    picked = list(selection.get("rows", [])) or [cell[0] for cell in selection.get("cells", [])]  # tick box or any cell
    ids = st.session_state.get("aud-ids", [])
    case_id = ids[picked[0]] if picked and picked[0] < len(ids) else None
    st.session_state["aud-open"] = case_id
    waiting = st.session_state.get("aud-waiting", [])
    if case_id in waiting:  # a case waiting for review: it opens at the top, under "Waiting for you"
        st.session_state["sup-open"] = case_id


def audit_records_box(heading: bool = True):
    """Audit records of all cases: one row per case (newest first), with search, status and date filters;
    a row opens the case's full history; both download as CSV."""
    if heading:
        st.subheader(t("ui.sup.audit_all"))
    records = audit_records()
    rows = audit_rows(records)
    if not rows:
        st.caption(t("ui.sup.no_audit"))
        return
    n = audit.counts_line(rows)
    line = [t("aud.n_cases", n=len(rows)), t("aud.n_waiting", n=n["waiting"]), t("aud.n_intake", n=n["intake"]),
            t("aud.n_approved", n=n["approved"])]
    line += [t("aud.n_sent_back", n=n["sent back"])] if n["sent back"] else []
    line += [t("aud.n_closed", n=n["closed"])] if n["closed"] else []
    line += [t("aud.n_deleted", n=n["deleted"])] if n["deleted"] else []
    st.markdown(f'<p class="aud-counts">{html.escape(" · ".join(line))}</p>', unsafe_allow_html=True)
    st.session_state["aud-waiting"] = [r["case_id"] for r in rows if r["status"] == "waiting"]
    with st.container(key="aud-filters", horizontal=True, gap="small"):
        st.text_input(t("aud.search"), key="aud-q", max_chars=20, placeholder="K7M2QX")
        st.selectbox(t("aud.status"), [""] + audit.STATUSES, key="aud-status",
                     format_func=lambda s: t(f"aud.st.{s}") if s else t("aud.all"))
        st.date_input(t("aud.dates"), value=(), key="aud-dates", format="DD/MM/YYYY", max_value=date.today())
    dates = st.session_state.get("aud-dates") or ()
    start = dates[0] if len(dates) > 0 else None
    end = dates[1] if len(dates) > 1 else start
    shown = audit.filter_rows(rows, st.session_state.get("aud-q", ""), st.session_state.get("aud-status") or "",
                              start, end)
    st.session_state["aud-ids"] = [r["case_id"] for r in shown]
    st.caption(t("aud.count", n=len(shown), total=len(rows)) + " " + t("aud.click"))
    with st.container(key="aud-table-box"):
        st.dataframe(shown_table(shown, AUDIT_COLUMNS), key="aud-table", hide_index=True, width="stretch",
                     on_select=open_audit_row, selection_mode=["single-row", "single-cell"])
    st.download_button(t("aud.csv"), audit.to_csv([{**r, "status": r["status_label"]} for r in shown],
                                                  [(k, t(h)) for k, h in AUDIT_COLUMNS]),
                       file_name=f"audit-records-{date.today():%Y-%m-%d}.csv", mime="text/csv",
                       key="aud-csv", icon=":material/download:")
    case_id = st.session_state.get("aud-open")
    record = records.get(case_id) if case_id in st.session_state["aud-ids"] else None
    if record:
        row = next(r for r in shown if r["case_id"] == case_id)
        st.markdown(f"**{t('aud.history_of', slip=row['code'], case_id=case_id)}**")
        audit_ai_summary(record)
        history_table(record, "aud-hist")
        close_or_reopen_box(case_id, row["status"])


def closed_line(closed: dict) -> str:
    """"Closed: resolved · the note · by SK on 11 November 2026"."""
    when = show_date(date.fromisoformat(closed["on"][:10]))
    return t("close.line", reason=t(f"close.reason.{closed['reason']}"), note=(" · " + closed["note"]) if closed.get("note")
             else "", by=closed["by"], on=when)


def close_case_now(case_id: str):
    get = st.session_state.get
    try:
        tracker.close_case(case_id, get(f"close-reason-{case_id}") or "", get(f"close-note-{case_id}") or "",
                           supervisor_name())
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state[f"close-msg-{case_id}"] = ("error", str(err))
        return
    st.session_state["supervisor_flash"] = t("close.done", case_id=case_id)


def reopen_case_now(case_id: str):
    try:
        tracker.reopen_case(case_id, st.session_state.get(f"reopen-reason-{case_id}") or "", supervisor_name())
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state[f"close-msg-{case_id}"] = ("error", str(err))
        return
    st.session_state["supervisor_flash"] = t("close.reopened", case_id=case_id)


def close_or_reopen_box(case_id: str, status: str):
    """Supervisor only: close an approved case (reason and a short note, no names), or reopen a closed
    one (with a reason). Both go in the audit record with the supervisor's name."""
    if status not in ("approved", "closed") or tracker.load(case_id) is None:
        return
    with st.container(border=True, key=f"close-box-{case_id}"):
        if status == "approved":
            st.markdown(f"**{t('close.title')}**")
            st.selectbox(t("close.reason"), tracker.CLOSE_REASONS, index=None, key=f"close-reason-{case_id}",
                         format_func=lambda r: t(f"close.reason.{r}"), placeholder=t("close.choose"))
            st.text_input(t("close.note"), key=f"close-note-{case_id}", max_chars=200, help=t("close.note_help"))
            st.button(t("close.go"), key=f"close-go-{case_id}", type="primary", icon=":material/lock:",
                      disabled=not st.session_state.get(f"close-reason-{case_id}"), on_click=close_case_now,
                      args=(case_id,))
            if not st.session_state.get(f"close-reason-{case_id}"):
                why_disabled(t("why.close_reason"))
        else:
            record = tracker.load(case_id) or {}
            if record.get("closed"):
                st.markdown(f"**{html.escape(closed_line(record['closed']))}**")
            st.text_input(t("close.reopen_reason"), key=f"reopen-reason-{case_id}", max_chars=200,
                          help=t("close.note_help"))
            st.button(t("close.reopen"), key=f"reopen-go-{case_id}", icon=":material/lock_open:",
                      on_click=reopen_case_now, args=(case_id,))
        msg = st.session_state.pop(f"close-msg-{case_id}", None)
        if msg:
            st.error(msg[1])


# Fields that fit only some problems (the rest fit every general case)
FIELDS_FOR = {"money_lost_online": "fraud", "money_lost_in_last_few_days": "fraud", "called_1930": "fraud",
              "essential_service_cut": ("electricity", "water"), "has_reference_number": ("electricity", "water", "ration")}
UNDERTRIAL_ONLY = {"custody_began", "offence_date", "offence_month", "section", "law", "more_than_one_section",
                   "never_convicted", "other_cases_pending", "delay_days_by_accused", "lawyer", "answer", "today"}


def audit_fact_label(key: str) -> str:
    for k in (f"ledger.f.{key}", f"fact.{key}", f"tfact.{key}"):
        if k in lang.strings("en"):
            return t(k)
    return key.replace("_", " ")


def show_stamp(text: str) -> str:
    """"2026-11-12T22:27:05" -> "12 November 2026, 22:27"."""
    try:
        return f"{show_date(date.fromisoformat(text[:10]))}, {text[11:16]}" if len(text) >= 16 else \
            show_date(date.fromisoformat(text[:10]))
    except ValueError:
        return text


def audit_ai_summary(record: dict, case_facts: "dict | None" = None):
    """What the AI read and what the volunteer changed, in the case form's plain labels ("A woman: yes"),
    only the fields that fit the case type, dates written out."""
    case_type = record.get("case_type") or ""
    kind = None
    if case_type == general.CASE_TYPE and case_facts:
        try:
            kind = casework.problem_type(general.GeneralFacts.from_dict(case_facts))
        except Exception:
            kind = None

    def fits(key):
        if case_type == general.CASE_TYPE and key in UNDERTRIAL_ONLY:
            return False
        if case_type == "Undertrial" and key not in UNDERTRIAL_ONLY and key not in ("in_custody", "woman", "under_18"):
            return False
        need = FIELDS_FOR.get(key)
        return need is None or kind is None or kind in (need if isinstance(need, tuple) else (need,))

    def value(v):
        return t("yes") if v is True else t("no") if v is False else str(v)
    lines = [t("aud.ai_model", model=llm.display_model(record.get("model")) or record.get("model", ""))]
    if record.get("ai_read_at"):
        lines.append(t("aud.ai_read_at", when=show_stamp(record["ai_read_at"])))
    found = [f"{audit_fact_label(k)}: {value(v)}" for k, v in (record.get("ai_extracted") or {}).items() if fits(k)]
    if found:
        lines.append(t("aud.ai_found", facts="; ".join(found)))
    blank = [audit_fact_label(k) for k in record.get("ai_answers_not_accepted") or [] if fits(k)]
    if blank:
        lines.append(t("aud.ai_blank", facts=", ".join(blank)))
    changed = [f"{audit_fact_label(c['field'])} ({c['ai_value']} → {c['final_value']})" for c in record.get("volunteer_changed") or []
               if fits(c["field"])]
    if record.get("model") not in (audit.NO_AI, None):
        lines.append(t("aud.changed", fields="; ".join(changed) if changed else t("aud.none")))
        typed = [audit_fact_label(k) for k in record.get("entered_by_volunteer") or [] if fits(k)]
        if typed:
            lines.append(t("aud.typed", fields=", ".join(typed)))
    st.caption("  \n".join(lines))


def event_text(event: str) -> str:
    """An audit event in plain words: "Point rejected" (a research point) and "Drafts sent back" (the drafts),
    never just "rejected" or "sent back". Other events as saved."""
    return t(f"aud.ev.{event}") if f"aud.ev.{event}" in lang.strings(lang.DEFAULT) else event


def history_table(record: dict, key: str):
    """One case's full history: Time, What happened, By, Details (the same table everywhere)."""
    rows = [{**r, "event": event_text(r["event"])} for r in audit.history_rows(record)]
    with st.container(key=f"{key}-box"):
        st.dataframe(shown_table(rows, HISTORY_COLUMNS), key=key, hide_index=True, width="stretch")
    st.download_button(t("aud.csv"), audit.to_csv(rows, [(k, t(h)) for k, h in HISTORY_COLUMNS]),
                       file_name=f"audit-{record['case_id']}.csv", mime="text/csv", key=f"{key}-csv",
                       icon=":material/download:")


def short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rsplit(" ", 1)[0] + "\u2026"


def problems_summary(problems: list) -> str:
    """One short line: "Today: AI busy 14 times; the backup answered 10. Earlier: 3 problems." """
    today = date.today().isoformat()
    todays = [p for p in problems if p["time"].startswith(today)]
    busy = [p for p in todays if not p.get("research_search")]
    backup = [p for p in busy if str(p.get("outcome", "")).startswith("answered")]
    parts = [t("ui.sup.problems_today", n=len(busy), ok=len(backup))] if busy else []
    searches = [p for p in todays if p.get("research_search")]
    if searches:
        parts.append(t("ui.sup.problems_search", n=len(searches)))
    earlier = len(problems) - len(todays)
    if earlier:
        parts.append(t("ui.sup.problems_earlier", n=earlier))
    return " · ".join(parts) or t("ui.sup.problems_earlier", n=len(problems))


def point_counts(case_id: str) -> tuple:
    """(approved, rejected, not decided) research points for a case, from the saved records."""
    points = [p for r in research.for_case(case_id) for p in r["points"] if p.get("kind") != "letter"]
    return (sum(p["status"].startswith("approved") for p in points), sum(p["status"] == "rejected" for p in points),
            sum(p["status"] == research.WAITING for p in points))


def add_letter_to_pending(case_id: str, issue: str = ""):
    """The complaint letter, rebuilt from the facts of the case and ONLY the points the supervisor approved
    (points not decided are left out, and the notes say how many). No point approved: a facts-only letter."""
    try:
        pending = store.get_pending(case_id)
    except ValueError:
        return
    briefs = research.for_case(case_id)
    if pending.get("case_type") != general.CASE_TYPE or not briefs:
        return
    issue = issue or briefs[-1]["issue"]
    approved = research.approved_points(case_id)
    not_decided = point_counts(case_id)[2]
    g = general.GeneralFacts.from_dict(pending["facts"])
    lang_code = pending.get("draft_lang", "en")
    if not approved:  # no point approved: the letter goes back to facts only (no legal points)
        store.replace_letter(case_id, casework.facts_only_letter(g, issue, pending.get("ai_model"), lang_code, not_decided))
        return
    store.replace_letter(case_id, casework.complaint_letter(g, approved, issue, pending.get("ai_model"), lang_code,
                                                            not_decided))


def save_research_knowledge(research_id: str, point_id: str):
    get = st.session_state.get
    words = [w.strip() for w in (get(f"rsk-w-{research_id}-{point_id}") or "").split(",") if w.strip()]
    try:
        entry = research.save_knowledge(research_id, point_id, get(f"rsk-h-{research_id}-{point_id}") or "", words)
    except (research.ResearchFailed, storage.StorageError) as err:
        st.session_state["supervisor_flash"] = str(err)
        return
    st.session_state["supervisor_flash"] = t("rs.k_saved", id=entry["id"], state=entry["state"])


def warning_text(w: dict) -> str:
    """A research warning in the screen's language (the saved English text if it is an older record)."""
    try:
        if w["kind"] == "replaced" and w.get("in_source"):
            return t("rs.warn_replaced_source", old=w["old"], new=w["new"], date=show_date(date.fromisoformat(w["since"])))
        if w["kind"] == "replaced":
            return t("rs.warn_replaced", new=w["new"], date=show_date(date.fromisoformat(w["since"])))
        if w["kind"] == "mismatch":
            return t("rs.warn_mismatch", law=w["law"], title=w["title"])
        if w["kind"] == "other_state":
            return t("rs.warn_other_state", other=w["other"], state=w["state"])
    except KeyError:
        pass
    return w["text"]


# ---------- the supervisor's research checklist: one list, one button ----------

KIND_KEYS = {"route": "rs.kind.route", "documents": "rs.kind.documents", "time_limit": "rs.kind.time_limit",
             "how_to_file": "rs.kind.how_to_file"}
MD_SPECIAL = re.compile(r"([\\`*_\[\]$<>#|~])")


def md_plain(text: str) -> str:
    """Text shown as it is in a widget label (no bold, links or maths from stray * [ ] $)."""
    return MD_SPECIAL.sub(r"\\\1", text or "")


def kind_label(kind: str) -> str:
    return t(KIND_KEYS[kind]) if kind in KIND_KEYS else research.KINDS.get(kind, kind)


def rs_ticked(r: dict, p: dict) -> bool:
    """Ticked = approve. Ticked at first for the points the volunteer kept, unticked for those left out."""
    return bool(st.session_state.setdefault(f"rsx-{r['id']}-{p['id']}", p.get("volunteer") != research.LEFT_OUT))


def rs_edited(r: dict, p: dict) -> str:
    """The supervisor's edited text ("" when not edited). Kept outside the text box, so it stays when the box is closed."""
    text = " ".join((st.session_state.get(f"rsedv-{r['id']}-{p['id']}") or "").split())
    return text if text and text != " ".join(p["text"].split()) else ""


def keep_edit(key: str):
    st.session_state[key.replace("rse-", "rsedv-", 1)] = st.session_state.get(key, "")


def toggle_flag(key: str):
    st.session_state[key] = not st.session_state.get(key)


def rs_reject_reason(r: dict, p: dict) -> str:
    """The supervisor's reason for rejecting a point: a quick choice, or "Other" with a short text ("" if none)."""
    get = st.session_state.get
    kb = f"{r['id']}-{p['id']}"
    choice = get(f"rsr-{kb}")
    if choice == "other":
        return (get(f"rsrt-{kb}") or "").strip()
    return t(f"rs.why_left.{choice}") if choice else ""


def rs_state(r: dict, p: dict) -> str:
    """What saving does with a waiting point: "approve" (ticked), "reject" (unticked, with a reason),
    "undecided" (left out by the volunteer and not touched: stays out of the letter, for later) or
    "missing" (kept by the volunteer, then unticked: a reason is needed)."""
    if rs_ticked(r, p):
        return "approve"
    if rs_reject_reason(r, p):
        return "reject"
    return "undecided" if p.get("volunteer") == research.LEFT_OUT else "missing"


def rs_checklist_state(r: dict, waiting: list) -> tuple:
    """(approved, rejected, not decided, [what still stops the save])."""
    import replaced_laws
    counts = {"approve": 0, "reject": 0, "undecided": 0, "missing": 0}
    needs_edit = 0
    for p in waiting:
        state = rs_state(r, p)
        counts[state] += 1
        edited = rs_edited(r, p)
        if state == "approve" and ((research.blocked(p) and not edited) or
                                   (edited and replaced_laws.still_relies_on_old(edited))):
            needs_edit += 1
    problems = ([t("why.rs_reason_missing", n=counts["missing"])] if counts["missing"] else []) + \
               ([t("why.rs_edit_needed", n=needs_edit)] if needs_edit else [])
    return counts["approve"], counts["reject"], counts["undecided"], problems


def case_point_problems(case_id: str) -> list:
    """What stops the point decisions of a case being saved (a missing reason, a replaced law not edited)."""
    problems = []
    for r in research.for_case(case_id):
        waiting = [p for p in r["points"] if p.get("kind") != "letter" and p["status"] == research.WAITING]
        problems += rs_checklist_state(r, waiting)[3]
    return list(dict.fromkeys(problems))


def save_point_decisions(case_id: str, approve_all: bool = False):
    """Save the decisions on screen for every waiting point of a case (one audit entry per point, with the
    supervisor's name and the date). Points not decided stay waiting. approve_all: every point the volunteer
    kept is approved (a point naming a replaced law only once edited). Raises ValueError for anything that stops the save.
    Returns the number of points left as they were because they name a replaced law."""
    import replaced_laws
    if not approve_all:
        problems = case_point_problems(case_id)
        if problems:
            raise ValueError(problems[0])
    by, skipped = supervisor_name(), 0
    for r in research.for_case(case_id):
        for p in [p for p in r["points"] if p.get("kind") != "letter" and p["status"] == research.WAITING]:
            edited = rs_edited(r, p)
            state = "approve" if approve_all and p.get("volunteer") != research.LEFT_OUT else rs_state(r, p)
            if state == "approve":
                if (research.blocked(p) and not edited) or (edited and replaced_laws.still_relies_on_old(edited)):
                    skipped += 1
                    continue
                research.decide(r["id"], p["id"], research.EDIT if edited else research.APPROVE, edited or None, by=by)
            elif state == "reject":
                research.decide(r["id"], p["id"], research.REJECT, by=by, reason=rs_reject_reason(r, p))
    return skipped


def research_row(r: dict, p: dict, locked: bool):
    """One point: the tick box with its text, a small kind tag and the source links, then "Edit" (opens the text
    in place) and, when unticked, the reason for rejecting it."""
    kb = f"{r['id']}-{p['id']}"
    edited = rs_edited(r, p)
    text = edited or p["text"]
    with st.container(key=f"rs-row-{kb}"):
        if locked:  # someone else must decide: the point only, no tick box
            st.markdown(html.escape(text))
        else:
            rs_ticked(r, p)
            st.checkbox(md_plain(text), key=f"rsx-{kb}")
        links = " · ".join(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(label)}</a>'
                           for label, url in research.source_labels(p["sources"]))
        undecided = not locked and rs_state(r, p) == "undecided"
        st.markdown(f'<div class="rs-meta">{ui.tag(kind_label(p["kind"]))}'
                    + (f' <span class="tag edited">{html.escape(t("rs.edited"))}</span>' if edited else "")
                    + (f' <span class="tag undecided">{html.escape(t("rs.not_decided"))}</span>'
                       if undecided or locked else "")
                    + (f' <span class="rs-src">{ui.icon("link")} {links}</span>' if links else "") + "</div>",
                    unsafe_allow_html=True)
        if p.get("volunteer") == research.LEFT_OUT:
            st.caption(t("rs.sup_left_why", reason=p.get("volunteer_reason") or t("rs.no_reason")))
        for w in p.get("warnings", []):
            (st.error if w["kind"] == "replaced" else st.warning)(
                warning_text(w), icon=":material/gavel:" if w["kind"] == "replaced" else ":material/rule:")
        if locked:
            return
        if research.blocked(p) and not edited:
            st.caption(t("rs.edit_needed"))
        open_key = f"rso-{kb}"
        st.button(t("rs.edit_close") if st.session_state.get(open_key) else t("rs.edit_link"), key=f"rsedit-{kb}",
                  type="tertiary", icon=":material/edit:", on_click=toggle_flag, args=(open_key,))
        if st.session_state.get(open_key):
            st.session_state.setdefault(f"rse-{kb}", st.session_state.get(f"rsedv-{kb}") or p["text"])
            st.text_area(t("rs.edit_label"), key=f"rse-{kb}", height=110, on_change=keep_edit, args=(f"rse-{kb}",))
        if not st.session_state.get(f"rsx-{kb}"):  # kept by the volunteer: a reason is needed; left out: optional
            left_out = p.get("volunteer") == research.LEFT_OUT
            st.radio(t("rs.reject_optional" if left_out else "rs.reject_reason"), LEFT_OUT_CHOICES, index=None,
                     horizontal=True, key=f"rsr-{kb}", format_func=lambda c: t(f"rs.why_left.{c}"))
            if st.session_state.get(f"rsr-{kb}") == "other":
                st.text_input(t("rs.why_left.other_text"), key=f"rsrt-{kb}", max_chars=200)


def decided_row(r: dict, p: dict):
    """A point already decided: its text, tag, sources and the decision (who, when, why)."""
    with st.container(key=f"rs-row-{r['id']}-{p['id']}"):
        st.markdown(html.escape(p["text"]))
        links = " · ".join(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(label)}</a>'
                           for label, url in research.source_labels(p["sources"]))
        st.markdown(f'<div class="rs-meta">{ui.tag(kind_label(p["kind"]))}'
                    + (f' <span class="rs-src">{ui.icon("link")} {links}</span>' if links else "") + "</div>",
                    unsafe_allow_html=True)
        when = show_date(date.fromisoformat(p["decided_on"])) if p.get("decided_on") else ""
        line = t(f"rs.decided.{'rejected' if p['status'] == 'rejected' else 'edited' if 'editing' in p['status'] else 'approved'}",
                 by=p.get("decided_by") or audit.SUPERVISOR, on=when)
        if p.get("reject_reason"):
            line += " " + t("rs.decided.reason", reason=p["reject_reason"])
        st.caption(line)
        if p in savable_points(r):
            knowledge_save_control(r, p)


def research_checklist(r: dict, locked: bool = False, save: bool = False):
    """One research brief as one list in one box (like the volunteer's): ticked = approve, "Edit" = edit then
    approve, unticked = reject with a reason; the volunteer's left-out points folded below; one button saves
    every decision (one audit entry per point) and, for a waiting draft, rebuilds the letter."""
    points = [p for p in r["points"] if p.get("kind") != "letter"]  # never the AI's own letter
    waiting = [p for p in points if p["status"] == research.WAITING]
    with st.container(border=True, key=f"rs-review-{r['id']}"):
        if waiting:
            st.warning(t("rs.volunteer_label"), icon=":material/pending:")
        st.caption(t("rs.sup_caption", by=r["asked_by"], on=show_date(date.fromisoformat(r["asked_at"][:10])),
                     found=r["sources_found"], official=r["sources_official"], dropped=len(r["dropped"])))
        if waiting and not locked:
            st.markdown(f'<p class="rs-list-head">{html.escape(t("rs.sup_list_head"))}</p>', unsafe_allow_html=True)
        kept = [p for p in waiting if p.get("volunteer") != research.LEFT_OUT]
        left = [p for p in waiting if p.get("volunteer") == research.LEFT_OUT]
        for p in kept:
            research_row(r, p, locked)
        if left:
            with st.expander(t("rs.sup_left_title", n=len(left)), icon=":material/remove_done:"):
                for p in left:
                    research_row(r, p, locked)
        for p in [p for p in points if p["status"] != research.WAITING]:
            decided_row(r, p)
        if r["dropped"]:
            with st.expander(f"{t('rs.dropped')} ({len(r['dropped'])})"):
                for d in r["dropped"]:
                    st.markdown(f"- {html.escape(d['text'][:200])} _({d['reason']})_")
        if not waiting:
            return
        if locked:
            why_disabled(t("ui.sup.own_draft"))
            return
        approved, rejected, undecided, problems = rs_checklist_state(r, waiting)
        nothing = not (approved or rejected)
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key=f"rs-buttons-{r['id']}"):
            if save:  # no drafts waiting: the decisions are saved here (with drafts, they are applied in Step 3)
                st.button(t("rs.save_all_no_letter", a=approved, r=rejected, u=undecided), key=f"rs-save-{r['id']}",
                          type="primary", icon=":material/task_alt:", disabled=bool(problems) or nothing,
                          on_click=save_research_checklist, args=(r["id"],))
            if kept:  # only the points in the list (not those the volunteer left out)
                st.button(t("rs.approve_all", n=len(kept)), key=f"rs-all-{r['id']}", icon=":material/done_all:",
                          on_click=approve_all_points, args=(r["id"], save))
        for problem in problems or ([t("why.rs_nothing_to_save")] if nothing and save else []):
            why_disabled(problem)


def save_research_checklist(research_id: str):
    """"Save point decisions" (a case with no drafts waiting): every point decided on screen is saved (with the
    supervisor's name and the date); points not decided stay for later."""
    case_id = research_id.rsplit(".r", 1)[0]
    if own_work(case_id):  # checked again on saving, not only on screen
        st.session_state["supervisor_flash"] = t("ui.sup.own_draft")
        return
    try:
        save_point_decisions(case_id)
    except (research.ResearchFailed, storage.StorageError, ValueError) as err:
        st.session_state["supervisor_flash"] = str(err)
        return
    a, r, u = point_counts(case_id)
    st.session_state["supervisor_flash_info"] = t("rs.saved_all_no_letter", a=a, r=r, u=u)


def approve_all_points(research_id: str, save: bool):
    """"Approve all points": every point in the list (the points the volunteer kept) is ticked; with no drafts
    waiting they are also saved (with the supervisor's name and the date), otherwise Step 3 applies them.
    A point naming a replaced law is left until it is edited to the current law."""
    case_id = research_id.rsplit(".r", 1)[0]
    if own_work(case_id):
        st.session_state["supervisor_flash"] = t("ui.sup.own_draft")
        return
    record = research.load(research_id)
    for p in record["points"]:
        if p.get("kind") != "letter" and p["status"] == research.WAITING and p.get("volunteer") != research.LEFT_OUT:
            st.session_state[f"rsx-{research_id}-{p['id']}"] = True
    if not save:
        return
    try:
        skipped = save_point_decisions(case_id, approve_all=True)
    except (research.ResearchFailed, storage.StorageError, ValueError) as err:
        st.session_state["supervisor_flash"] = str(err)
        return
    a, r, u = point_counts(case_id)
    st.session_state["supervisor_flash_info"] = t("rs.saved_all_no_letter", a=a, r=r, u=u) \
        + (" " + t("rs.all_skipped", n=skipped) if skipped else "")


def research_only_cases() -> list:
    """Cases with research points still to decide and no draft waiting (no drafts sent yet, or drafts
    already approved with points left for later). Drafts sent back are with the volunteer."""
    with_draft = {r["id"] for r in store.list_pending() + store.list_pending(status=store.SENT_BACK)}
    return list(dict.fromkeys(r["case_id"] for r in research.waiting() if r["case_id"] not in with_draft))


def research_review_box():
    """Decided research (no draft waiting) whose approved points can still be saved to our verified files."""
    with_draft = {r["id"] for r in store.list_pending() + store.list_pending(status=store.SENT_BACK)}
    later = set(research_only_cases())
    decided = [r for r in research.all_records()
               if r["status"] != research.WAITING and r["case_id"] not in with_draft | later and savable_points(r)]
    for r in decided:
        with st.expander(t("rs.sup_row", case_id=r["case_id"], state=r["state"], issue=r["issue"]),
                         icon=":material/travel_explore:"):
            for p in savable_points(r):
                decided_row(r, p)


def savable_points(r: dict) -> list:
    """Approved points not yet saved to our verified files."""
    return [p for p in r["points"] if p.get("kind") != "letter" and p["status"].startswith("approved")
            and not p.get("knowledge_id")]


def knowledge_save_control(r: dict, p: dict):
    """Inside the approved point's own card: "Save to our verified files", only after a lawyer has checked
    it (saved with lawyer_checked = no)."""
    with st.expander(t("rs.k_save"), icon=":material/bookmark_add:"):
        st.caption(t("rs.k_lawyer_first"))
        st.text_input(t("rs.k_heading"), key=f"rsk-h-{r['id']}-{p['id']}",
                      value=f"{r['state']}: {research.KINDS[p['kind']].lower()} for {r['issue'][:60]}")
        st.text_input(t("rs.k_words"), key=f"rsk-w-{r['id']}-{p['id']}", value=", ".join(research.keywords(r["issue"])))
        st.button(t("rs.k_save"), key=f"rsk-{r['id']}-{p['id']}", type="primary",
                  on_click=save_research_knowledge, args=(r["id"], p["id"]))


def knowledge_added_box():
    entries = research.learned()
    if not entries:
        return
    with st.expander(t("rs.k_title", n=len(entries)), icon=":material/library_books:"):
        st.caption(t("rs.k_export_caption"))
        for e in entries:
            approved = t("rs.approved_by", name=research.approved_by(e), date=show_stamp(e.get("approved_on") or e["checked"]))
            st.markdown(f"- **{html.escape(e['heading'])}** ({e['state']}) · {ui.tag(approved)}  \n"
                        f"  {html.escape(e['body'][:300])}  \n  _Source: {html.escape(e['source'])} ({e['link']})_",
                        unsafe_allow_html=True)
        st.download_button(t("rs.k_export"), research.export_markdown(), file_name="research_approved.md",
                           mime="text/markdown", key="rsk-export", icon=":material/download:")


def mark_reviewed(case_id: str):
    try:
        tracker.mark_reviewed(case_id)
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state["supervisor_flash"] = str(err)
        return
    st.session_state["supervisor_flash"] = t("sup.reviewed", case_id=case_id)


def changed_after_approval_box():
    """Approved cases a volunteer changed: the changes, then "Mark changes as reviewed"."""
    records = tracker.needs_review()
    if not records:
        return
    st.subheader(t("sup.changed_title", n=len(records)))
    for record in records:
        r = record["review_needed"]
        with st.expander(t("sup.changed_row", case_id=record["id"], v=r["version"], by=r["by"], on=show_stamp(r["since"][:10])),
                         expanded=True, icon=":material/history:"):
            case_file_view(record["id"], record, editable=False)
            st.button(t("sup.mark_reviewed"), key=f"reviewed-{record['id']}", type="primary",
                      icon=":material/task_alt:", on_click=mark_reviewed, args=(record["id"],))


def delete_selected_case():
    case_id = st.session_state.get("del-case")
    if (st.session_state.get("del-confirm") or "").strip() != "DELETE":
        st.session_state["del-msg"] = ("error", t("del.need_confirm"))
        return
    try:
        store.delete_case(case_id, by=supervisor_name())
    except ValueError as err:
        st.session_state["del-msg"] = ("error", str(err))
        return
    st.session_state["del-msg"] = ("ok", t("del.done", case_id=case_id))
    st.session_state["del-confirm"] = ""
    st.session_state["del-case"] = None


def delete_case_box():
    with st.expander(t("del.title")):
        st.caption(t("del.caption"))
        # every case at any stage, intake in progress included (not only those sent or approved)
        rows = {r["id"]: r for r in tracker.rows()}
        cases = sorted(rows, reverse=True)
        st.selectbox(t("del.case"), cases, index=None, key="del-case",
                     format_func=lambda c: " · ".join(x for x in (rows[c].get("code"), c, status_text(rows[c]["status"]))
                                                      if x))
        st.text_input(t("del.confirm"), key="del-confirm")
        st.button(t("del.button"), key="del-go", on_click=delete_selected_case,
                  disabled=not st.session_state.get("del-case"))
        if not st.session_state.get("del-case"):
            why_disabled(t("why.del_case"))
        msg = st.session_state.pop("del-msg", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


def facts_from_tracker(case: dict) -> "general.GeneralFacts | None":
    """A general case with no drafts sent: its facts rebuilt from the tracker record (the checked story lines,
    the problem, the papers, the yes/no facts and answers), the same way "Continue a case" rebuilds them."""
    if case.get("case_type") != general.CASE_TYPE:
        return None
    values = tracker.known_for_form(case)
    reading = general.GeneralReading(what_happened=list(case.get("summary", [])),
                                     issues=[tuple(i) for i in case.get("issues", [])],
                                     documents_held=list(case.get("documents_held", [])), facts=dict(values))
    missing = general.check_eligibility(values).missing
    return general.build_facts(reading, [tuple(a) for a in case.get("answers", [])],
                               [general.ELIGIBILITY_QUESTIONS[m] for m in missing if m in general.ELIGIBILITY_QUESTIONS],
                               dict(values), date.today())


def supervisor_case_cards(record: dict, g: "general.GeneralFacts | None" = None):
    """The same case cards the volunteer saw in step 3 (At a glance, Facts, Timeline, Documents, Free
    legal aid, For the lawyer, Next steps), rebuilt from the saved facts by the same code (g: facts rebuilt
    from the tracker, for a case with no drafts sent)."""
    if g is None and (record.get("case_type") != general.CASE_TYPE or not record.get("facts")):
        return
    try:
        g = g or general.GeneralFacts.from_dict(record["facts"])
        approved = research.approved_points(record["id"])
        g.research = research.items_for_summary(record["id"], g.facts.get("state"),
                                                [n for _, n in g.issues]) if g.issues else []
        case_cards(g, general.check_eligibility(g.facts), approved, casework.problem_type(g), code(), case_for=record["id"])
    except (KeyError, TypeError, ValueError, storage.StorageError):
        st.caption(t("sup.cards_unavailable"))


def own_work(case_id: str, record: "dict | None" = None) -> bool:
    """True when the signed-in supervisor sent this case's draft or asked for its research (names compared
    without case, spaces or dots): someone else must decide it, points included."""
    name = supervisor_name()
    if not name:
        return False
    if record is None:
        try:
            record = store.get_pending(case_id)
        except Exception:  # no waiting draft
            record = {}
    if record and store.sent_this(record, name):
        return True
    try:
        return any(store.same_person(name, r.get("asked_by", "")) for r in research.for_case(case_id))
    except storage.StorageError:
        return False


# ---------- the Supervisor page: "Waiting for you", one case open at a time, in three steps ----------

DRAFT_TAB_ORDER = ["summary", "s479", "letter", "application"]


def draft_kind(part: str) -> str:
    """Which draft a part of the bundle is: "letter", "application", "s479" (the Section 479 note) or "summary"."""
    if any(m in part for m in store.LETTER_MARKERS):
        return "letter"
    if "APPLICATION FOR FREE LEGAL SERVICES" in part or "मुफ़्त क़ानूनी सेवाओं के लिए आवेदन" in part:
        return "application"
    if "Section 479 of the Bharatiya" in part or "धारा 479 के तहत रिहाई" in part:
        return "s479"
    return "summary"


def waiting_rows() -> list:
    """Every case waiting for the supervisor, oldest first: drafts sent for review, and cases with research
    points to decide but no draft waiting. Each kind of record is read once (on the cloud every read is a
    network call). Each row: id, code, kind, volunteer, date, whether drafts were sent, and its chips."""
    pending = store.list_pending()
    with_draft = {r["id"] for r in pending + store.list_pending(status=store.SENT_BACK)}
    briefs = {}
    for r in research.all_records():
        briefs.setdefault(r["case_id"], []).append(r)
    rows = [{"id": record["id"], "pending": record, "kind": record.get("case_type", ""),
             "by": record.get("resent_by") or record.get("sent_by", ""), "when": record.get("submitted", "")}
            for record in pending]
    for case_id in dict.fromkeys(r["case_id"] for r in research.all_records() if r.get("status") == research.WAITING):
        if case_id in with_draft:
            continue  # drafts waiting (already a row), or sent back to the volunteer
        waiting = [r for r in briefs[case_id] if r["status"] == research.WAITING]
        rows.append({"id": case_id, "pending": None, "kind": "", "by": waiting[0]["asked_by"],
                     "when": waiting[0]["asked_at"], "approved_before": case_drafts_approved(case_id)})
    for row in rows:
        case = tracker.load(row["id"]) or {}
        row["code"] = case.get("code", "")
        row["kind"] = row["kind"] or case.get("case_type", "")
        row["points"] = sum(p["status"] == research.WAITING and p.get("kind") != "letter"
                            for r in briefs.get(row["id"], []) for p in r["points"])
        row["chips"] = waiting_chips(row)
    return sorted(rows, key=lambda r: r["when"])


def waiting_chips(row: dict) -> list:
    """What needs doing, as short chips: "3 research points", "Drafts ready", "Sent with 4 items not ticked",
    "Research only — no drafts yet" (or "Drafts already approved")."""
    chips = [("waiting", t("sup.chip.points", n=row["points"]))] if row["points"] else []
    record = row["pending"]
    if record:
        chips.append(("approved", t("sup.chip.drafts")))
        unticked = [r for r in record.get("readiness") or [] if r["key"] != "send_reason"
                    and r.get("note") == readiness.NOT_TICKED]
        if unticked:
            chips.append(("sent-back", t("sup.chip.unticked", n=len(unticked))))
    else:
        chips.append(("intake", t("sup.chip.approved_before" if row.get("approved_before") else "sup.chip.research_only")))
    return chips


def case_drafts_approved(case_id: str) -> bool:
    try:
        return tracker.status_of(case_id) in tracker.APPROVED_STATUSES + (tracker.CHANGED, tracker.CLOSED)
    except (ValueError, tracker.TrackerError, storage.StorageError):
        return False


def open_case(case_id: str):
    st.session_state["sup-open"] = case_id
    st.session_state.pop("sup-closed", None)


def close_case_view():
    """"Close this case": back to the list, with no case open until one is opened again."""
    st.session_state["sup-closed"] = True
    st.session_state.pop("sup-open", None)


def waiting_list(rows: list) -> str:
    """The compact list at the top; returns the id of the case open below it (the first one if none chosen,
    None after "Close this case")."""
    ids = [r["id"] for r in rows]
    current = st.session_state.get("sup-open")
    current = current if current in ids else None if st.session_state.get("sup-closed") else ids[0]
    e = html.escape
    with st.container(key="sup-list"):
        for row in rows:
            here = row["id"] == current
            with st.container(key=f"sup-row-{row['id']}", horizontal=True, vertical_alignment="center", gap="small"):
                when = show_stamp(row["when"][:10]) if row["when"] else ""
                head = (f"<b>{e(row['code'] or row['id'])}</b> · {e(case_type_label(row['kind']))}"
                        + (f" · {e(row['by'])}" if row["by"] else "") + (f" · {e(when)}" if when else ""))
                chips = " ".join(ui.chip(kind, text) for kind, text in row["chips"])
                st.markdown(f'<div class="sup-row{" current" if here else ""}"><div class="sup-row-head">{head}</div>'
                            f'<div class="sup-row-chips">{chips}</div></div>', unsafe_allow_html=True)
                st.button(t("sup.opened") if here else t("sup.open"), key=f"sup-open-{row['id']}",
                          type="secondary" if here else "primary", disabled=here, on_click=open_case, args=(row["id"],))
    return current


def letter_preview(case_id: str, record: dict) -> tuple:
    """The letter rebuilt from the ticks on screen: the saved approved points plus the ticked ones (never a point
    not decided or rejected), the same way it is rebuilt on approval. (letter text or "", points not decided)."""
    briefs = research.for_case(case_id)
    if record.get("case_type") != general.CASE_TYPE or not briefs:
        return "", 0
    approved, not_decided = list(research.approved_points(case_id)), 0
    for r in briefs:
        for p in [p for p in r["points"] if p.get("kind") != "letter" and p["status"] == research.WAITING]:
            if rs_state(r, p) == "approve":
                approved.append({"kind": p["kind"], "text": rs_edited(r, p) or p["text"], "sources": p["sources"],
                                 "approved_on": date.today().isoformat(), "approved_by": supervisor_name()})
            elif rs_state(r, p) != "reject":
                not_decided += 1
    g = general.GeneralFacts.from_dict(record["facts"])
    code_, model = record.get("draft_lang", "en"), record.get("ai_model")
    if not approved:
        return casework.facts_only_letter(g, briefs[-1]["issue"], model, code_, not_decided), not_decided
    return casework.complaint_letter(g, approved, briefs[-1]["issue"], model, code_, not_decided), not_decided


def set_mode(case_id: str, mode: str):
    st.session_state[f"sup-mode-{case_id}"] = mode


def open_edit(case_id: str):
    """"Edit then approve": with research, the point decisions are saved and the letter rebuilt first; then the
    edit box opens with the rebuilt drafts."""
    if research.for_case(case_id):
        rebuild_for_edit(case_id)
        if st.session_state.get(f"decide-err-{case_id}"):
            return
    st.session_state.pop(f"edit-{case_id}", None)
    set_mode(case_id, "edit")


def review_open_case(row: dict):
    """One case in three steps: 1 Understand the case, 2 Check the research points (if any), 3 Decide on the drafts."""
    case_id, record = row["id"], row["pending"]
    own = own_work(case_id, record)
    with st.container(border=True, key=f"review-{case_id}"):  # the open case, in one box
        when = show_stamp(row["when"]) if row["when"] else ""
        head = t("ui.sup.case_head", case_id=case_id, slip=row.get("code") or "-", kind=case_type_label(row["kind"]),
                 by=row["by"] or "-")
        if not record:  # research run, drafts not sent (or approved earlier)
            head += " · " + t("sup.head_approved_before" if row.get("approved_before") else "sup.head_no_drafts")
        with st.container(key=f"sup-head-{case_id}", horizontal=True, vertical_alignment="top", gap="small"):
            st.markdown(f'<h3 class="sup-case-head">{html.escape(head)}</h3>', unsafe_allow_html=True)
            st.button(t("sup.close_case"), key=f"sup-close-{case_id}", type="tertiary", icon=":material/close:",
                      on_click=close_case_view)
        if own:  # first, before anything can be decided: no tick boxes and no decision buttons below
            st.error(t("ui.sup.own_draft"), icon=":material/block:")
        for h in (record or {}).get("history", []):
            st.caption(t("ui.sup.resent", when=show_stamp(h["resent"]), reason=h["sent_back_reason"]))

        # Step 1 · Understand the case
        st.markdown(ui.step_band(1, t("sup.step1"), "now", ""), unsafe_allow_html=True)
        if when:  # the date and time: when the drafts were sent, or when the research was run
            st.caption(t("sup.sent_line" if record else "sup.research_line", when=when))
        with st.container(border=True, key=f"sup-understand-{case_id}"):
            if record and record.get("case_type") == general.CASE_TYPE:
                supervisor_case_cards(record)
            elif record:
                st.caption(t("sup.u_cards"))
            else:  # no drafts sent: the cards from the case's tracker record, and what is still missing
                case = tracker.load(case_id) or {}
                g = facts_from_tracker(case)
                if g:
                    supervisor_case_cards({"id": case_id}, g)
                    if g.still_to_ask:
                        st.markdown(f"**{html.escape(t('sup.still_missing'))}**  \n"
                                    + "  \n".join(f"- {html.escape(q)}" for q in g.still_to_ask))
                st.caption(t("sup.drafts_approved_before" if row.get("approved_before") else "sup.no_drafts_line"))
            rows = [r for r in (record or {}).get("readiness") or [] if r["key"] != "send_reason"]
            unticked = [r for r in rows if r.get("note") == readiness.NOT_TICKED]
            reason = next((r["note"] for r in (record or {}).get("readiness") or [] if r["key"] == "send_reason"), "")
            if unticked:  # the volunteer's "sent anyway" reason and the unticked items, once
                st.warning(t("ready.sup_unticked", items="; ".join(t("ready." + r["key"]) for r in unticked))
                           + (" " + t("ready.sup_reason", reason=reason) if reason else ""), icon=":material/rule:")
        if record and record.get("ledger"):
            ledger_box(record["ledger"])
        audit_record = audit.read_record(case_id)
        agent_did_card(audit_record, f"sup-{case_id}")
        with st.expander(t("ui.sup.audit_one")):
            if audit_record:
                audit_ai_summary(audit_record, (record or {}).get("facts"))
                history_table(audit_record, f"hist-{case_id}")
            else:
                st.caption(t("ui.sup.no_audit_one"))

        # Step 2 · Check the research points (only if the case has research)
        briefs = [r for r in research.for_case(case_id) if r["status"] == research.WAITING or savable_points(r)]
        if briefs:
            st.markdown(ui.step_band(2, t("sup.step2"), "now", ""), unsafe_allow_html=True)
            st.caption(t("sup.step2_note" if record else "sup.step2_note_no_drafts"))
            for r in briefs:
                research_checklist(r, own, save=record is None)
        if not record:  # no drafts sent: no step 3
            return

        # Step 3 · Decide on the drafts
        st.markdown(ui.step_band(3 if briefs else 2, t("sup.step3"), "now", ""), unsafe_allow_html=True)
        decide_on_drafts(case_id, record, own, bool(research.for_case(case_id)))


def decide_on_drafts(case_id: str, record: dict, own: bool, has_points: bool):
    """The drafts as tabs (the letter rebuilt from the ticks on screen), then Approve drafts · Edit then approve ·
    Send back to the volunteer."""
    parts = [p.strip() for p in casework.split_bundle(record["draft"])]
    kinds = [draft_kind(p) for p in parts]
    letter, not_decided = letter_preview(case_id, record) if has_points else ("", 0)
    if letter and "letter" not in kinds:  # the letter is added from the approved points on approval
        parts.append(letter)
        kinds.append("letter")
    order = sorted(range(len(parts)), key=lambda i: DRAFT_TAB_ORDER.index(kinds[i]))
    tabs = st.tabs([t(f"sup.tab.{kinds[i]}") for i in order])
    for tab, i in zip(tabs, order):
        with tab:
            text = letter if kinds[i] == "letter" and letter else parts[i]
            if kinds[i] == "letter" and not_decided:
                st.caption(t("sup.not_in_letter", n=not_decided))
            document_view(text.strip(), f"sup-{case_id}-{kinds[i]}", f"{case_id} {t('sup.tab.' + kinds[i])}")
    if own:
        return
    busy = bool(st.session_state.get(f"deciding-{case_id}"))  # one click only
    problems = case_point_problems(case_id) if has_points else []
    if has_points:
        st.caption(approve_note(case_id))
    with st.container(key=f"sup-decide-{case_id}", horizontal=True, gap="small"):
        st.button(t("sup.approve_drafts"), key=f"approve-{case_id}", type="primary", icon=":material/task_alt:",
                  disabled=busy or bool(problems), on_click=decide, args=(case_id, "approve"))
        st.button(t("sup.edit_then_approve"), key=f"edit-open-{case_id}", icon=":material/edit:",
                  disabled=busy or bool(problems), on_click=open_edit, args=(case_id,))
        st.button(t("sup.send_back_open"), key=f"back-open-{case_id}", icon=":material/undo:", disabled=busy,
                  on_click=set_mode, args=(case_id, "back"))
    for why in problems or ([t("why.busy")] if busy else []):
        why_disabled(why)
    mode = st.session_state.get(f"sup-mode-{case_id}")
    if mode == "edit":
        st.text_area(t("ui.sup.edit"), value=record["draft"], height=500, key=f"edit-{case_id}")
        st.caption(t("ui.sup.no_personal"))
        st.button(t("ui.sup.save_approve"), type="primary", key=f"edit-approve-{case_id}", disabled=busy,
                  on_click=decide, args=(case_id, "edit"))
    elif mode == "back":  # at any time, even before the points are decided
        st.text_area(t("ui.sup.reason"), key=f"reason-{case_id}")
        if any(r["status"] == research.WAITING for r in research.for_case(case_id)):
            st.caption(t("ui.sup.points_go_back"))
        st.button(t("sup.send_back"), key=f"reject-{case_id}", type="primary", icon=":material/undo:", disabled=busy,
                  on_click=decide, args=(case_id, "send back"))
    err = st.session_state.pop(f"decide-err-{case_id}", None)
    if err:
        st.error(err)


def approve_note(case_id: str) -> str:
    """What "Approve and save" will do with the research points, from the ticks on screen."""
    counts = [0, 0, 0]
    for r in research.for_case(case_id):
        waiting = [p for p in r["points"] if p.get("kind") != "letter" and p["status"] == research.WAITING]
        a, rj, u, _ = rs_checklist_state(r, waiting)
        counts = [counts[0] + a, counts[1] + rj, counts[2] + u]
    done = point_counts(case_id)
    return t("ui.sup.approve_note", a=counts[0] + done[0], r=counts[1] + done[1], u=counts[2])


def rebuild_for_edit(case_id: str):
    """"Edit then approve" with research: save the point decisions and rebuild the letter first; the edit box
    then holds the rebuilt drafts."""
    if own_work(case_id):
        st.session_state[f"decide-err-{case_id}"] = t("ui.sup.own_draft")
        return
    try:
        save_point_decisions(case_id)
    except (research.ResearchFailed, storage.StorageError, ValueError) as err:
        st.session_state[f"decide-err-{case_id}"] = str(err)
        return
    add_letter_to_pending(case_id)
    st.session_state[f"rebuilt-{case_id}"] = True
    st.session_state.pop(f"edit-{case_id}", None)  # the edit box starts from the rebuilt drafts


def points_note(case_id: str) -> str:
    """For the drafts' one audit entry: "3 points approved, 1 rejected, 2 not decided" ("" with no research)."""
    if not research.for_case(case_id):
        return ""
    a, r, u = point_counts(case_id)
    return f"{a} point{'' if a == 1 else 's'} approved, {r} rejected, {u} not decided"


def decide(case_id: str, kind: str):
    """Approve, edit-then-approve or send back, on the first click; the button is disabled from then on.
    A case decided in the meantime (a double click, or another supervisor) shows a calm notice."""
    get = st.session_state.get
    if own_work(case_id):  # checked again on saving, not only on screen
        st.session_state[f"decide-err-{case_id}"] = t("ui.sup.own_draft")
        return
    if kind == "approve" and research.for_case(case_id):  # one click: the point decisions on screen are saved,
        try:                                                # the letter is rebuilt from the approved points only
            save_point_decisions(case_id)
        except (research.ResearchFailed, storage.StorageError, ValueError) as err:
            st.session_state[f"decide-err-{case_id}"] = str(err)
            return
        add_letter_to_pending(case_id)
    st.session_state[f"deciding-{case_id}"] = True
    try:
        if kind == "approve":
            store.approve(case_id, by=supervisor_name(), note=points_note(case_id))
            st.session_state["supervisor_flash"] = t("ui.sup.approved", case_id=case_id)
        elif kind == "edit":
            store.approve(case_id, edited_text=get(f"edit-{case_id}"), by=supervisor_name(), note=points_note(case_id))
            st.session_state["supervisor_flash"] = t("ui.sup.edited_approved", case_id=case_id)
        else:
            store.reject(case_id, get(f"reason-{case_id}") or "", by=supervisor_name())
            st.session_state["supervisor_flash"] = t("ui.sup.sent_back", case_id=case_id)
    except store.AlreadyDecided:
        st.session_state["supervisor_flash_info"] = t("ui.sup.already_decided", case_id=case_id)
    except store.OwnDraft:
        st.session_state[f"decide-err-{case_id}"] = t("ui.sup.own_draft")
    except ValueError as err:  # for example no reason given: the button works again
        st.session_state[f"deciding-{case_id}"] = False
        st.session_state[f"decide-err-{case_id}"] = str(err)
    else:  # decided: the case leaves "Waiting for you" and the next one in the list opens
        st.session_state.pop("sup-open", None)
        st.session_state.pop("sup-closed", None)
        st.session_state.pop(f"sup-mode-{case_id}", None)


# ---------- clinic sign-in, and the shared case tracker ----------
# One clinic passcode for volunteers (CLINIC_PASSCODE) and a separate supervisor password
# (SUPERVISOR_PASSWORD), both only in the host's secret settings / .streamlit/secrets.toml.

def clinic_passcode() -> str:
    return storage.setting("CLINIC_PASSCODE")


def clinic_name() -> str:
    return storage.setting("CLINIC_NAME") or t("slip.default_clinic")


def app_url() -> str:
    return storage.setting("APP_URL")


def who() -> str:
    """The volunteer's name or initials, saved with every action. Without a clinic passcode (practice
    on one computer) a stand-in is used if none was typed."""
    name = (st.session_state.get("volunteer") or "").strip()
    return name or ("" if clinic_passcode() else t("gate.no_name"))


def clinic_ok() -> bool:
    return not clinic_passcode() or bool(st.session_state.get("clinic_ok"))


def clinic_sign_in():
    typed = (st.session_state.get("gate-pass") or "").strip()  # spaces copied in by mistake are ignored
    name = (st.session_state.get("gate-name") or "").strip()
    keys = guard_keys("volunteer")
    if signin_guard.seconds_locked(keys):  # 5 wrong passcodes: wait 5 minutes
        st.session_state["gate-msg"] = t("gate.too_many")
        return
    if is_supervisor_password(typed) and not hmac.compare_digest(typed.encode(), clinic_passcode().strip().encode()):
        st.session_state.update(**{"gate-msg": t("gate.supervisor_here"), "gate-pass": ""})
        return
    if not name:
        st.session_state["gate-msg"] = t("gate.need_name")
        return
    if not hmac.compare_digest(typed.encode(), clinic_passcode().strip().encode()):
        signin_guard.failed(keys)
        st.session_state["gate-msg"] = t("gate.too_many") if signin_guard.seconds_locked(keys) else t("gate.wrong")
        return
    signin_guard.succeeded(keys)
    st.session_state.update(clinic_ok=True, volunteer=tracker.clean_text(name, 40), **{"gate-pass": ""})


def clinic_gate(screen: str = "New case"):
    """The volunteer sign-in. Its side panel says what the screen behind it is for: Case tracker has its
    own (signin.t1-t3); Current case and the rest use signin.v1-v3."""
    page_title(t("gate.title"), helplines=False)
    with signin_columns("t" if screen == "My cases" else "v"), st.container(key="signin-card"):
        practice_hint()
        st.caption(t("gate.caption"))
        with st.form("gate-form", enter_to_submit=True, border=False):  # Enter signs in
            st.text_input(t("gate.passcode"), type="password", key="gate-pass")
            st.text_input(t("gate.name"), key="gate-name", max_chars=40, help=t("gate.name_help"))
            st.form_submit_button(t("gate.go"), type="primary", key="gate-go", on_click=clinic_sign_in)
        msg = st.session_state.pop("gate-msg", None) or locked_message("volunteer")
        if msg:
            st.error(msg)


def new_case_side() -> str:
    """Beside the New case card (laptop): today's camp, or "No camp started", and a short tip."""
    camp = st.session_state.get("camp_today")
    text = (t("nc.camp_value", village=camp["village"], district=camp["district"],
              date=show_date(date.fromisoformat(camp["on"]))) if camp else t("nc.no_camp"))
    return ui.new_case_side(t("nc.camp_label"), text, bool(camp), t("nc.tip"))


def volunteer_line(card: bool = False):
    """Who is acting, and today's camp (optional, tagged on new cases). card: the New case card, where
    every control is one full-width button and the camp itself is shown beside the card."""
    if clinic_passcode():
        st.markdown(f'<span class="who" title="{html.escape(t("gate.name_help"))}">'
                    f'{html.escape(t("gate.signed_in_short", name=who()))}</span>', unsafe_allow_html=True)
        if st.button(t("gate.sign_out"), key="gate-out", type="primary", icon=":material/logout:"):  # navy, filled:
            # Arushi's choice; not a step action, so the one-filled-button rule does not apply
            for key in ("clinic_ok", "volunteer", "case_id"):
                st.session_state.pop(key, None)
            st.rerun()
    else:
        st.text_input(t("gate.name"), key="volunteer", max_chars=40, help=t("gate.name_help"))
    camp_bar(card)


def open_camp_form():
    st.session_state["camp-open"] = True


def close_camp_form():
    st.session_state["camp-open"] = False


def save_todays_camp():
    get = st.session_state.get
    village = tracker.clean_text(get("camp-today-village") or "", 60)
    district = tracker.clean_text(get("camp-today-district") or "", 60)
    if not village or not district:
        st.session_state["camp-msg"] = t("camp.need")
        return
    on = get("camp-today-date") or date.today()
    st.session_state["camp_today"] = {"village": village, "district": district, "on": on.isoformat()}
    st.session_state["camp-open"] = False


def end_todays_camp():
    st.session_state.pop("camp_today", None)


def camp_bar(card: bool = False):
    """Today's camp: "Start today's camp" opens village, district and date; once saved, a small chip
    "Camp: <village>, <district> · <date>" with "End camp" (in the New case card: just "End camp", the
    camp itself is shown beside the card). New cases are tagged with it."""
    camp = st.session_state.get("camp_today")
    if camp and card:
        st.button(t("camp.end"), key="camp-end", icon=":material/close:", on_click=end_todays_camp)
    elif camp:
        with st.container(key="camp-row", horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(ui.chip("camp", t("camp.chip", village=camp["village"], district=camp["district"],
                                          date=show_date(date.fromisoformat(camp["on"])))), unsafe_allow_html=True)
            st.button(t("camp.end"), key="camp-end", type="tertiary", icon=":material/close:", on_click=end_todays_camp)
    elif st.session_state.get("camp-open"):
        with st.container(border=True, key="camp-form"):
            st.caption(t("camp.today_caption"))
            c1, c2, c3 = (st, st, st) if card else st.columns(3)  # the narrow card: one below the other
            c1.text_input(t("camp.village"), key="camp-today-village", max_chars=60)
            c2.text_input(t("camp.district"), key="camp-today-district", max_chars=60)
            c3.date_input(t("camp.date"), key="camp-today-date", format="DD/MM/YYYY", max_value=date.today(),
                          value=date.today())
            with st.container(horizontal=True, gap="small"):
                st.button(t("camp.save_today"), key="camp-save-today", type="primary", icon=":material/check:",
                          on_click=save_todays_camp)
                st.button(t("ui.cancel"), key="camp-cancel", on_click=close_camp_form)
            msg = st.session_state.pop("camp-msg", None)
            if msg:
                st.error(msg)
    else:
        st.button(t("camp.start"), key="camp-start", icon=":material/holiday_village:", on_click=open_camp_form)


def todays_camp():
    camp = st.session_state.get("camp_today")
    return {"village": camp["village"], "district": camp["district"], "on": date.fromisoformat(camp["on"])} \
        if camp else None


# "What the agent did": these audit events, in the order they happened
AGENT_EVENTS = {"story read": "story", "question asked": "question", "research asked": "research",
                "research failed": "research_failed", "research looked at by the volunteer": "points",
                "letter drafted": "letter", "drafts made": "drafts", audit.SENT: "sent", audit.RESENT: "sent",
                audit.APPROVED: "approved", store.SENT_BACK: "sent_back", "research point rejected": "point_rejected"}


def agent_line(e: dict, events: list) -> str:
    """One line of "What the agent did", in plain words: no "Tavily search" twice, no raw model id."""
    kind = AGENT_EVENTS[e["event"]]
    details = re.sub(r"\s*\(by .*\)\s*$", "", e.get("details", ""))  # who did it is in the audit table
    if kind == "research":
        num = lambda pattern: int((re.search(pattern, details) or [0, 0])[1])  # noqa: E731
        found, official = num(r"(\d+) search results"), num(r"(\d+) official")
        kept, dropped = num(r"(\d+) points? kept"), num(r"(\d+) dropped")
        sites = (re.search(r"sites searched: ([^(]+?)\s*$", details) or [None, ""])[1].strip()
        line = t("agent.research_line", sites=sites or "-", found=found, kept=kept,
                 official=t("agent.all_official") if found and found == official else t("agent.n_official", n=official))
        return line + ("; " + t("agent.left_out", n=dropped) if dropped else "")
    if kind == "sent":
        after = next((x for x in events[events.index(e) + 1:] if x.get("event") == "readiness when sent"), {})
        note = after.get("details", "")
        n = int((re.search(r"(\d+) items missing", note) or [0, 0])[1])
        if not n:
            return t("agent.sent_ready")
        return t("agent.sent_unticked", n=n) + ("; " + t("agent.reason_given") if "reason given" in note else "")
    if kind == "approved":
        return t("agent.approved_by", name=audit.who_did(e))
    if kind in ("sent_back", "point_rejected"):  # the reason after "reason: " or after the point's ": "
        reason = re.sub(r"^reason:\s*", "", details) if kind == "sent_back" else details.split(": ", 1)[-1]
        return t("agent.by_reason", name=audit.who_did(e), reason=reason)
    details = re.sub(r"model ([^;]+)", lambda m: "model " + (llm.display_model(m.group(1)) or m.group(1)), details)
    return agent_details(details)


def agent_did_card(record, key: str):
    """A collapsed card from the case's audit record: story read (model, numbers removed), questions
    asked, sites searched, research points kept and left out (with reasons), drafts made, with times."""
    events = [e for e in (record or {}).get("events", []) if e.get("event") in AGENT_EVENTS]
    with st.expander(t("agent.title", n=len(events)), icon=":material/smart_toy:"):
        st.caption(t("agent.caption"))
        if not events:
            st.caption(t("agent.none"))
            return
        lines = []
        for e in events:
            when = e.get("time", "")
            try:
                stamp = f"{show_date(date.fromisoformat(when[:10]))} {when[11:16]}"
            except ValueError:
                stamp = when[:16]
            details = agent_line(e, events)
            label = t("agent.ev." + AGENT_EVENTS[e["event"]])
            lines.append(f'<li><span class="agent-time">{html.escape(stamp)}</span> '
                         f'<b>{html.escape(label)}</b>' + (f" · {html.escape(details)}" if details else "") + "</li>")
        st.markdown(f'<ul class="agent-did">{"".join(lines)}</ul>', unsafe_allow_html=True)


# The audit record is kept in English; its fixed words are shown in the screen's language
AGENT_WORDS = [("(answered)", "agent.w.answered"), ("(don't know)", "agent.w.dont_know"), ("(not sure)", "agent.w.not_sure"),
               ("removed before sending: nothing", "agent.w.removed_none"), ("removed before sending:", "agent.w.removed"), ("questions planned", "agent.w.planned"),
               ("case summary; free legal aid application if needed", "agent.w.drafts"),
               ("facts only (no research point ticked)", "agent.w.facts_only")]


def agent_details(details: str) -> str:
    if code() == "en":
        return details
    for m in general.ELIGIBILITY_QUESTIONS:  # the app's own questions, as asked on screen
        details = details.replace(lang.t(f"elig.q.{m}", "en"), t(f"elig.q.{m}"))
    for english, key in AGENT_WORDS:
        details = details.replace(english, t(key))
    return details


def log_agent(event: str, details: str):
    """A step of the agent's work, in the case's audit record ("What the agent did"). Only once a case
    exists; never names (the details are the model, counts, questions and site names)."""
    case_id = st.session_state.get("case_id")
    if not case_id:
        return
    try:
        audit.add_event(case_id, event, audit.VOLUNTEER, f"{details} (by {who()})")
    except storage.StorageError:
        pass


def ensure_case(case_type: str) -> str:
    """The case number for the intake in progress: opened (with its slip code) the first time."""
    case_id = st.session_state.get("case_id")
    if case_id:
        return case_id
    record = tracker.open_case(case_type, who(), camp=todays_camp())
    st.session_state["case_id"] = record["id"]
    st.session_state["slip_new"] = True
    return record["id"]


def tracker_error(err: Exception):
    st.session_state["case-msg"] = ("error", str(err))


def clear_case():
    """Start another case: the current one stays saved in the tracker."""
    clear_general()
    clear_notes()
    for key in ("g_notes", "f_notes"):  # emptied, not just forgotten: the browser would show the old story again
        st.session_state[key] = ""
    for key in ("case_id", "slip_new", "case_opened", "sent", "case-msg"):
        st.session_state.pop(key, None)


def continue_case(where: str):
    st.session_state["continue_code"] = st.session_state.get(f"cont-code-{where}", "")
    st.session_state[f"cont-code-{where}"] = ""
    go("New case")


def open_existing(record: dict):
    """Open a case from its slip code. Known facts fill the questions, so they are never asked again."""
    clear_case()
    case_id = record["id"]
    st.session_state["case_id"] = case_id
    st.session_state["case_opened"] = True
    values = tracker.known_for_form(record)
    if record.get("case_type") == "Undertrial":
        st.session_state["case_type"] = "Undertrial"
        init_form()
        st.session_state["ai"] = {"reading": intake.Reading(values=dict(values)), "removed": {}, "skipped": set(),
                                  "values": dict(values), "model": record.get("ai_model"),
                                  "read_at": record.get("ai_read_at"), "translated_from": None, "translation": ""}
        if not intake.missing_facts(values):
            apply_to_form(values)
    else:
        st.session_state["case_type"] = ANY_CASE
        reading = general.GeneralReading(what_happened=list(record.get("summary", [])),
                                         issues=[tuple(i) for i in record.get("issues", [])],
                                         documents_held=list(record.get("documents_held", [])), facts=dict(values))
        _start_general(reading, record.get("ai_model"), {})
        st.session_state["gen"].update(answers=[tuple(a) for a in record.get("answers", [])],
                                       read_at=record.get("ai_read_at"))
    try:
        audit.add_event(case_id, "case continued", audit.VOLUNTEER, f"by {who()}")
    except storage.StorageError:
        pass


def open_by_code():
    """A code typed on Home or New case, or from the slip's QR code (?code=...)."""
    typed = st.session_state.pop("continue_code", None)
    if not typed:
        return
    try:
        record = tracker.find_by_code(typed)
        if record.get("closed"):  # read-only: it can't be continued until the supervisor reopens it
            st.session_state["case-msg"] = ("error", t("close.cannot_continue"))
            return
        open_existing(record)
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state["case-msg"] = ("error", str(err))


def continue_box(where: str):
    """Type the code from the case slip, or scan its QR code with the camera."""
    with st.expander(t("cont.title"), icon=":material/folder_open:",
                     expanded=bool(st.session_state.get(f"scan-open-{where}"))):
        st.text_input(t("cont.code"), key=f"cont-code-{where}", max_chars=12, placeholder="K7M2QX")
        with st.container(horizontal=True, gap="small"):
            st.button(t("cont.open"), key=f"cont-go-{where}", type="secondary", on_click=continue_case, args=(where,))
            st.button(t("home.scan"), key=f"scan-{where}", icon=":material/qr_code_scanner:", on_click=toggle,
                      args=(f"scan-open-{where}",))
        if st.session_state.get(f"scan-open-{where}"):
            scan_box(where)


def merge_into_case(case_id: str, facts: dict, source: str):
    try:
        tracker.merge_facts(case_id, facts, who(), source)
    except (tracker.TrackerError, storage.StorageError) as err:
        tracker_error(err)


def resolve_conflict(case_id: str, fact: str, keep: str):
    try:
        tracker.resolve(case_id, fact, keep, who())
    except (tracker.TrackerError, storage.StorageError) as err:
        tracker_error(err)
        return
    record = tracker.load(case_id)  # the questions and the form use the chosen value
    value = tracker.known_for_form(record).get(fact)
    if st.session_state.get("gen"):
        st.session_state["gen"]["facts"][fact] = value
    if st.session_state.get("ai"):
        st.session_state["ai"]["values"][fact] = value
        apply_to_form({fact: value})


def any_fact_label(fact: str) -> str:
    fact = {"section_typed": "section", "law_typed": "law"}.get(fact, fact)  # as typed on the form
    for key in (f"fact.{fact}", f"tfact.{fact}"):
        if key in lang.strings("en"):
            return t(key)
    return fact


def show_fact_value(fact: str, value) -> str:
    if fact in tracker.DATE_FACTS and isinstance(value, str):
        try:
            return show_date(date.fromisoformat(value))
        except ValueError:
            return value
    if fact == "annual_income" and isinstance(value, int):
        return f"{lang.inr(value)} " + t("tfact.per_year")
    return show_value(value)


def conflicts_block(case_id) -> bool:
    """A new value that contradicts an earlier one: "Cannot conclude yet" with both values, until a
    volunteer chooses. Returns True while any is open (no dates, summary or draft until then)."""
    record = tracker.load(case_id) if case_id else None
    open_ones = tracker.open_conflicts(record) if record else []
    for c in open_ones:
        fact = any_fact_label(c["fact"])
        earlier, new = c["earlier"], c["new"]
        st.error(t("abstain.title", reason=t("abstain.earlier_vs_new", fact=fact,
                                              earlier=show_fact_value(c["fact"], earlier["value"]),
                                              new=show_fact_value(c["fact"], new["value"]))))
        st.caption(t("abstain.earlier_vs_new_who", earlier_by=earlier["by"], earlier_on=show_stamp(earlier["on"][:10]),
                     new_by=new["by"], new_on=show_stamp(new["on"][:10])) + " " + t("abstain.needed.earlier_vs_new"))
        b1, b2 = st.columns(2)
        b1.button(t("abstain.keep_earlier", value=show_fact_value(c["fact"], earlier["value"])),
                  key=f"keep-earlier-{c['fact']}", on_click=resolve_conflict, args=(case_id, c["fact"], "earlier"))
        b2.button(t("abstain.use_new", value=show_fact_value(c["fact"], new["value"])),
                  key=f"keep-new-{c['fact']}", on_click=resolve_conflict, args=(case_id, c["fact"], "new"))
    return bool(open_ones)


# ----- the case slip -----

def slip_box(record: dict, expanded: bool = False):
    with st.expander(t("slip.title"), expanded=expanded):
        slip_content(record)


def slip_content(record: dict):
    if True:
        st.caption(t("slip.caption"))
        lines = tracker.slip_lines(record, clinic_name())
        qr = tracker.qr_png_data_uri(app_url(), record["code"])
        page = ui.slip_page(lines, qr, t("slip.print"), t("slip.save_image"))
        components.html(page, height=640)
        st.download_button(t("slip.download_print"), ui.slip_page(lines, qr, print_only=True),
                           file_name=f"case-slip-{record['code']}.html", mime="text/html",
                           key=f"slip-dl-{record['id']}")


# ----- the case file: summary, facts known, still missing, documents, next step, visits -----

def still_missing(record: dict) -> list:
    values = tracker.known_for_form(record)
    if record.get("case_type") == "Undertrial":
        return [fact_label(f) for f in intake.missing_facts(values)]
    return [t(f"elig.q.{m}") for m in general.check_eligibility(values).missing]


def next_step_words(step: str, tl_step) -> str:
    if tl_step:
        return step_title(tl_step)
    return lang.strings(code()).get(f"next:{step}", t(f"tr.next.{step}") if f"tr.next.{step}" in lang.strings("en") else step)


def show_change_value(field: str, value) -> str:
    if value in (None, ""):
        return t("ed.empty")
    if field == "next step date" and isinstance(value, str):
        return show_fact_value("custody_began", value)  # a date
    if field in ("note", "next step"):
        return str(value)
    return show_fact_value(field, value)


def change_field_label(field: str) -> str:
    return {"note": t("cf.notes"), "next step": t("ed.next"), "next step date": t("ed.next_due")}.get(
        field, any_fact_label(field))


def case_file_view(case_id: str, record: dict, editable: bool = True):
    """The case file: summary, facts known (with who added them), still missing, documents, next step,
    notes, visits and every change made. "Edit / make changes" opens the edit form."""
    e = html.escape
    status = tracker.status_of(case_id)
    if editable:
        st.button(t("cf.edit"), key=f"cf-edit-{case_id}", icon=":material/edit:", on_click=start_edit, args=(case_id,))
    if record.get("review_needed"):
        old = max((v["version"] for v in record.get("versions", [])), default=1)
        st.markdown(f'<div class="review-flag">{e(t("ed.review_banner", v=record["review_needed"]["version"], old=old))}'
                    f'</div>', unsafe_allow_html=True)
    out = [f'<h4>{e(t("cf.summary"))}</h4>']
    out.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in record["summary"]) + "</ul>" if record.get("summary")
               else f'<p class="case-sub">{e(t("cf.no_summary"))}</p>')
    out.append(f'<h4>{e(t("cf.facts"))}</h4>')
    facts = record.get("facts", {})
    out.append("<ul>" + "".join(
        f"<li>{e(any_fact_label(f))}: <b>{e(show_fact_value(f, x['value']))}</b> "
        f"{ui.tag(t('cf.added', on=show_stamp(x['on'][:10]), by=x['by']))}</li>" for f, x in facts.items()) + "</ul>"
        if facts else f'<p class="case-sub">{e(t("cf.no_facts"))}</p>')
    missing = still_missing(record)
    out.append(f'<h4>{e(t("cf.missing"))}</h4>')
    out.append("<ul>" + "".join(f"<li>{e(m)}</li>" for m in missing) + "</ul>" if missing
               else f'<p>{e(t("cf.nothing_missing"))}</p>')
    out.append(f'<h4>{e(t("cf.documents"))}</h4>')
    held = record.get("documents_held", [])
    if held:
        out.append(f'<p>{e(t("cf.held"))} {e(", ".join(held))}</p>')
    categories = [i[0] for i in record.get("issues", [])] or (
        ["arrest_or_custody"] if record.get("case_type") == "Undertrial" else ["other"])
    if record.get("case_type") == general.CASE_TYPE:  # the same list as the intake screen (one function)
        lists = [(None, casework.case_file_documents(record, code()), "")]
    else:
        lists = general.document_lists(categories, held, record.get("summary", []))
    for _, items, source in lists:
        if items:
            out.append(f'<p>{e(t("cf.to_collect"))} '
                       f'{e(", ".join(lang.strings(code()).get(f"doc:{x}", x) for x in items))}</p>')
            if source:
                out.append(f'<p class="case-sub"><em>{e(source)}</em></p>')
    step, due, tl_step = tracker.next_step(record, status, case_id)
    out.append(f'<h4>{e(t("ed.next"))}</h4><p>{e(next_step_words(step, tl_step))}'
               + (f" · {e(t('cf.due', due=show_date(date.fromisoformat(due))))}" if due else "") + "</p>")
    if record.get("next") and status == tracker.CHANGED:
        n = record["next"]
        out.append(f'<p class="case-sub">{e(n["step"])}'
                   + (f" · {e(t('cf.due', due=show_date(date.fromisoformat(n['due']))))}" if n.get("due") else "")
                   + f' {ui.tag(t("cf.added", on=show_stamp(n["on"][:10]), by=n["by"]))}</p>')
    if record.get("research_points"):
        out.append(f'<h4>{e(t("cf.research"))}</h4><ul>' + "".join(
            f"<li>{e(research.KINDS[p['kind']])}: {e(p['text'][:400])} "
            f"{ui.tag(casework.approved_text(p, code()))}<br><em>{e(research.source_line(p['sources']))}</em></li>"
            for p in record["research_points"]) + "</ul>")
    if record.get("notes"):
        out.append(f'<h4>{e(t("cf.notes"))}</h4><ul>' + "".join(
            f"<li>{e(n['text'])} {ui.tag(t('cf.added', on=show_stamp(n['on'][:10]), by=n['by']))}</li>"
            for n in reversed(record["notes"])) + "</ul>")
    out.append(f'<h4>{e(t("cf.visits"))}</h4>')
    visits = record.get("visits", [])
    if not visits:
        out.append(f'<p class="case-sub">{e(t("cf.no_visits"))}</p>')
    else:
        items = []
        for v in reversed(visits):
            parts = [f"<b>{e(show_date(date.fromisoformat(v['on'])))}</b> · {e(t('visit.how.' + v['how']))} "
                     f"{ui.tag(v['by'])}"]
            for key in ("learned", "done"):
                if v.get(key):
                    parts.append(f"{e(t('visit.' + key))}: {e(v[key])}")
            if v.get("next_step"):
                parts.append(f"{e(t('visit.next'))}: {e(v['next_step'])}"
                             + (f" ({e(show_date(date.fromisoformat(v['next_due'])))})" if v.get("next_due") else ""))
            items.append("<li>" + "<br>".join(parts) + "</li>")
        out.append("<ul>" + "".join(items) + "</ul>")
    if record.get("edits"):
        out.append(f'<h4>{e(t("ed.history"))}</h4><ul>' + "".join(
            f"<li>{e(change_field_label(c['field']))}: {e(show_change_value(c['field'], c['old']))} → "
            f"<b>{e(show_change_value(c['field'], c['new']))}</b> "
            f"{ui.tag(show_stamp(ed['time']) + ' · ' + ed['by'] + ' · ' + t('cf.version', v=ed.get('version', 1)))}</li>"
            for ed in reversed(record["edits"]) for c in ed["changes"]) + "</ul>")
    tags = []
    if record.get("camp"):
        tags.append(ui.tag(t("camp.tagged", camp=tracker.camp_label(record["camp"]))))
    tags.append(ui.tag(t("cf.last", by=record.get("last_by", ""), at=show_stamp(record.get("last_at") or ""))))
    out.append(f'<p style="margin-top:14px">{" ".join(tags)}</p>')
    st.markdown('<div class="cf">' + "".join(out) + "</div>", unsafe_allow_html=True)
    for c in tracker.open_conflicts(record):
        st.warning(t("cf.conflict", fact=any_fact_label(c["fact"])))


# ----- editing a case: "Edit / make changes" -> "Save changes" or "Cancel" -----

def start_edit(case_id: str):
    for key in [k for k in st.session_state.keys() if isinstance(k, str) and k.startswith(f"ed-{case_id}-")]:
        del st.session_state[key]
    st.session_state[f"editing-{case_id}"] = True
    st.session_state[f"open-{case_id}"] = True


def cancel_edit(case_id: str):
    st.session_state[f"editing-{case_id}"] = False


def save_edit(case_id: str):
    get = st.session_state.get
    record = tracker.load(case_id) or {}
    facts = {f: get(f"ed-{case_id}-{f}") for f in record.get("facts", {})}
    step = (get(f"ed-{case_id}-next") or "").strip()
    due = get(f"ed-{case_id}-due")
    step_changed = step != get(f"ed-{case_id}-next-shown", "") or due != get(f"ed-{case_id}-due-shown")
    try:
        changes = tracker.edit_case(case_id, who(), facts=facts, note=get(f"ed-{case_id}-note") or "",
                                    next_step=step if step_changed else None, next_due=due if step_changed else None)
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state[f"ed-msg-{case_id}"] = ("error", str(err))
        return
    record = tracker.load(case_id)
    st.session_state[f"editing-{case_id}"] = False
    st.session_state[f"saved-msg-{case_id}"] = (
        t("ed.saved_review", v=record["version"]) if record.get("review_needed") else t("ed.saved", n=len(changes)))


def fact_input(case_id: str, fact: str, value):
    key, label = f"ed-{case_id}-{fact}", any_fact_label(fact)
    if fact in tracker.DATE_FACTS:
        try:
            shown = date.fromisoformat(value) if isinstance(value, str) else value
        except ValueError:
            shown = None
        st.date_input(label, value=shown, key=key, format="DD/MM/YYYY", min_value=date(1950, 1, 1),
                      max_value=date.today())
    elif isinstance(value, bool):
        st.radio(label, [True, False], index=0 if value else 1, horizontal=True, key=key,
                 format_func=lambda v: t("ed.yes") if v else t("ed.no"))
    elif isinstance(value, int):
        st.number_input(label, value=value, step=1, key=key)
    elif isinstance(value, float):
        st.number_input(label, value=value, key=key)
    else:
        st.text_input(label, value="" if value is None else str(value), key=key, max_chars=300)


def edit_form(case_id: str, record: dict):
    status = tracker.status_of(case_id)
    with st.container(border=True, key=f"edit-box-{case_id}"):
        st.markdown(f'<div class="step-title" style="margin-top:0">{html.escape(t("ed.title", case_id=case_id))}</div>',
                    unsafe_allow_html=True)
        st.caption(t("ed.caption"))
        if status in tracker.APPROVED_STATUSES:
            st.warning(t("ed.approved_note"), icon=":material/history:")
        st.markdown(f"**{t('ed.facts')}**")
        facts = record.get("facts", {})
        if not facts:
            st.caption(t("ed.no_facts"))
        cols = st.columns(2)
        for i, (fact, entry) in enumerate(facts.items()):
            with cols[i % 2]:
                fact_input(case_id, fact, entry["value"])
        step, due, tl_step = tracker.next_step(record, status, case_id)
        shown = next_step_words(step, tl_step) if step else ""
        st.session_state[f"ed-{case_id}-next-shown"] = shown
        st.session_state[f"ed-{case_id}-due-shown"] = date.fromisoformat(due) if due else None
        c1, c2 = st.columns([2, 1])
        c1.text_input(t("ed.next"), value=shown, key=f"ed-{case_id}-next", max_chars=200)
        c2.date_input(t("ed.next_due"), value=date.fromisoformat(due) if due else None, key=f"ed-{case_id}-due",
                      format="DD/MM/YYYY", min_value=date.today() - timedelta(days=365))
        st.text_area(t("ed.note"), key=f"ed-{case_id}-note", max_chars=300, height=90)
        with st.container(horizontal=True, gap="small"):
            st.button(t("ed.save"), key=f"ed-save-{case_id}", type="primary", icon=":material/save:",
                      on_click=save_edit, args=(case_id,))
            st.button(t("ui.cancel"), key=f"ed-cancel-{case_id}", on_click=cancel_edit, args=(case_id,))
        msg = st.session_state.pop(f"ed-msg-{case_id}", None)
        if msg:
            st.error(msg[1])


def case_file_or_edit(case_id: str, record: dict, edit_button: bool = True):
    saved = st.session_state.pop(f"saved-msg-{case_id}", None)
    if saved:
        st.success(saved, icon=":material/check_circle:")
    if st.session_state.get(f"editing-{case_id}"):
        edit_form(case_id, record)
    else:
        case_file_view(case_id, record, editable=edit_button)


def save_visit(case_id: str):
    get = st.session_state.get
    try:
        tracker.add_visit(case_id, get(f"vis-on-{case_id}") or date.today(), who(), get(f"vis-how-{case_id}") or "",
                          learned=get(f"vis-learned-{case_id}") or "", done=get(f"vis-done-{case_id}") or "",
                          next_step=get(f"vis-next-{case_id}") or "", next_due=get(f"vis-due-{case_id}"))
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state[f"vis-msg-{case_id}"] = ("error", str(err))
        return
    for key in ("learned", "done", "next"):
        st.session_state[f"vis-{key}-{case_id}"] = ""
    st.session_state[f"vis-due-{case_id}"] = None
    st.session_state[f"vis-msg-{case_id}"] = ("ok", t("visit.saved"))


def visit_form(case_id: str):
    with st.expander(t("visit.title")):
        visit_content(case_id)


def visit_content(case_id: str):
    if True:
        st.caption(t("visit.caption"))
        c1, c2 = st.columns(2)
        c1.date_input(t("visit.on"), key=f"vis-on-{case_id}", value=date.today(), format="DD/MM/YYYY",
                      max_value=date.today())
        c2.selectbox(t("visit.how"), tracker.VISIT_WAYS, key=f"vis-how-{case_id}", format_func=option_text("visit.how."))
        st.text_area(t("visit.learned"), key=f"vis-learned-{case_id}", max_chars=300, height=80,
                     placeholder=t("visit.placeholder"))  # the no-names rule, inside each box
        st.text_area(t("visit.done"), key=f"vis-done-{case_id}", max_chars=300, height=80,
                     placeholder=t("visit.placeholder"))
        c3, c4 = st.columns([2, 1])
        c3.text_input(t("visit.next"), key=f"vis-next-{case_id}", max_chars=200, placeholder=t("visit.placeholder"))
        c4.date_input(t("visit.next_due"), key=f"vis-due-{case_id}", value=None, format="DD/MM/YYYY",
                      min_value=date.today() - timedelta(days=365))
        st.button(t("visit.save"), key=f"vis-save-{case_id}", on_click=save_visit, args=(case_id,), type="primary")
        msg = st.session_state.pop(f"vis-msg-{case_id}", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


def save_camp(case_id: str):
    get = st.session_state.get
    try:
        tracker.set_camp(case_id, get(f"camp-village-{case_id}") or "", get(f"camp-district-{case_id}") or "",
                         get(f"camp-date-{case_id}") or date.today(), who())
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state[f"camp-msg-{case_id}"] = ("error", str(err))
        return
    st.session_state[f"camp-msg-{case_id}"] = ("ok", t("camp.saved"))


def camp_form(case_id: str, record: dict):
    with st.expander(t("camp.title")):
        camp = record.get("camp") or {}
        c1, c2, c3 = st.columns(3)
        c1.text_input(t("camp.village"), key=f"camp-village-{case_id}", value=camp.get("village", ""), max_chars=60)
        c2.text_input(t("camp.district"), key=f"camp-district-{case_id}", value=camp.get("district", ""), max_chars=60)
        c3.date_input(t("camp.date"), key=f"camp-date-{case_id}", format="DD/MM/YYYY", max_value=date.today(),
                      value=date.fromisoformat(camp["date"]) if camp.get("date") else date.today())
        st.button(t("camp.save"), key=f"camp-save-{case_id}", on_click=save_camp, args=(case_id,))
        msg = st.session_state.pop(f"camp-msg-{case_id}", None)
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])


def case_tools(case_id: str, record: dict, file_open: bool = False, slip_open: bool = False):
    slip_box(record, expanded=slip_open)
    with st.expander(t("cf.title"), expanded=file_open or bool(st.session_state.get(f"editing-{case_id}")),
                     icon=":material/folder_open:"):
        case_file_or_edit(case_id, record)
    visit_form(case_id)


def current_case_panel():
    """On New case: the case in progress (number, code, slip, case file, visits)."""
    case_id = st.session_state.get("case_id")
    if not case_id:
        return
    record = tracker.load(case_id)
    if record is None:
        st.session_state.pop("case_id", None)
        return
    status = tracker.status_of(case_id)
    tab_key = f"case-tab-{case_id}"
    if st.session_state.pop("case_opened", False):
        st.session_state[tab_key] = "file"  # a continued case opens on its case file
    with st.container(border=True, key="case-panel"):
        # The code is what volunteers use, so it is large; the long case number is small and grey
        st.markdown(f'<div class="case-head"><span class="lbl">{html.escape(t("slip.code"))}</span>'
                    f'<span class="code">{html.escape(record["code"])}</span>{status_chip(status)}</div>'
                    f'<div class="case-id">{html.escape(t("ui.case_title", case_id=case_id))}</div>',
                    unsafe_allow_html=True)
        line = sent_status_line(case_id)
        if line:  # also after a reload: the case card shows where the draft is
            st.markdown(f'<p class="sent-status">{html.escape(line)}</p>', unsafe_allow_html=True)
        if st.session_state.pop("slip_new", False):
            st.success(t("slip.new_short", slip_code=record["code"]), icon=":material/qr_code_2:")
        if record.get("intake_finished") and record.get("next"):
            n = record["next"]
            st.success(t("intake.done", step=next_step_words(n["step"], None),
                         due=show_date(date.fromisoformat(n["due"])) if n.get("due") else "-"),
                       icon=":material/task_alt:")
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="case-actions"):
            current = st.session_state.get(tab_key)
            for option, icon in CASE_TABS:  # small quiet buttons; open one panel, press again to close it
                st.button(t(f"case.tab.{option}"), key=f"case-tab-{option}", icon=icon,
                          type="secondary" if current == option else "tertiary",
                          on_click=toggle_case_tab, args=(tab_key, option))
        tab = st.session_state.get(tab_key)
        if tab == "slip":
            slip_content(record)
        elif tab == "file":
            case_file_or_edit(case_id, record)
        elif tab == "visit":
            visit_content(case_id)


CASE_TABS = [("slip", ":material/qr_code_2:"), ("file", ":material/folder_open:"), ("visit", ":material/event_note:")]


def toggle_case_tab(tab_key: str, option: str):
    st.session_state[tab_key] = None if st.session_state.get(tab_key) == option else option


def finish_intake(case_id: str):
    try:
        sent = tracker.status_of(case_id) == store.WAITING  # already sent: the supervisor reviews next
        tracker.finish_intake(case_id, who(), next_step=tracker.NEXT_REVIEW if sent else "")
    except (tracker.TrackerError, storage.StorageError) as err:
        st.session_state["case-msg"] = ("error", str(err))


STATUS_CHIPS = {tracker.INTAKE: ("intake", "ui.status.intake"), store.WAITING: ("waiting", "ui.status.waiting"),
                tracker.INTAKE_DONE: ("intake-done", "ui.status.intake_done"),
                store.SENT_BACK: ("sent-back", "ui.status.sent_back"), store.APPROVED: ("approved", "ui.status.approved"),
                tracker.SUBMITTED: ("submitted", "ui.status.submitted"), tracker.CHANGED: ("changed", "ui.status.changed"),
                tracker.ACKNOWLEDGED: ("acknowledged", "ui.status.acknowledged"),
                tracker.CLOSED: ("closed", "ui.status.closed")}


def status_text(status: str) -> str:
    return t(STATUS_CHIPS[status][1])


def status_chip(status: str) -> str:
    return ui.chip(STATUS_CHIPS[status][0], status_text(status))


def next_step_text(row: dict) -> str:
    if row.get("step"):
        return step_title(row["step"])
    key = f"tr.next.{row['next_step']}"
    return t(key) if key in lang.strings("en") else row["next_step"]


# ---------- Home ----------

def keep_place_in_address(screen: str):
    """The screen (and, on New case, the open case number) in the page address, so switching language,
    reloading or a phone reconnecting keeps the volunteer where they were. Case numbers only, never names."""
    key = {**{s: k for s, k in NAV}, "Practice": "practice"}.get(screen, "home")
    if st.query_params.get("screen") != key:
        st.query_params["screen"] = key
    if screen != "Learn" and "guide" in st.query_params:  # the open guide belongs to the Learn page only
        del st.query_params["guide"]
    case_id = st.session_state.get("case_id") if screen == "New case" else None
    if case_id and st.query_params.get("case") != case_id:
        st.query_params["case"] = case_id
    elif not case_id and "case" in st.query_params:
        del st.query_params["case"]


def go(screen: str):
    st.session_state["screen"] = screen
    st.session_state["menu_open"] = False


def start_case():
    clear_case()  # the case in progress stays saved in the tracker
    go("New case")
    st.session_state["case_type"] = ANY_CASE


def ask_start_case():
    """"Start a case": with a case open, ask first (the open case stays saved in the tracker)."""
    st.session_state["menu_open"] = False
    if st.session_state.get("case_id"):
        st.session_state["leave_ask"] = True
    else:
        start_case()


def leave_case_box():
    if not st.session_state.get("leave_ask"):
        return
    with st.container(border=True, key="leave-box"):
        st.warning(t("nav.leave_q"), icon=":material/logout:")
        with st.container(horizontal=True, gap="small"):
            st.button(t("nav.leave_yes"), key="leave-yes", type="primary",
                      on_click=lambda: (st.session_state.pop("leave_ask", None), start_case()))
            st.button(t("nav.leave_no"), key="leave-no", on_click=lambda: st.session_state.pop("leave_ask", None))


def home_to_case(speak: bool):
    """Home's story box opens step 1 of New case, with the story carried over (and the mic open)."""
    story = (st.session_state.get("home_story") or "").strip()
    start_case()
    if story:
        for key in ("gen", "gen_error", "g_checked", "gen_sent"):
            st.session_state.pop(key, None)
        st.session_state["g_notes"] = story
        # Also held apart (in this browser session only, never saved), because the clinic sign-in may
        # come in between and the story box is not drawn while it shows.
        st.session_state["held_story"] = {"text": story, "lang": multilingual.detect_language(story)}
    if speak:
        st.session_state["g_audio-open"] = True


def toggle(flag: str, other: str = ""):
    st.session_state[flag] = not st.session_state.get(flag)
    if other:
        st.session_state[other] = False


def scan_box(where: str):
    """Scan the QR code on a case slip with the camera; the case opens by itself."""
    st.caption(t("scan.caption"))
    n = st.session_state.get(f"scan-n-{where}", 0)
    photo = st.camera_input(t("scan.camera"), key=f"scan-cam-{where}-{n}")
    if photo is None:
        return
    st.session_state[f"scan-n-{where}"] = n + 1  # a fresh camera next time
    try:
        found = tracker.read_qr(photo.getvalue())
    except tracker.TrackerError as err:
        st.error(str(err))
        return
    st.session_state["continue_code"] = found
    st.session_state[f"scan-open-{where}"] = False
    go("New case")
    st.rerun()


def home_screen():
    st.markdown(ui.hero(t("home.badge"), t("home.kicker"), t("home.lead"), t("home.sub"),  # the badge says the rest
                        name=t("app.name")), unsafe_allow_html=True)
    with st.container(key="storybox", horizontal=True, vertical_alignment="center", gap="small"):
        st.text_area(t("home.story_label"), key="home_story", height=68, placeholder=t("home.story_placeholder"),
                     label_visibility="collapsed")
        st.button(t("home.mic"), key="home-mic", icon=":material/mic:", on_click=home_to_case, args=(True,))
        st.button(t("home.go"), key="home-go", icon=":material/arrow_forward:", on_click=home_to_case, args=(False,))
    with st.container(key="heroactions", horizontal=True, gap="small"):
        st.button(t("home.start"), key="home-start", type="primary", icon=":material/note_add:", on_click=ask_start_case)
        st.button(t("home.continue"), key="home-continue", icon=":material/folder_open:",
                  on_click=toggle, args=("cont-open-home", "scan-open-home"))
        st.button(t("home.scan"), key="home-scan", icon=":material/qr_code_scanner:",
                  on_click=toggle, args=("scan-open-home", "cont-open-home"))
    if st.session_state.get("cont-open-home"):
        with st.container(key="continuebox", border=True):
            st.text_input(t("cont.code"), key="cont-code-home", max_chars=12, placeholder="K7M2QX")
            st.button(t("cont.open"), key="cont-go-home", type="primary", on_click=continue_case, args=("home",))
    if st.session_state.get("scan-open-home"):
        with st.container(key="scanbox", border=True):
            scan_box("home")
    st.markdown(ui.helpline("", t("home.helpline_danger"), t("home.helpline_aid")), unsafe_allow_html=True)  # the footer says "open source"

    st.markdown(ui.section("how-it-works", t("home.how_title"), t("home.how_h2"),
                           ui.how_cards([(t(f"home.how{i}_t"), t(f"home.how{i}_p")) for i in range(1, 6)])),
                unsafe_allow_html=True)
    st.markdown(ui.compare(
        {"eyebrow": t("home.today_t"), "title": t("home.today_h"), "chips": [t(f"home.today_c{i}") for i in range(1, 6)],
         "text": t("home.today_p")},
        {"eyebrow": t("home.raahi_t"), "title": t("home.raahi_h"),
         "rows": [(icon, t(f"home.raahi_f{i}_b"), t(f"home.raahi_f{i}")) for i, icon in enumerate(RAAHI_ICONS, 1)]}),
        unsafe_allow_html=True)
    st.markdown(ui.section("safety", t("home.safe_title"), t("home.safe_h2"), ui.safe_cards(
        [(SAFE_ICONS[i - 1], t(f"home.safe{i}_t"), t(f"home.safe{i}_p")) for i in range(1, 7)])),
        unsafe_allow_html=True)
    labels = {k: t(f"facts.{k}") for k in ("prev", "next", "pause", "play", "of", "source", "region")}
    with st.container(key="factsband"):  # full width navy band; the carousel runs in its own small page
        components.html(ui.facts_carousel(t("home.facts_title"), home.facts(code()), labels), height=380)
    st.markdown(ui.section("learn-basics", t("home.learn_title"), t("home.learn_h2"), "", extra="learn"),
                unsafe_allow_html=True)
    with st.container(key="learnlinks"):
        cols = st.columns(4, gap="medium")
        for i, col in enumerate(cols, 1):
            with col.container(key=f"learn-card-{i}"):
                ready = i == 4 or guides.content(guides.GUIDES[i - 1].key).ready
                st.markdown(ui.guide_card(LEARN_ICONS[i - 1], t(f"home.learn{i}"), t(f"home.learn{i}_p"),
                                          "" if ready else t("learn.coming_soon")), unsafe_allow_html=True)
                if i < 4 and ready:
                    st.button(t("home.learn_go"), key=f"home-learn-{i}", icon=":material/arrow_forward:",
                              on_click=open_guide, args=(guides.GUIDES[i - 1].key,))  # its own guide
                elif i == 4:  # the 4th item: Practice, public like Learn
                    st.button(t("home.eval_go"), key="nav-practice", type="primary", icon=":material/quiz:",
                              on_click=go, args=("Practice",))


LEARN_ICONS = ["volunteer_activism", "gavel", "phishing", "quiz"]
RAAHI_ICONS = ["qr_code_2", "checklist", "description", "history", "event"]  # "With Agent Raahi" rows
SAFE_ICONS = ["verified_user", "menu_book", "lock", "help", "balance", "rule"]
# The top navigation: (screen, key). Evaluation (practice only) is reached from the footer.
NAV = [("Home", "home"), ("New case", "new"), ("My cases", "tracker"), ("Learn", "learn"), ("Supervisor", "supervisor")]


def nav_label(screen: str) -> str:
    """The menu name of a screen: "New case" until a case is open, then "Current case"."""
    if screen == "New case" and not st.session_state.get("case_id"):
        return t("ui.new_case.title")
    return t(f"screen.{screen}")


def top_bar(current: str):
    """Logo, the top navigation, one small EN · हिंदी switch and "Start a case". The same on every screen."""
    with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="medium"):
        st.markdown(ui.brand(t("app.name")), unsafe_allow_html=True)
        with st.container(key="topnav", horizontal=True, vertical_alignment="center", gap=None):
            for screen, key in NAV:
                st.button(nav_label(screen), key=f"nav-{key}", type="tertiary", on_click=go, args=(screen,))
        with st.container(key="topmenu"):  # phones: the menu folded behind one button
            st.button(t("nav.menu"), key="topmenu-btn", icon=":material/close:" if st.session_state.get("menu_open")
                      else ":material/menu:", on_click=toggle, args=("menu_open",))
        with st.container(key="toplang"):  # phones: logo, Start a case, menu, language (order set in app.css)
            language_switch()
        with st.container(key="topactions", horizontal=True, vertical_alignment="center", gap="small"):
            st.button(t("nav.start"), type="primary", key="nav-start", on_click=ask_start_case)
    if st.session_state.get("menu_open"):
        with st.container(key="phonemenu"):
            for screen, key in NAV:
                st.button(nav_label(screen), key=f"navm-{key}", type="tertiary", on_click=go, args=(screen,),
                          width="stretch")
            st.button(t("nav.start"), key="navm-start", type="primary", on_click=ask_start_case,
                      width="stretch")  # phones: "Start a case" lives in the menu (hidden from the top bar)
    here = dict(NAV).get(current)
    if here:  # the current screen is underlined in the navigation
        st.markdown(f"<style>.st-key-nav-{here} button {{ background: var(--sand) !important; }}"
                    f".st-key-nav-{here} button p {{ font-weight: 700 !important; }}</style>", unsafe_allow_html=True)


# ---------- navigation ----------

SCREENS = {
    "Home": home_screen,
    "New case": new_case_screen,
    "My cases": my_cases_screen,
    "Learn": learn_screen,
    "Practice": practice_screen,
    "Supervisor": supervisor_screen,
}

SCREEN_KEYS = {**{screen: key for screen, key in NAV}, "Practice": "practice",
               "Supervisor": "supervisor"}
OLD_SCREEN_KEYS = {"evaluation": "Supervisor"}  # the trainers' timing tool moved to the Supervisor page
if "screen" not in st.session_state:  # a fresh session (also after a phone reloads the page): the address says where
    from_url = {**{key: screen for screen, key in SCREEN_KEYS.items()}, **OLD_SCREEN_KEYS}.get(st.query_params.get("screen", ""))
    st.session_state["screen"] = from_url or START_SCREEN
    wanted = st.query_params.get("case", "")
    if wanted and re.fullmatch(r"U-\d{8}-[a-z0-9]{4}", wanted):
        st.session_state["case_id"] = wanted  # opened again after the clinic sign-in
if st.query_params.get("code"):  # opened from the QR code on a case slip
    st.session_state["continue_code"] = st.query_params.get("code")
    st.session_state["screen"] = "New case"
    del st.query_params["code"]
supervisor_idle_check()  # 30 minutes without activity: the supervisor is signed out
choice = st.session_state["screen"] if st.session_state["screen"] in SCREENS else "Home"
keep_place_in_address(choice)
st.session_state["shown_drafts"] = []
st.session_state["_next_shown"] = False  # one filled "next" button per screen
st.session_state["_next_key"] = None
top_bar(choice)
leave_case_box()
if storage.records_will_be_lost():  # online without Supabase: nothing saved would survive a restart
    st.error(t("online.no_supabase"), icon=":material/cloud_off:")
if st.session_state.get("supervisor_ok"):
    supervisor_idle_timer()
if choice in ("Home", "Learn", "Practice", "Supervisor") or clinic_ok():
    SCREENS[choice]()  # Supervisor has its own sign-in (the supervisor password only)
else:
    clinic_gate(choice)  # every other screen needs the clinic passcode (when one is set)
st.markdown(ui.footer(t("app.name"), [t("footer.open_source"), t("footer.built_on")], t("footer.privacy")),
            unsafe_allow_html=True)
