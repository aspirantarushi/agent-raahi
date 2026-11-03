"""Legal aid agent: Streamlit web app.

Run with:  streamlit run app.py
"""

import hmac
import os
from datetime import date

import streamlit as st

import section479

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
    if offence.ask_to_decide:
        st.markdown(f"**Question that decides the maximum term:** {offence.ask_to_decide}")
        if offence.notes:
            st.caption(offence.notes)
        question_answered = st.checkbox("This has been answered, and the offence above is the right one")

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

def my_cases_screen():
    st.title("My cases")
    st.info("Cases appear here after a supervisor approves them. None yet.")


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
    st.success("Signed in as supervisor.")
    st.info("Coming soon: drafts waiting for approval.")
    if st.button("Sign out"):
        st.session_state["supervisor_ok"] = False
        st.rerun()


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
