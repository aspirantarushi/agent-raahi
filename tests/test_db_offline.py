"""db.py checks that need no internet."""

import json
import urllib.error

import pytest

import db


def test_password_never_shown_in_reports():
    secret = db.Hidden("my-practice-password")
    for shown in (repr(secret), str(secret), repr({"password": secret}), f"{secret}"):
        assert "my-practice-password" not in shown
    assert json.loads(json.dumps({"password": secret}))["password"] == "my-practice-password"


def test_failed_sign_in_error_does_not_contain_password(monkeypatch):
    monkeypatch.setattr(db, "settings", lambda: {"url": "https://x.supabase.co", "key": "sb_publishable_x"})

    def fail(request, **k):
        raise urllib.error.HTTPError(request.full_url, 400, "bad", {}, None)

    monkeypatch.setattr(db.urllib.request, "urlopen", fail)
    with pytest.raises(db.DBError) as info:
        db.sign_in("someone@example.com", "-".join(["made", "up", "pw"]))  # built at run time
    report = str(info.getrepr(showlocals=True, style="long"))
    assert "made-up-pw" not in str(info.value)
    assert "made-up-pw" not in report  # not in any db.py frame's arguments or locals
    assert "'***'" in report


def test_secret_key_is_refused(monkeypatch):
    monkeypatch.setattr(db.llm, "_load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_secret_abc")
    with pytest.raises(db.DBError, match="SECRET"):
        db.settings()


def test_filter_values_are_quoted():
    assert db.eq("U-20261104-k7f1") == "eq.U-20261104-k7f1"
    assert db.eq("a&b=c") == "eq.a%26b%3Dc"
