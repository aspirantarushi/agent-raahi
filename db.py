"""Not used: kept for a later multi-clinic version.

Every call to the online database (Supabase) lives in this file.

Plain HTTPS with Python's built-in tools, no extra library.
Settings come from the environment or the .env file (kept out of git):
  SUPABASE_URL              the project address, e.g. https://abcd.supabase.co
  SUPABASE_PUBLISHABLE_KEY  the public key (safe: the database's own rules decide what anyone can see)
The secret / service-role key is never used by the app.

Every request is made AS the signed-in person (their access token), so the database's
row-level security decides what they can see and do: their organisation only, supervisor-only
approval, no self-approval. The app's own checks are a second line, not the only one.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import llm  # for the shared .env reader and HTTPS settings

TIMEOUT_SECONDS = 40


class DBError(Exception):
    """A database request failed. The message is safe to show to the person."""


class Hidden(str):
    """A password that never shows itself in error reports or logs."""

    def __repr__(self) -> str:
        return "'***'"

    __str__ = __repr__


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_at: float
    user_id: str
    email: str


# ---------- settings ----------

def settings() -> Dict[str, str]:
    llm._load_dotenv()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if key.startswith("sb_secret_"):
        raise DBError("SUPABASE_PUBLISHABLE_KEY holds a SECRET key. Use the publishable key instead.")
    return {"url": url, "key": key}


def configured() -> bool:
    s = settings()
    return bool(s["url"] and s["key"])


# ---------- the one place that sends requests ----------

def _request(method: str, path: str, body: Any = None, token: Optional[str] = None,
             extra_headers: Optional[Dict[str, str]] = None) -> Any:
    s = settings()
    if not (s["url"] and s["key"]):
        raise DBError("The online database is not set up (SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY).")
    headers = {"apikey": s["key"], "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    data = json.dumps(body, default=str).encode("utf-8") if body is not None else None
    request = urllib.request.Request(s["url"] + path, data=data, headers=headers, method=method)
    del data  # the encoded body may hold a password: keep no readable copy in error reports
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=llm._ssl_context()) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read() or b"{}")
        except Exception:
            detail = {}
        message = (detail.get("message") or detail.get("msg") or detail.get("error_description")
                   or detail.get("error") or "")
        if err.code in (401, 403) and not message:
            message = "Not allowed. Please sign in again."
        raise DBError(_friendly(message, err.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DBError("Could not reach the online database. Check the internet and try again.") from None
    return json.loads(raw) if raw else None


def _friendly(message: str, code: int) -> str:
    if "violates check constraint" in message and "personal_numbers" in message.replace(" ", "_"):
        return "Refused: the text seems to contain a phone number, Aadhaar number or email address."
    if "violates check constraint" in message:
        return "Refused by the database's safety checks."
    if "permission denied" in message:
        return "Not allowed for your role."
    if "Invalid login credentials" in message:
        return "Wrong email or password."
    if "Email not confirmed" in message:
        return "Please confirm your email first (check your inbox)."
    return message or f"The database refused the request (error {code})."


# ---------- signing in ----------

def _session_from(data: dict) -> Session:
    return Session(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=time.time() + int(data.get("expires_in", 3600)),
        user_id=data["user"]["id"],
        email=data["user"].get("email", ""),
    )


def sign_in(email: str, password: str) -> Session:
    password = Hidden(password)
    data = _request("POST", "/auth/v1/token?grant_type=password",
                    {"email": email.strip().lower(), "password": password})
    return _session_from(data)


def sign_up(email: str, password: str, full_name: str) -> None:
    """Create an account. The person must confirm their email before signing in."""
    password = Hidden(password)
    _request("POST", "/auth/v1/signup", {"email": email.strip().lower(), "password": password,
                                         "data": {"full_name": full_name.strip()[:100]}})


def refresh(session: Session) -> Session:
    data = _request("POST", "/auth/v1/token?grant_type=refresh_token",
                    {"refresh_token": session.refresh_token})
    return _session_from(data)


def fresh(session: Session) -> Session:
    """Refresh the sign-in a minute before it runs out."""
    return refresh(session) if time.time() > session.expires_at - 60 else session


def sign_out(session: Session) -> None:
    try:
        _request("POST", "/auth/v1/logout", {}, token=session.access_token)
    except DBError:
        pass


# ---------- reading and writing as the signed-in person ----------

def select(session: Session, table: str, query: str = "select=*") -> List[dict]:
    return _request("GET", f"/rest/v1/{table}?{query}", token=session.access_token) or []


def insert(session: Session, table: str, row: dict) -> dict:
    result = _request("POST", f"/rest/v1/{table}", row, token=session.access_token,
                      extra_headers={"Prefer": "return=representation"})
    return result[0] if isinstance(result, list) and result else {}


def update(session: Session, table: str, match: str, values: dict) -> List[dict]:
    return _request("PATCH", f"/rest/v1/{table}?{match}", values, token=session.access_token,
                    extra_headers={"Prefer": "return=representation"}) or []


def delete(session: Session, table: str, match: str) -> None:
    _request("DELETE", f"/rest/v1/{table}?{match}", token=session.access_token)


def rpc(session: Session, function: str, args: Optional[dict] = None) -> Any:
    return _request("POST", f"/rest/v1/rpc/{function}", args or {}, token=session.access_token)


def eq(value: str) -> str:
    """Safely quote a value for a filter, e.g. 'id=' + eq(case_id)."""
    return "eq." + urllib.parse.quote(str(value), safe="")


# ---------- the case actions (rules checked by the database) ----------

def submit_case(session: Session, case_id: str, org_id: str, case_type: str, facts: dict, draft: str,
                ai_model: Optional[str], ai_audit: dict) -> None:
    rpc(session, "submit_case", {"p_id": case_id, "p_org": org_id, "p_case_type": case_type, "p_facts": facts,
                                 "p_draft": draft, "p_ai_model": ai_model, "p_ai_audit": ai_audit})


def reject_case(session: Session, case_id: str, reason: str) -> None:
    rpc(session, "reject_case", {"p_id": case_id, "p_reason": reason})


def resend_case(session: Session, case_id: str, draft: str) -> None:
    rpc(session, "resend_case", {"p_id": case_id, "p_draft": draft})


def approve_case(session: Session, case_id: str, final_draft: str, case_file: str, edited: bool,
                 next_step: str, next_step_due: Optional[str]) -> None:
    rpc(session, "approve_case", {"p_id": case_id, "p_final_draft": final_draft, "p_case_file": case_file,
                                  "p_edited": edited, "p_next_step": next_step,
                                  "p_next_step_due": next_step_due})


def mark_submitted(session: Session, case_id: str, on: str) -> None:
    rpc(session, "mark_submitted", {"p_id": case_id, "p_on": on})


def set_next_step(session: Session, case_id: str, step: str, due: Optional[str]) -> None:
    rpc(session, "set_next_step", {"p_id": case_id, "p_step": step, "p_due": due})


def accept_invitations(session: Session) -> int:
    return rpc(session, "accept_invitations") or 0
