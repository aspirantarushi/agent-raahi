"""Legal aid agent: Streamlit web app.

Run with:  streamlit run app.py
"""

import hmac
import json
import os
from datetime import date

import streamlit as st

import audit
import drafts
import intake
import llm
import section479
import store

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

DATE_FORMAT = "%d %B %Y"  # 15 July 2026


def show_date(d: date) -> str:
    return d.strftime(DATE_FORMAT).lstrip("0")


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
FACT_LABELS = {
    "custody_began": "Date custody began", "offence_date": "Date of the offence", "today": "Today's date",
    "section": "Section", "law": "Law", "more_than_one_section": "More than one section charged",
    "never_convicted": "Never convicted", "other_cases_pending": "Other cases pending",
    "delay_days_by_accused": "Days of delay caused by the accused", "lawyer": "Lawyer",
    "answer": "Answer to the deciding question",
}


def init_form():
    for key, value in FORM_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    if st.session_state["f_today"] is None:
        st.session_state["f_today"] = date.today()


def save_problem(key: str, case_id, where: str):
    text = st.session_state.get(f"problem-{key}", "")
    try:
        audit.report_problem(text, case_id, where)
    except ValueError as err:
        st.session_state[f"problem-msg-{key}"] = ("error", str(err))
        return
    st.session_state[f"problem-{key}"] = ""
    st.session_state[f"problem-msg-{key}"] = ("ok", "Thank you. The problem was saved for the supervisor.")


def report_problem_box(key: str, where: str, case_id=None):
    """A small "Report a problem" box. Saved to the problems log with the case number and date."""
    with st.expander("\u26a0\ufe0f Report a problem"):
        st.caption("Describe the problem in a few words. Do not include names, phone numbers, "
                   "Aadhaar numbers, addresses or prisoner IDs.")
        st.text_area("What went wrong?", key=f"problem-{key}", max_chars=audit.MAX_PROBLEM_LENGTH, height=100)
        st.button("Send report", key=f"problem-send-{key}", on_click=save_problem, args=(key, case_id, where))
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
    st.title("New case")
    st.caption("Use only case numbers (CNR, FIR). Do not type names, phone numbers, "
               "Aadhaar numbers, addresses or prisoner IDs.")

    case_type = st.radio("What kind of case is it?", ["Undertrial"], horizontal=True)
    if case_type == "Undertrial":
        init_form()
        notes_box()
        if not ask_missing_facts():  # while missing facts are asked one at a time, the form waits
            undertrial_form()
        sent = st.session_state.get("sent")
        report_problem_box("new-case", "New case", sent["id"] if sent else None)


# ----- reading pasted case notes with the AI -----

def show_value(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
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
    with st.expander("Paste case notes (optional): the AI fills in the form for you", expanded=ai is None):
        st.warning("**Do not type names**, phone numbers, Aadhaar numbers, addresses or prisoner IDs. "
                   "Phone numbers, Aadhaar numbers and email addresses are removed before the notes are "
                   "sent to the AI (Google Gemini), but names cannot be removed automatically.")
        if not llm.available():
            st.info("AI reading is not set up on this computer, so please fill in the form below by hand.")
            return
        st.text_area("Case notes", key="f_notes", height=220,
                     placeholder="For example: He was arrested on 15 March 2024 and is charged under IPC 380 ...")
        col1, col2 = st.columns(2)
        col1.button("Read notes", type="primary", on_click=read_notes)
        if ai:
            col2.button("Clear notes and start again", on_click=clear_notes)
    if st.session_state.get("ai_error"):
        st.error(st.session_state["ai_error"] + " You can fill in the form below by hand.")


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


def ask_missing_facts() -> bool:
    """Ask the first missing fact. Returns True while questions remain."""
    ai = st.session_state.get("ai")
    if not ai:
        return False
    missing = intake.missing_facts(ai["values"], ai["skipped"])
    if not missing:
        return False

    fact = missing[0]
    questions = intake.intake_questions()
    number = dict(intake.FACT_QUESTIONS)[fact]
    st.subheader(f"A few facts are missing ({len(missing)} to go)")
    if ai["removed"]:
        st.caption("Removed before sending: " + ", ".join(f"{n} × {k}" for k, n in ai["removed"].items()))
    found = {f: v for f, v in ai["values"].items() if f in FACT_LABELS}
    if found:
        st.caption("Found in the notes so far: "
                   + "; ".join(f"{FACT_LABELS[f]}: {show_value(v)}" for f, v in found.items()))

    with st.container(border=True):
        question = questions[number]
        if fact == "answer":
            question = intake.offence_question(ai["values"])
        st.markdown(f"**{question}**")
        if fact in ai["reading"].notes_say:
            st.caption(f"The notes say: “{ai['reading'].notes_say[fact]}”")
        question_widget(fact)
        col1, col2, col3 = st.columns([1, 1, 2])
        col1.button("Next", type="primary", key=f"next-{fact}", on_click=answer_fact, args=(fact,))
        col2.button("Don't know", key=f"skip-{fact}", on_click=answer_fact, args=(fact, True))
        col3.button("Skip the rest and check the form", key="skip-all", on_click=skip_all)
    return True


def question_widget(fact: str):
    """Draw one input for one missing fact."""
    if fact in ("custody_began", "offence_date"):
        st.date_input("Date", value=None, format="DD/MM/YYYY", key=f"q-{fact}",
                      min_value=date(1990, 1, 1), max_value=date.today())
    elif fact == "section":
        col1, col2 = st.columns([1, 2])
        col1.selectbox("Law", ["IPC", "BNS"], key="q-law")
        col2.text_input("Section number", key="q-section", placeholder="for example 380")
        st.checkbox("More than one section is charged in this case", key="q-many")
    elif fact == "never_convicted":
        st.radio("Answer", ["Never", "Yes", "Not sure"], index=None, key="q-never", horizontal=True)
    elif fact in ("other_cases_pending", "delay_days_by_accused"):
        st.radio("Answer", ["No", "Yes", "Not sure"], index=None, key=f"q-{fact}", horizontal=True)
        if fact == "delay_days_by_accused" and st.session_state.get("q-delay_days_by_accused") == "Yes":
            st.number_input("About how many days of delay?", min_value=1, step=1, value=None,
                            key="q-delay-days")
    elif fact == "answer":
        st.text_input("Answer", key="q-answer", max_chars=200)
    elif fact == "lawyer":
        st.radio("Answer", drafts.LAWYER_OPTIONS, index=None, key="q-lawyer")


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
        st.markdown("**Filled in from the notes. Check every field above against the notes and correct "
                    "anything wrong before going on.**")
        rows = [f"- {FACT_LABELS[f]}: {show_value(v)} — notes: “{reading.evidence[f]}”"
                for f, v in reading.values.items() if f in FACT_LABELS and f in reading.evidence]
        asked = [f for f in ai["values"] if f not in reading.values and f in FACT_LABELS]
        if rows:
            st.markdown("Found in the notes:\n" + "\n".join(rows))
        if asked:
            st.markdown("You answered: " + ", ".join(FACT_LABELS[f] for f in asked))
        unknown = [FACT_LABELS[f] for f in ai["skipped"] if f in FACT_LABELS]
        if unknown:
            st.warning("Still not known: " + ", ".join(unknown) + ".")
        if reading.values.get("all_sections"):
            st.warning("The notes name more than one section: " + ", ".join(reading.values["all_sections"])
                       + ". The form uses the first; a lawyer must check whether Section 479(2) bars release.")
        return st.checkbox("I have checked every field against the notes", key="f_checked")


def undertrial_form():
    st.header("Undertrial: Section 479 BNSS dates")

    col1, col2 = st.columns([1, 2])
    law = col1.selectbox("Law", ["IPC", "BNS"], key="f_law")
    section = col2.text_input("Section number", placeholder="for example 380 or 117(2)", key="f_section")

    offence_date = st.date_input("Date of the offence", format="DD/MM/YYYY", key="f_offence_date",
                                 min_value=date(1990, 1, 1), max_value=date.today(),
                                 help="Before 1 July 2024 the IPC applies; from 1 July 2024 the BNS.")
    custody_began = st.date_input("Date custody began", format="DD/MM/YYYY", key="f_custody",
                                  min_value=date(1990, 1, 1), max_value=date.today())
    today = st.date_input("Today's date", format="DD/MM/YYYY", key="f_today")

    never_convicted = st.checkbox("Never convicted of any offence before", key="f_never")
    other_cases = st.checkbox("Other cases pending against the person", key="f_other")
    many_sections = st.checkbox("More than one section charged in this case", key="f_many")
    delay_days = st.number_input("Days of delay caused by the accused (0 if none or not known)",
                                 min_value=0, step=1, key="f_delay")

    if not section.strip():
        st.info("Type the IPC or BNS section to see the dates.")
        return

    matches = section479.find_offences(law, section)
    if not matches:
        st.warning(
            f"{law} {section} is not in our sentence table yet, so we can't work out the dates. "
            "Please ask a lawyer, or call NALSA's free legal aid helpline on 15100."
        )
        return

    if len(matches) > 1:
        labels = [f"BNS {o.bns_section} / IPC {o.ipc_section}: {o.offence}" for o in matches]
        picked = st.radio("This section covers more than one offence. Which one fits?", labels)
        offence = matches[labels.index(picked)]
    else:
        offence = matches[0]

    question_answered = False
    answer = ""
    if offence.ask_to_decide:
        st.markdown(f"**Question that decides the maximum term:** {offence.ask_to_decide}")
        if offence.notes:
            st.caption(offence.notes)
        answer = st.text_input("Answer (leave empty if not known)", max_chars=200,
                               placeholder="for example: No, no one was hurt", key="f_answer")
        confirmed = st.checkbox("With this answer, the offence above is the right one", key="f_confirm")
        question_answered = bool(answer.strip()) and confirmed
        if not question_answered:
            st.caption("Until the question is answered and confirmed, the dates are to be checked by a lawyer.")

    if not checked_by_volunteer():
        st.info("Tick the box above once you have checked every field. Then the dates are worked out.")
        return

    if custody_began is None:
        st.info("Pick the date custody began to see the dates.")
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
    st.subheader("Draft")
    if known["offence_date"] is None:
        st.info("Pick the date of the offence (at the top) to make the draft. "
                "It decides whether the note names the IPC or the BNS section first.")
        return
    lawyer = st.radio("Does the person have a lawyer?", drafts.LAWYER_OPTIONS, key="f_lawyer")
    if lawyer is None:
        st.info("Answer the question above to make the draft.")
        return
    facts = drafts.UndertrialFacts(lawyer=lawyer, **known)
    ai_info = ai_info_for_audit()
    ai_model = ai_info["model"] if ai_info else None
    signature = json.dumps({**facts.to_dict(), "ai_model": ai_model}, sort_keys=True)

    if st.button("Make draft", type="primary"):
        st.session_state["draft"] = {"sig": signature,
                                     "text": drafts.make_undertrial_draft(facts, result, ai_model=ai_model)}

    draft = st.session_state.get("draft")
    if not draft or draft["sig"] != signature:
        return  # no draft yet, or the facts changed since it was made

    if lawyer == "None":
        st.caption("The person has no lawyer, so a DLSA application for free legal aid is added after the note.")
    st.code(draft["text"], language=None, wrap_lines=True)
    st.caption("Blanks in [square brackets] are left for a person to fill. "
               "Names, phone numbers, Aadhaar numbers and addresses are filled by hand, never in this app. "
               "The supervisor's approval date is filled in when the draft is approved.")

    sent = st.session_state.get("sent")
    report_problem_box("draft", "Draft on New case",
                       sent["id"] if sent and sent["sig"] == signature else None)
    if sent and sent["sig"] == signature:
        st.success(f"Sent to the supervisor as case {sent['id']}. See its status on \"My cases\".")
    elif st.button("Send to supervisor"):
        try:
            case_id = store.submit(draft["text"], facts, ai=ai_info)
        except ValueError as err:
            st.error(str(err))
            return
        st.session_state["sent"] = {"sig": signature, "id": case_id}
        st.rerun()


def show_result(result: section479.Result):
    o = result.offence
    st.divider()
    st.subheader("Result")
    st.markdown(
        f"- **Offence:** {o.offence}\n"
        f"- **BNS section:** {o.bns_section}\n"
        f"- **IPC section:** {o.ipc_section}\n"
        f"- **Maximum prison term used:** "
        + (f"{result.maximum.months} months, as per {result.maximum.section}"
           if result.maximum.months is not None else result.maximum.value)
    )
    if result.maximum.reason:
        st.caption(result.maximum.reason
                   + (f"  \n{result.maximum.source_line}" if result.maximum.source_line else ""))

    if not result.applies:
        for reason in result.reasons:
            st.error(reason)
    else:
        if result.lawyer_check:
            st.warning("These dates are **to be checked by a lawyer**.")
        for m in (result.one_third, result.one_half):
            if m.when is None:
                st.markdown(f"**{m.name}:** not available. {m.note}")
                continue
            status = "✅ reached" if m.reached else "⏳ not yet reached"
            st.markdown(
                f"**{m.name}** ({section479.format_months(m.months)}): "
                f"{show_date(m.when)} — {status}"
            )
            if m.note:
                st.caption(m.note)
        for reason in result.reasons:
            st.caption(reason)

    st.info(section479.NOT_AUTOMATIC)

    src = section479.knowledge_source("How to work out the Section 479 dates")
    st.caption(
        f"Source: {src['source']} — {src['link']}  \n"
        f"Sentence table source: {o.source_url}  \n"
        f"Checked: {src.get('checked', 'not stated')}"
    )


# ---------- other screens ----------

STATUS_LABELS = {
    store.WAITING: "⏳ Waiting for the supervisor",
    store.APPROVED: "✅ Approved",
    store.SENT_BACK: "↩️ Sent back",
}


def my_cases_screen():
    st.title("My cases")
    cases = store.list_cases()
    if not cases:
        st.info("No cases yet. Make a draft on \"New case\" and send it to the supervisor.")
        return
    for c in cases:
        with st.container(border=True):
            st.markdown(f"**Case {c['id']}** · {c['case_type']}  \n{STATUS_LABELS[c['status']]}")
            if c["status"] == store.SENT_BACK:
                st.warning(f"Supervisor's reason: {c['reason']}")
                fix_and_resend(c["id"])
            if c["status"] == store.APPROVED:
                with st.expander("Case file"):
                    st.markdown(c["file"].read_text(encoding="utf-8"))
                draft_file = c["file"].parent.parent / "drafts" / c["file"].name
                if draft_file.exists():
                    with st.expander("Approved draft"):
                        st.code(draft_file.read_text(encoding="utf-8"), language=None, wrap_lines=True)
            report_problem_box(f"case-{c['id']}", "My cases", c["id"])


def fix_and_resend(case_id: str):
    flag = f"fixing-{case_id}"
    if not st.session_state.get(flag):
        if st.button("Fix and resend", key=f"fix-{case_id}"):
            st.session_state[flag] = True
            st.rerun()
        return
    record = store.get_pending(case_id)
    fixed = st.text_area("Fix the draft", value=record["draft"], height=500, key=f"fixtext-{case_id}")
    st.caption("Do not add names, phone numbers, Aadhaar numbers, addresses or prisoner IDs. "
               "To change the facts (dates, sections, answers), make a new draft on \"New case\" instead.")
    col1, col2 = st.columns(2)
    if col1.button("Resend to supervisor", type="primary", key=f"resend-{case_id}"):
        try:
            store.resend(case_id, fixed)
        except ValueError as err:
            st.error(str(err))
            return
        st.session_state[flag] = False
        st.rerun()
    if col2.button("Cancel", key=f"cancel-{case_id}"):
        st.session_state[flag] = False
        st.rerun()


def learn_screen():
    st.title("Learn")
    st.info("Coming soon: explainers, quizzes and practice cases.")


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
    st.title("Supervisor")
    expected = supervisor_password()
    if not expected:
        st.warning("The supervisor password has not been set up yet. "
                   "Put SUPERVISOR_PASSWORD in .streamlit/secrets.toml (see the example file).")
        return
    if not st.session_state.get("supervisor_ok"):
        typed = st.text_input("Supervisor password", type="password")
        if st.button("Sign in"):
            if hmac.compare_digest(typed, expected):
                st.session_state["supervisor_ok"] = True
                st.rerun()
            else:
                st.error("Wrong password.")
        return
    top1, top2 = st.columns([3, 1])
    top1.success("Signed in as supervisor.")
    if top2.button("Sign out"):
        st.session_state["supervisor_ok"] = False
        st.rerun()

    flash = st.session_state.pop("supervisor_flash", None)
    if flash:
        st.success(flash)

    waiting = store.list_pending()
    if not waiting:
        st.info("No drafts are waiting for approval.")
    else:
        st.subheader(f"Drafts waiting for approval: {len(waiting)}")
        for record in waiting:
            review_one(record)

    st.subheader("Problems reported")
    problems = audit.list_problems()
    if not problems:
        st.caption("No problems reported.")
    for p in problems:
        st.markdown(f"- **{p['time'].replace('T', ' ')}** · case {p['case_id']} · {p['where']}: {p['text']}"
                    + (f" _(removed: {p['removed']})_" if p.get("removed") else ""))

    st.subheader("Audit records of all cases")
    records = audit.list_records()
    if not records:
        st.caption("No audit records yet.")
    for r in records:
        with st.expander(f"Case {r['case_id']} · AI: {r['model']} · last: {r['events'][-1]['event']}"):
            st.markdown(audit.describe(r))


def review_one(record: dict):
    case_id = record["id"]
    with st.expander(f"Case {case_id} · {record['case_type']} · sent {record['submitted'].replace('T', ' ')}",
                     expanded=True):
        for h in record.get("history", []):
            st.caption(f"Sent back earlier, then fixed and resent ({h['resent'].replace('T', ' ')}). "
                       f"Your reason then: {h['sent_back_reason']}")
        st.code(record["draft"], language=None, wrap_lines=True)
        audit_record = audit.read_record(case_id)
        with st.expander("Audit record: what the AI and the volunteer did"):
            st.markdown(audit.describe(audit_record) if audit_record else "No audit record for this case.")
        action = st.radio("Your decision", ["Approve", "Edit then Approve", "Reject with a reason"],
                          index=None, horizontal=True, key=f"action-{case_id}")
        try:
            if action == "Approve":
                if st.button("Approve and save", type="primary", key=f"approve-{case_id}"):
                    store.approve(case_id)
                    st.session_state["supervisor_flash"] = f"Case {case_id} approved and saved."
                    st.rerun()
            elif action == "Edit then Approve":
                edited = st.text_area("Edit the draft", value=record["draft"], height=500,
                                      key=f"edit-{case_id}")
                st.caption("Do not add names, phone numbers, Aadhaar numbers, addresses or prisoner IDs.")
                if st.button("Save edits and approve", type="primary", key=f"edit-approve-{case_id}"):
                    store.approve(case_id, edited_text=edited)
                    st.session_state["supervisor_flash"] = f"Case {case_id} edited, approved and saved."
                    st.rerun()
            elif action == "Reject with a reason":
                reason = st.text_area("Reason (shown on \"My cases\")", key=f"reason-{case_id}")
                if st.button("Send back", key=f"reject-{case_id}"):
                    store.reject(case_id, reason)
                    st.session_state["supervisor_flash"] = f"Case {case_id} sent back."
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

st.sidebar.title("Legal aid agent")
choice = st.sidebar.radio("Go to", list(SCREENS))
st.sidebar.markdown("---")
st.sidebar.markdown("**In danger? Call 112 now.**  \nFree legal aid helpline: **15100**")
SCREENS[choice]()
