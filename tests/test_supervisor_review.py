"""Supervisor section: the audit table and each case's history, the supervisor's name on decisions (and
no approving your own draft), the sign-in lockout, "already decided", one "sent to supervisor" event,
and signing out after 30 idle minutes. Fake practice data only."""

import time
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import audit
import signin_guard
import store
import tracker
from test_compliance import ai_info, make

CLINIC, SUPERVISOR = "practice-pass-123", "sup-pass-9"


def ok(at):
    assert not at.exception, at.exception[0].stack_trace


def waiting_case(base=None, by="Volunteer A", case_type="Undertrial"):
    """A draft sent to the supervisor, with a case slip code (like a real intake)."""
    kw = {"base": base} if base else {}
    record = tracker.open_case(case_type, by, **kw)
    facts, text = make()
    store.submit(text, facts, case_id=record["id"], by=by, **kw)
    return record["id"], record["code"]


def supervisor_screen(monkeypatch, name="SK", **state):
    monkeypatch.setenv("CLINIC_PASSCODE", CLINIC)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", SUPERVISOR)
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.session_state["screen"] = "Supervisor"
    for k, v in {"supervisor_ok": True, "supervisor_name": name, "sup_last_active": time.time(),
                 "clinic_ok": True, "clinic_via_supervisor": True, "volunteer": name, **state}.items():
        at.session_state[k] = v
    at.run()
    ok(at)
    return at


def tables(at):
    return [d.value for d in at.dataframe]


# ---------- 5. one "sent to supervisor" event, with the volunteer's name ----------

def test_one_send_event_with_the_volunteers_name(tmp_path):
    case_id, _ = waiting_case(tmp_path, by="Volunteer A")
    events = audit.read_record(case_id, base=tmp_path)["events"]
    sends = [e for e in events if "sent to" in e["event"]]
    assert sends == [{"time": sends[0]["time"], "event": "sent to supervisor", "by": "Volunteer A", "role": "volunteer"}]


# ---------- 2. the supervisor's name on every decision; no approving your own draft ----------

def test_supervisor_name_on_approve_edit_approve_and_send_back(tmp_path):
    a, _ = waiting_case(tmp_path)
    store.reject(a, "Add the court.", base=tmp_path, by="SK")
    facts, text = make()
    store.resend(a, text, base=tmp_path, by="Volunteer A")
    store.approve(a, edited_text=text + "\nEdited.", base=tmp_path, by="Asha R")
    b, _ = waiting_case(tmp_path)
    store.approve(b, base=tmp_path, by="SK")
    decided = [(e["event"], e["by"], e.get("role")) for e in audit.read_record(a, base=tmp_path)["events"]
               if e["event"] in ("sent back", "approved", "fixed and resent")]
    assert decided == [("sent back", "SK", "supervisor"), ("fixed and resent", "Volunteer A", "volunteer"),
                       ("approved", "Asha R", "supervisor")]
    assert [e for e in audit.read_record(b, base=tmp_path)["events"] if e["event"] == "approved"][0]["by"] == "SK"
    assert "approved, by Asha R (supervisor) (edited by the supervisor before approval)" in \
        audit.describe(audit.read_record(a, base=tmp_path))


@pytest.mark.parametrize("supervisor", ["Volunteer A", "volunteer a", " Volunteer  A ", "VOLUNTEER-A"])
def test_cannot_approve_a_draft_you_sent(tmp_path, supervisor):
    case_id, _ = waiting_case(tmp_path, by="Volunteer A")
    with pytest.raises(store.OwnDraft, match="You sent this draft, so another supervisor must approve it."):
        store.approve(case_id, base=tmp_path, by=supervisor)
    with pytest.raises(store.OwnDraft):
        store.approve(case_id, edited_text=store.get_pending(case_id, base=tmp_path)["draft"] + "\nx",
                      base=tmp_path, by=supervisor)
    assert store.get_pending(case_id, base=tmp_path)["status"] == store.WAITING  # nothing saved
    store.approve(case_id, base=tmp_path, by="Supervisor B")  # another supervisor can


def test_cannot_approve_a_draft_you_resent(tmp_path):
    case_id, _ = waiting_case(tmp_path, by="Volunteer A")
    store.reject(case_id, "Add the court.", base=tmp_path, by="SK")
    facts, text = make()
    store.resend(case_id, text, base=tmp_path, by="SK")  # the supervisor fixed and resent it themselves
    with pytest.raises(store.OwnDraft):
        store.approve(case_id, base=tmp_path, by="SK")
    store.approve(case_id, base=tmp_path, by="Supervisor B")


def test_supervisor_is_asked_for_a_name_after_the_password(monkeypatch):
    monkeypatch.setenv("CLINIC_PASSCODE", CLINIC)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", SUPERVISOR)
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = "Supervisor"
    at.run()
    at.text_input(key="sup-pass").set_value(SUPERVISOR)
    at.button(key="sup-go").click().run()
    assert {w.key for w in at.text_input} == {"sup-name"} and at.text_input(key="sup-name").label == "Your name or initials"
    at.button(key="sup-name-go").click().run()  # no name: asked again
    assert "Type your name or initials" in at.error[0].value
    at.text_input(key="sup-name").set_value("  SK ")
    at.button(key="sup-name-go").click().run()
    ok(at)
    assert at.session_state["supervisor_name"] == "SK" and at.title[0].value == "Supervisor"


def test_own_draft_on_screen_cannot_be_approved(monkeypatch):
    case_id, _ = waiting_case(by="Practice Volunteer Z")
    at = supervisor_screen(monkeypatch, name="practice volunteer z")
    at.radio(key=f"action-{case_id}").set_value("Approve").run()
    assert any("You sent this draft, so another supervisor must approve it." in w.value for w in at.warning)
    assert at.button(key=f"approve-{case_id}").disabled
    assert store.get_pending(case_id)["status"] == store.WAITING


# ---------- 4. already decided; one click only ----------

def test_deciding_twice_says_already_decided(tmp_path):
    case_id, _ = waiting_case(tmp_path)
    store.approve(case_id, base=tmp_path, by="SK")
    with pytest.raises(store.AlreadyDecided, match="This case was already decided."):
        store.approve(case_id, base=tmp_path, by="SK2")
    with pytest.raises(store.AlreadyDecided):
        store.reject(case_id, "late", base=tmp_path, by="SK2")
    other, _ = waiting_case(tmp_path)
    store.reject(other, "Add the court.", base=tmp_path, by="SK")
    with pytest.raises(store.AlreadyDecided):
        store.approve(other, base=tmp_path, by="SK2")


def test_second_supervisor_sees_already_decided_not_an_error(monkeypatch):
    case_id, _ = waiting_case()
    at = supervisor_screen(monkeypatch)
    at.radio(key=f"action-{case_id}").set_value("Approve").run()
    store.approve(case_id, by="Another supervisor")  # decided elsewhere in the meantime
    at.button(key=f"approve-{case_id}").click().run()
    ok(at)
    assert any("This case was already decided." in i.value for i in at.info)
    assert not any("already" in e.value.lower() for e in at.error)


def test_decision_button_is_disabled_after_the_first_click(monkeypatch):
    case_id, _ = waiting_case()
    calls = []
    monkeypatch.setattr(store, "approve", lambda cid, **kw: calls.append(cid))  # the draft stays waiting
    at = supervisor_screen(monkeypatch)
    at.radio(key=f"action-{case_id}").set_value("Approve").run()
    assert not at.button(key=f"approve-{case_id}").disabled
    at.button(key=f"approve-{case_id}").click().run()
    ok(at)
    assert calls == [case_id] and at.button(key=f"approve-{case_id}").disabled


def test_send_back_without_a_reason_can_be_tried_again(monkeypatch):
    case_id, _ = waiting_case()
    at = supervisor_screen(monkeypatch)
    at.radio(key=f"action-{case_id}").set_value("Reject with a reason").run()
    at.button(key=f"reject-{case_id}").click().run()
    assert any("reason" in e.value for e in at.error) and not at.button(key=f"reject-{case_id}").disabled
    at.text_area(key=f"reason-{case_id}").set_value("Add the court.")
    at.button(key=f"reject-{case_id}").click().run()
    ok(at)
    assert store.get_pending(case_id)["status"] == store.SENT_BACK
    assert store.get_pending(case_id)["sent_back_by"] == "SK"


# ---------- 1. the audit table, each case's history, CSV ----------

def test_audit_rows_columns_status_and_newest_first(tmp_path):
    a, code_a = waiting_case(tmp_path, by="VA")
    b, code_b = waiting_case(tmp_path, by="VB")
    c, code_c = waiting_case(tmp_path, by="VC")
    store.reject(b, "Add the court.", base=tmp_path, by="SK")
    store.approve(c, base=tmp_path, by="SK2")
    d, code_d = waiting_case(tmp_path, by="VD")
    store.delete_case(d, base=tmp_path, by="SK")
    codes = {r["id"]: r["code"] for r in tracker.all_records(base=tmp_path)}
    rows = [audit.summary_row(r, codes.get(r["case_id"], "")) for r in audit.list_records(base=tmp_path)]
    by_case = {r["case_id"]: r for r in rows}
    assert by_case[a]["status"] == "waiting" and by_case[a]["sent_by"] == "VA" and by_case[a]["decision_by"] == ""
    assert by_case[a]["code"] == code_a and by_case[a]["case_type"] == "Undertrial" and by_case[a]["ai_used"] == "no AI"
    assert by_case[b]["status"] == "sent back" and by_case[b]["decision_by"] == "SK (supervisor)"
    assert by_case[c]["status"] == "approved" and by_case[c]["decision_by"] == "SK2 (supervisor)"
    assert by_case[c]["last_step"] == "timeline created" and by_case[c]["decision_on"]
    assert by_case[d]["status"] == "deleted" and by_case[d]["decision_by"] == "SK (supervisor)"
    assert set(by_case[a]) >= {"code", "case_type", "status", "sent_by", "sent_on", "decision_by", "decision_on",
                               "ai_used", "last_step"}
    shown = audit.filter_rows(rows)
    keys = [r["sent_on"] or r["created"] for r in shown]
    assert keys == sorted(keys, reverse=True)  # newest first


def test_audit_filters_search_status_and_dates(tmp_path):
    a, code_a = waiting_case(tmp_path)
    b, _ = waiting_case(tmp_path)
    store.approve(b, base=tmp_path, by="SK")
    codes = {r["id"]: r["code"] for r in tracker.all_records(base=tmp_path)}
    rows = [audit.summary_row(r, codes.get(r["case_id"], "")) for r in audit.list_records(base=tmp_path)]
    assert [r["case_id"] for r in audit.filter_rows(rows, search=code_a.lower())] == [a]
    assert [r["case_id"] for r in audit.filter_rows(rows, search=a)] == [a]  # the case number works too
    assert [r["case_id"] for r in audit.filter_rows(rows, status="approved")] == [b]
    today = date.today()
    assert len(audit.filter_rows(rows, start=today, end=today)) == 2
    assert audit.filter_rows(rows, start=date(2020, 1, 1), end=date(2020, 1, 2)) == []


def test_history_rows_and_csv(tmp_path):
    case_id, _ = waiting_case(tmp_path, by="VA")
    store.reject(case_id, "Add the court.", base=tmp_path, by="SK")
    rows = audit.history_rows(audit.read_record(case_id, base=tmp_path))
    assert (rows[0]["event"], rows[0]["by"]) == ("sent to supervisor", "VA (volunteer)")
    assert rows[-1]["event"] == "sent back" and rows[-1]["by"] == "SK (supervisor)"
    assert rows[-1]["details"] == "reason: Add the court." and len(rows[-1]["time"]) == 16
    text = audit.to_csv(rows, [("time", "Time"), ("event", "What happened"), ("by", "By"), ("details", "Details")])
    assert text.splitlines()[0] == "Time,What happened,By,Details" and "SK (supervisor)" in text


def test_audit_table_on_screen_opens_a_history_and_downloads(monkeypatch):
    case_id, code = waiting_case(by="Volunteer Q")
    store.reject(case_id, "Add the court.", by="SK")
    at = supervisor_screen(monkeypatch)
    at.text_input(key="aud-q").set_value(code).run()  # search by case code
    ok(at)
    table = tables(at)[-1]
    assert list(table.columns) == ["Case code", "Case type", "Status", "Sent by", "Sent on", "Decision by",
                                   "Decision on", "AI used", "Last step"]
    assert table.to_dict("records")[0]["Case code"] == code and table.iloc[0]["Status"] == "Sent back"
    assert table.iloc[0]["Sent by"] == "Volunteer Q" and table.iloc[0]["Decision by"] == "SK (supervisor)"
    at.selectbox(key="aud-status").set_value("approved").run()
    assert len(tables(at)[-1]) == 0
    at.selectbox(key="aud-status").set_value("sent back").run()
    at.session_state["aud-open"] = case_id  # what clicking the row does
    at.run()
    ok(at)
    history = tables(at)[-1]
    assert list(history.columns) == ["Time", "What happened", "By", "Details"]
    assert history.iloc[-1]["What happened"] == "sent back" and history.iloc[-1]["By"] == "SK (supervisor)"
    assert any(f"History of case {code}" in m.value for m in at.markdown)
    assert len(at.get("download_button")) >= 2  # the table and the history


def test_waiting_draft_audit_record_uses_the_history_table(monkeypatch):
    case_id, _ = waiting_case(by="Volunteer W")
    at = supervisor_screen(monkeypatch)
    histories = [t for t in tables(at) if list(t.columns) == ["Time", "What happened", "By", "Details"]]
    assert any((h["What happened"] == "sent to supervisor").any() and (h["By"] == "Volunteer W (volunteer)").any()
               for h in histories)


def test_audit_table_scrolls_inside_its_own_box():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "assets" / "app.css").read_text(encoding="utf-8")
    assert "st-key-aud-table-box" in css and "overflow-x: auto" in css
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert 'on_select=open_audit_row, selection_mode=["single-row", "single-cell"]' in source  # a row: tick box or any cell


# ---------- 3. five wrong passwords lock the sign-in for five minutes ----------

def test_guard_locks_after_five_and_opens_after_five_minutes():
    keys = ["supervisor:session:x"]
    for _ in range(4):
        assert not signin_guard.failed(keys, now=1000)
    assert signin_guard.seconds_locked(keys, now=1000) == 0
    assert signin_guard.failed(keys, now=1000)  # the 5th
    assert 0 < signin_guard.seconds_locked(keys, now=1000) <= 300
    assert signin_guard.seconds_locked(keys, now=1000 + 299) > 0
    assert signin_guard.seconds_locked(keys, now=1000 + 301) == 0


def test_guard_shared_address_has_a_higher_limit():
    ip = "ip:volunteer:10.0.0.1"
    for n in range(19):
        signin_guard.failed([f"volunteer:session:{n}", ip], now=50)  # many volunteers on one hotspot
    assert signin_guard.seconds_locked(["volunteer:session:new", ip], now=50) == 0
    signin_guard.failed(["volunteer:session:20", ip], now=50)
    assert signin_guard.seconds_locked(["volunteer:session:new", ip], now=50) > 0


@pytest.mark.parametrize("screen, box, go, right, wrong_message", [
    ("Supervisor", "sup-pass", "sup-go", SUPERVISOR, "Wrong password."),
    ("New case", "gate-pass", "gate-go", CLINIC, "That passcode is not right. Ask your clinic coordinator."),
])
def test_five_wrong_tries_lock_the_sign_in(monkeypatch, screen, box, go, right, wrong_message):
    monkeypatch.setenv("CLINIC_PASSCODE", CLINIC)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", SUPERVISOR)
    at = AppTest.from_file("../app.py", default_timeout=20)
    at.session_state["screen"] = screen
    at.run()
    for n in range(5):
        at.text_input(key=box).set_value(f"wrong-{n}")
        if box == "gate-pass":
            at.text_input(key="gate-name").set_value("RK")
        at.button(key=go).click().run()
        ok(at)
        assert at.error[0].value == (wrong_message if n < 4 else "Too many tries; wait 5 minutes.")
    at.text_input(key=box).set_value(right)  # even the right password waits now
    if box == "gate-pass":
        at.text_input(key="gate-name").set_value("RK")
    at.button(key=go).click().run()
    assert at.error[0].value == "Too many tries; wait 5 minutes."
    assert "clinic_ok" not in at.session_state and "supervisor_ok" not in at.session_state


# ---------- 6. signed out after 30 minutes without activity ----------

def test_supervisor_signed_out_after_30_idle_minutes(monkeypatch):
    at = supervisor_screen(monkeypatch, sup_last_active=time.time() - 31 * 60)
    assert at.title[0].value == "Supervisor sign-in"
    assert any("Signed out after 30 minutes without activity" in i.value for i in at.info)
    assert not at.session_state["supervisor_ok"] and "clinic_ok" not in at.session_state  # the clinic access ends too
    at.session_state["screen"] = "New case"
    at.run()
    assert at.title[0].value == "Volunteer sign-in"


def test_activity_keeps_the_supervisor_signed_in(monkeypatch):
    before = time.time() - 29 * 60
    at = supervisor_screen(monkeypatch, sup_last_active=before)
    assert at.title[0].value == "Supervisor" and at.session_state["supervisor_ok"]
    assert at.session_state["sup_last_active"] > before  # this visit counts as activity


def test_idle_timer_checks_once_a_minute():
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert "@st.fragment(run_every=60)\ndef supervisor_idle_timer" in source
    assert "SUPERVISOR_IDLE_SECONDS = 30 * 60" in source
