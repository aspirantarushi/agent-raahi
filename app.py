"""Legal aid agent: Streamlit web app.

Run with:  streamlit run app.py
"""

import hmac
import json
import os
from datetime import date

import streamlit as st

import drafts
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

def new_case_screen():
    st.title("New case")
    st.caption("Use only case numbers (CNR, FIR). Do not type names, phone numbers, "
               "Aadhaar numbers, addresses or prisoner IDs.")

    case_type = st.radio("What kind of case is it?", ["Undertrial"], horizontal=True)
    if case_type == "Undertrial":
        undertrial_form()


def undertrial_form():
    st.header("Undertrial: Section 479 BNSS dates")

    col1, col2 = st.columns([1, 2])
    law = col1.selectbox("Law", ["IPC", "BNS"])
    section = col2.text_input("Section number", placeholder="for example 380 or 117(2)")

    offence_date = st.date_input("Date of the offence", value=None, format="DD/MM/YYYY",
                                 min_value=date(1990, 1, 1), max_value=date.today(),
                                 help="Before 1 July 2024 the IPC applies; from 1 July 2024 the BNS.")
    custody_began = st.date_input("Date custody began", value=None, format="DD/MM/YYYY",
                                  min_value=date(1990, 1, 1), max_value=date.today())
    today = st.date_input("Today's date", value=date.today(), format="DD/MM/YYYY")

    never_convicted = st.checkbox("Never convicted of any offence before")
    other_cases = st.checkbox("Other cases pending against the person")
    many_sections = st.checkbox("More than one section charged in this case")
    delay_days = st.number_input("Days of delay caused by the accused (0 if none or not known)",
                                 min_value=0, step=1, value=0)

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
                               placeholder="for example: No, no one was hurt")
        confirmed = st.checkbox("With this answer, the offence above is the right one")
        question_answered = bool(answer.strip()) and confirmed
        if not question_answered:
            st.caption("Until the question is answered and confirmed, the dates are to be checked by a lawyer.")

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
    lawyer = st.radio("Does the person have a lawyer?", drafts.LAWYER_OPTIONS, index=None)
    if lawyer is None:
        st.info("Answer the question above to make the draft.")
        return
    facts = drafts.UndertrialFacts(lawyer=lawyer, **known)
    signature = json.dumps(facts.to_dict(), sort_keys=True)

    if st.button("Make draft", type="primary"):
        st.session_state["draft"] = {"sig": signature,
                                     "text": drafts.make_undertrial_draft(facts, result)}

    draft = st.session_state.get("draft")
    if not draft or draft["sig"] != signature:
        return  # no draft yet, or the facts changed since it was made

    if lawyer == "None":
        st.caption("The person has no lawyer, so a DLSA application for free legal aid is added after the note.")
    st.code(draft["text"], language=None, wrap_lines=True)
    st.caption("Blanks in [square brackets] are left for a person to fill. "
               "Names, phone numbers, Aadhaar numbers and addresses are filled by hand, never in this app.")

    sent = st.session_state.get("sent")
    if sent and sent["sig"] == signature:
        st.success(f"Sent to the supervisor as case {sent['id']}. See its status on \"My cases\".")
    elif st.button("Send to supervisor"):
        try:
            case_id = store.submit(draft["text"], facts)
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
        f"- **Maximum prison term:** "
        + (f"{o.max_months} months" if o.max_months is not None else o.max_prison)
    )

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
        return
    st.subheader(f"Drafts waiting for approval: {len(waiting)}")
    for record in waiting:
        review_one(record)


def review_one(record: dict):
    case_id = record["id"]
    with st.expander(f"Case {case_id} · {record['case_type']} · sent {record['submitted'].replace('T', ' ')}",
                     expanded=True):
        for h in record.get("history", []):
            st.caption(f"Sent back earlier, then fixed and resent ({h['resent'].replace('T', ' ')}). "
                       f"Your reason then: {h['sent_back_reason']}")
        st.code(record["draft"], language=None, wrap_lines=True)
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
