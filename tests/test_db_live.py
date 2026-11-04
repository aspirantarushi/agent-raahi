"""Live checks of the online database's own rules, signed in as the four PRACTICE accounts.

Run only when asked:   LIVE_DB_TESTS=1 .venv/bin/python -m pytest tests/test_db_live.py
Needs SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and PRACTICE_PASSWORD in .env.
Uses fake practice organisations only. Cases it creates have case type "Automated test".
"""

import os
import secrets
from datetime import date

import pytest

import db

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE_DB_TESTS") != "1" or not db.configured()
    or not (db.llm._load_dotenv() or os.environ.get("PRACTICE_PASSWORD")),
    reason="Live database tests run only with LIVE_DB_TESTS=1 and the practice password set",
)

ALPHA, BETA, GAMMA = ("Practice Clinic Alpha (fake data)", "Practice Clinic Beta (fake data)",
                      "Practice Clinic Gamma (not verified)")
TEST_TYPE = "Automated test"
DRAFT = "DRAFT — to be checked by a lawyer\n\nPractice draft made by an automated test. Fake data."


@pytest.fixture(scope="module")
def people():
    password = os.environ["PRACTICE_PASSWORD"]
    return {
        "volunteer": db.sign_in("volunteer.alpha@example.com", password),
        "sup1": db.sign_in("supervisor1.alpha@example.com", password),
        "sup2": db.sign_in("supervisor2.alpha@example.com", password),
        "beta": db.sign_in("member.beta@example.com", password),
    }


@pytest.fixture(scope="module")
def orgs(people):
    alpha = db.select(people["volunteer"], "organisations", "select=id,name")
    beta = db.select(people["beta"], "organisations", "select=id,name")
    ids = {o["name"]: o["id"] for o in alpha + beta}
    return {"alpha": ids[ALPHA], "beta": ids[BETA], "gamma": ids[GAMMA]}


def new_id() -> str:
    return f"U-{date.today():%Y%m%d}-{secrets.choice('abcdefghjkmnpqrstuvwxyz')}{secrets.token_hex(2)[:3]}"


def submit(session, org_id, draft=DRAFT) -> str:
    case_id = new_id()
    db.submit_case(session, case_id, org_id, TEST_TYPE, {"test": True}, draft, None, {})
    return case_id


def case(session, case_id):
    rows = db.select(session, "cases", f"select=*&id={db.eq(case_id)}")
    return rows[0] if rows else None


# ---------- who sees what ----------

def test_each_person_sees_only_their_organisations(people):
    names = lambda s: sorted(o["name"] for o in db.select(s, "organisations", "select=name"))
    assert names(people["volunteer"]) == [ALPHA]
    assert names(people["sup2"]) == [ALPHA]
    assert names(people["beta"]) == [BETA, GAMMA]


def test_other_organisation_cannot_read_a_case(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    assert case(people["volunteer"], case_id)["status"] == "waiting"
    assert case(people["sup1"], case_id) is not None  # same organisation
    assert case(people["beta"], case_id) is None      # other organisation: invisible
    assert db.select(people["beta"], "audit_events", f"select=*&case_id={db.eq(case_id)}") == []


def test_other_organisation_cannot_approve_or_reject(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    with pytest.raises(db.DBError, match="Only a supervisor"):
        db.approve_case(people["beta"], case_id, DRAFT, "file", False, "", None)
    with pytest.raises(db.DBError, match="Only a supervisor"):
        db.reject_case(people["beta"], case_id, "no")


# ---------- approval rules ----------

def test_volunteer_cannot_approve(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    with pytest.raises(db.DBError, match="Only a supervisor"):
        db.approve_case(people["volunteer"], case_id, DRAFT, "file", False, "", None)


def test_supervisor_cannot_approve_own_draft(people, orgs):
    case_id = submit(people["sup1"], orgs["alpha"])
    with pytest.raises(db.DBError, match="made themselves"):
        db.approve_case(people["sup1"], case_id, DRAFT, "file", False, "", None)
    with pytest.raises(db.DBError, match="made themselves"):
        db.reject_case(people["sup1"], case_id, "own draft")
    db.approve_case(people["sup2"], case_id, DRAFT, "Case file (fake)", False, "Follow up", "2026-12-01")
    c = case(people["sup1"], case_id)
    assert c["status"] == "approved"
    assert c["approved_by_name"] == "Practice Supervisor A2"
    assert c["approved_at"] and c["approved_by"] == people["sup2"].user_id
    assert c["next_step_due"] == "2026-12-01"


def test_supervisor_who_resent_cannot_approve(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    db.reject_case(people["sup1"], case_id, "Please fix the court name.")
    db.resend_case(people["sup2"], case_id, DRAFT + "\nFixed.")
    assert case(people["sup2"], case_id)["last_resent_by"] == people["sup2"].user_id
    with pytest.raises(db.DBError, match="resent themselves"):
        db.approve_case(people["sup2"], case_id, DRAFT, "file", False, "", None)
    db.approve_case(people["sup1"], case_id, DRAFT, "file", False, "", None)
    assert case(people["sup1"], case_id)["approved_by_name"] == "Practice Supervisor A1"


def test_audit_events_record_who_and_when(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    db.reject_case(people["sup1"], case_id, "Add the FIR number.")
    db.resend_case(people["volunteer"], case_id, DRAFT + "\nFIR added.")
    db.approve_case(people["sup2"], case_id, DRAFT, "file", True, "", None)
    db.mark_submitted(people["volunteer"], case_id, "2026-11-05")
    events = db.select(people["volunteer"], "audit_events",
                       f"select=event,by_name,by_role,details,event_at&case_id={db.eq(case_id)}&order=id")
    assert [(e["event"], e["by_name"]) for e in events] == [
        ("sent to supervisor", "Practice Volunteer A"),
        ("sent back", "Practice Supervisor A1"),
        ("fixed and resent", "Practice Volunteer A"),
        ("approved", "Practice Supervisor A2"),
        ("marked as submitted", "Practice Volunteer A"),
    ]
    assert events[3]["details"] == "edited by the supervisor before approval"
    assert all(e["event_at"] for e in events)
    assert case(people["volunteer"], case_id)["submitted_on"] == "2026-11-05"


def test_cannot_approve_twice(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    db.approve_case(people["sup1"], case_id, DRAFT, "file", False, "", None)
    with pytest.raises(db.DBError, match="Only waiting drafts"):
        db.approve_case(people["sup2"], case_id, DRAFT, "file", False, "", None)


# ---------- organisations and safety checks ----------

def test_unverified_organisation_cannot_create_cases(people, orgs):
    with pytest.raises(db.DBError, match="not been verified"):
        submit(people["beta"], orgs["gamma"])


def test_cannot_create_case_for_another_organisation(people, orgs):
    with pytest.raises(db.DBError, match="not a member"):
        submit(people["volunteer"], orgs["beta"])


def test_phone_number_in_draft_is_refused(people, orgs):
    with pytest.raises(db.DBError, match="phone number"):
        submit(people["volunteer"], orgs["alpha"], DRAFT + "\nSister: 9876543210")


def test_cases_cannot_be_changed_directly(people, orgs):
    case_id = submit(people["volunteer"], orgs["alpha"])
    with pytest.raises(db.DBError):
        db.update(people["sup1"], "cases", f"id={db.eq(case_id)}", {"status": "approved"})
    with pytest.raises(db.DBError):
        db.update(people["volunteer"], "cases", f"id={db.eq(case_id)}", {"approved_by_name": "Someone"})
    assert case(people["volunteer"], case_id)["status"] == "waiting"


def test_only_platform_admin_creates_organisations(people):
    with pytest.raises(db.DBError):
        db.insert(people["sup2"], "organisations", {"name": "Not allowed", "kind": "NGO"})


def test_nobody_can_make_themselves_platform_admin(people):
    with pytest.raises(db.DBError):
        db.insert(people["volunteer"], "platform_admins", {"user_id": people["volunteer"].user_id})


def test_volunteer_cannot_change_roles(people, orgs):
    rows = db.update(people["volunteer"], "memberships",
                     f"org_id={db.eq(orgs['alpha'])}&user_id={db.eq(people['volunteer'].user_id)}",
                     {"is_supervisor": True})
    assert rows == []  # the row rules let nothing through
    me = db.select(people["volunteer"], "memberships",
                   f"select=is_supervisor&user_id={db.eq(people['volunteer'].user_id)}")
    assert me == [{"is_supervisor": False}]


def test_org_admin_can_invite_but_not_for_another_organisation(people, orgs):
    email = f"invite-test-{secrets.token_hex(3)}@example.com"
    row = db.insert(people["sup2"], "invitations", {"org_id": orgs["alpha"], "email": email})
    assert row["email"] == email
    db.delete(people["sup2"], "invitations", f"id={db.eq(row['id'])}")
    with pytest.raises(db.DBError):
        db.insert(people["sup2"], "invitations", {"org_id": orgs["beta"], "email": email})
    with pytest.raises(db.DBError):  # sup1 is a supervisor but not an organisation admin
        db.insert(people["sup1"], "invitations", {"org_id": orgs["alpha"], "email": email})


def test_problem_reports_stay_in_the_organisation(people, orgs):
    db.insert(people["volunteer"], "problems",
              {"org_id": orgs["alpha"], "place": "automated test", "message": "Practice problem report."})
    alpha = db.select(people["sup1"], "problems", "select=message&place=eq.automated%20test")
    assert alpha and all(p["message"] == "Practice problem report." for p in alpha)
    assert db.select(people["beta"], "problems", "select=message&place=eq.automated%20test") == []
    with pytest.raises(db.DBError, match="phone number"):
        db.insert(people["volunteer"], "problems",
                  {"org_id": orgs["alpha"], "place": "automated test", "message": "call 9876543210"})


def test_names_visible_only_within_the_organisation(people):
    seen = sorted(p["full_name"] for p in db.select(people["beta"], "profiles", "select=full_name"))
    assert seen == ["Practice Member B"]
    alpha = sorted(p["full_name"] for p in db.select(people["volunteer"], "profiles", "select=full_name"))
    assert alpha == ["Practice Supervisor A1", "Practice Supervisor A2", "Practice Volunteer A"]
