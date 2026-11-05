"""Ready for Streamlit Community Cloud: pinned requirements, no data on the server's disk without
Supabase, and no secret in the repository."""

import re
import subprocess
from pathlib import Path

from streamlit.testing.v1 import AppTest

import storage

ROOT = Path(__file__).resolve().parent.parent


def test_every_requirement_is_pinned():
    lines = [l.split("#")[0].strip() for l in (ROOT / "requirements.txt").read_text().splitlines()]
    reqs = [l for l in lines if l]
    assert reqs and all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][\w.]*", r) for r in reqs), reqs
    names = {r.split("==")[0].lower() for r in reqs}
    assert {"streamlit", "segno", "zxing-cpp", "pillow", "certifi"} <= names
    assert "playwright" not in names  # screenshots only, never online


def test_online_without_supabase_shows_a_red_notice(monkeypatch):
    monkeypatch.setenv("RAAHI_FORCE_CLOUD", "1")
    monkeypatch.setenv("RAAHI_START_SCREEN", "Home")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    assert any("Supabase" in e.value for e in at.error)
    monkeypatch.delenv("RAAHI_FORCE_CLOUD")
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    assert not any("Supabase" in e.value for e in at.error)  # on a computer: local files are fine


def test_no_secret_files_or_keys_are_tracked():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert not [f for f in tracked if f.endswith((".env", "secrets.toml", ".pem", ".key"))]
    key = re.compile(r"AIza[0-9A-Za-z_-]{30,}|gsk_[0-9A-Za-z]{20,}|tvly-[0-9A-Za-z-]{16,}|sb_secret_[0-9A-Za-z_-]{16,}")
    for f in tracked:
        path = ROOT / f
        if path.suffix in (".py", ".md", ".toml", ".txt", ".json", ".sql", ".example", ".csv", ".yml", ".yaml"):
            assert not key.search(path.read_text(encoding="utf-8", errors="ignore")), f


def test_dates_are_india_time_even_on_a_utc_server():
    import os
    import time
    assert os.environ["TZ"] == "Asia/Kolkata" and time.strftime("%z") == "+0530"
