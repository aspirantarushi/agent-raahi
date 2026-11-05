"""Where saved records live: plain files on this computer, or the clinic's Supabase table.

Every module that saves something (store, audit, timeline, tracker, evaluation, impact) goes
through this file, so the app works the same either way.

- Local files (the default, and always in tests): pending/, drafts/, cases/, audit/, timelines/,
  tracker/, problems/, impact/, evaluation/sessions/ in the app folder (or RAAHI_DATA_DIR).
- Supabase: one table, raahi_records (supabase/tracker.sql), used only from the app's server with
  the secret key from the host's secret settings. Row level security is on with no public access,
  so nothing can be read from outside the app.

Supabase is used when SUPABASE_URL and SUPABASE_SECRET_KEY are set and RAAHI_STORAGE is not
"local". Tests set RAAHI_STORAGE=local (tests/conftest.py), so they never touch real data.
"""

import json
import os
import re
import secrets as _secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
TIMEOUT_SECONDS = 30

# kind -> (folder, file extension) for records saved one per file
FILES: Dict[str, Tuple[str, str]] = {
    "pending": ("pending", ".json"),
    "drafts": ("drafts", ".md"),
    "cases": ("cases", ".md"),
    "audit": ("audit", ".json"),
    "timelines": ("timelines", ".json"),
    "tracker": ("tracker", ".json"),
    "eval_sessions": ("evaluation/sessions", ".json"),
}
# kind -> file for logs (one entry per line)
LOGS: Dict[str, str] = {
    "problems": "problems/problems.jsonl",
    "impact": "impact/log.jsonl",
}


class StorageError(Exception):
    """Saving or reading failed. The message is safe to show."""


def setting(name: str) -> str:
    """A setting from the environment, the .env file, or .streamlit/secrets.toml (host secret settings)."""
    value = os.environ.get(name, "").strip()
    if value or os.environ.get("RAAHI_TEST"):
        return value  # tests never read the real .env or secrets file (it would copy real passwords in)
    try:
        import llm
        llm._load_dotenv()
        value = os.environ.get(name, "").strip()
        if value:
            return value
    except Exception:
        pass
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:  # no secrets file
        return ""


# ---------- local files ----------

class LocalFiles:
    name = "local files"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, kind: str, record_id: str) -> Path:
        folder, ext = FILES[kind]
        if "/" in record_id or "\\" in record_id or ".." in record_id:
            raise StorageError("Not a valid record name.")
        return self.root / folder / f"{record_id}{ext}"

    def read(self, kind: str, record_id: str) -> Optional[str]:
        path = self._path(kind, record_id)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write(self, kind: str, record_id: str, text: str) -> None:
        """Write via a temporary file, so a half-written file is never left behind."""
        path = self._path(kind, record_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    def delete(self, kind: str, record_id: str) -> bool:
        path = self._path(kind, record_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def ids(self, kind: str) -> List[str]:
        folder, ext = FILES[kind]
        directory = self.root / folder
        if not directory.exists():
            return []
        return sorted(p.name[: -len(ext)] for p in directory.glob(f"*{ext}"))

    def all(self, kind: str) -> List[Tuple[str, str]]:
        return [(i, self.read(kind, i) or "") for i in self.ids(kind)]

    # logs
    def _log(self, kind: str) -> Path:
        return self.root / LOGS[kind]

    def log_append(self, kind: str, entry: dict) -> None:
        path = self._log(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_entries(self, kind: str) -> List[dict]:
        path = self._log(kind)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def log_remove(self, kind: str, matches: Callable[[dict], bool]) -> int:
        entries = self.log_entries(kind)
        kept = [e for e in entries if not matches(e)]
        if len(kept) != len(entries):
            path = self._log(kind)
            tmp = path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in kept), encoding="utf-8")
            os.replace(tmp, path)
        return len(entries) - len(kept)


# ---------- Supabase (server side only, secret key) ----------

class Supabase:
    name = "Supabase"
    TABLE = "raahi_records"

    def __init__(self, url: str, key: str):
        self.url, self.key = url.rstrip("/"), key

    def _request(self, method: str, query: str, body=None, prefer: str = "") -> object:
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):  # an older-style service key also needs this header
            headers["Authorization"] = f"Bearer {self.key}"
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(f"{self.url}/rest/v1/{self.TABLE}?{query}", data=data, headers=headers,
                                         method=method)
        try:
            import llm
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=llm._ssl_context()) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            try:
                detail = json.loads(err.read() or b"{}")
            except Exception:
                detail = {}
            message = str(detail.get("message") or "")
            if "no_personal_numbers" in message:
                raise StorageError("Refused: the text seems to contain a phone number, Aadhaar number or email "
                                   "address.") from None
            raise StorageError(f"The online case store refused the request (error {err.code}). "
                               + message[:200]) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise StorageError("Could not reach the online case store. Check the internet and try again.") from None
        return json.loads(raw) if raw else None

    @staticmethod
    def _eq(value: str) -> str:
        return "eq." + urllib.parse.quote(str(value), safe="")

    def read(self, kind: str, record_id: str) -> Optional[str]:
        rows = self._request("GET", f"kind={self._eq(kind)}&id={self._eq(record_id)}&select=body") or []
        return rows[0]["body"] if rows else None

    def write(self, kind: str, record_id: str, text: str) -> None:
        self._request("POST", "on_conflict=kind,id",
                      [{"kind": kind, "id": record_id, "body": text, "updated_at": datetime.now().astimezone().isoformat()}],
                      prefer="resolution=merge-duplicates,return=minimal")

    def delete(self, kind: str, record_id: str) -> bool:
        rows = self._request("DELETE", f"kind={self._eq(kind)}&id={self._eq(record_id)}",
                             prefer="return=representation") or []
        return bool(rows)

    def all(self, kind: str) -> List[Tuple[str, str]]:
        rows = self._request("GET", f"kind={self._eq(kind)}&select=id,body&order=id.asc") or []
        return [(r["id"], r["body"]) for r in rows]

    def ids(self, kind: str) -> List[str]:
        rows = self._request("GET", f"kind={self._eq(kind)}&select=id&order=id.asc") or []
        return [r["id"] for r in rows]

    def log_append(self, kind: str, entry: dict) -> None:
        record_id = f"{datetime.now():%Y%m%dT%H%M%S%f}-{_secrets.token_hex(3)}"
        self.write(kind, record_id, json.dumps(entry, ensure_ascii=False))

    def log_entries(self, kind: str) -> List[dict]:
        return [json.loads(body) for _, body in self.all(kind)]

    def log_remove(self, kind: str, matches: Callable[[dict], bool]) -> int:
        removed = 0
        for record_id, body in self.all(kind):
            if matches(json.loads(body)):
                self.delete(kind, record_id)
                removed += 1
        return removed


# ---------- choosing ----------

def supabase_settings() -> Tuple[str, str]:
    url, key = setting("SUPABASE_URL"), setting("SUPABASE_SECRET_KEY")
    # Supabase's Data API page shows the address with /rest/v1/ on the end: accept it as pasted.
    url = re.sub(r"/rest/v1/?$", "", url.rstrip("/")).rstrip("/")
    if key and not (key.startswith("sb_secret_") or key.startswith("eyJ")):
        raise StorageError("SUPABASE_SECRET_KEY doesn't look like a Supabase secret key (it starts with sb_secret_).")
    return url, key


def online() -> bool:
    """True when the clinic's Supabase table is used for the app's own records."""
    if os.environ.get("RAAHI_STORAGE", "").strip().lower() == "local":
        return False
    url, key = supabase_settings()
    return bool(url and key)


def data_dir() -> Path:
    return Path(os.environ.get("RAAHI_DATA_DIR") or HERE)


def backend(base: Optional[Path] = None):
    """The store for a base folder. The app's own folder (the default) goes online when set up;
    any other folder (tests, practice copies) is always local files."""
    if base is None or Path(base).resolve() == HERE:
        if online():
            return Supabase(*supabase_settings())
        return LocalFiles(data_dir())
    return LocalFiles(Path(base))


def read_json(kind: str, record_id: str, base: Optional[Path] = None) -> Optional[dict]:
    text = backend(base).read(kind, record_id)
    return json.loads(text) if text else None


def write_json(kind: str, record_id: str, record: dict, base: Optional[Path] = None) -> None:
    backend(base).write(kind, record_id, json.dumps(record, indent=2, ensure_ascii=False, default=str))


def all_json(kind: str, base: Optional[Path] = None) -> List[dict]:
    return [json.loads(text) for _, text in backend(base).all(kind) if text]
