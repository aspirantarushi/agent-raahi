"""Practice Clinic only: a snapshot of the practice cases, and "Reset the Practice Clinic".

The live app runs as the "Agent Raahi Practice Clinic" with fictional stories. After people have tried it,
the supervisor can put every practice case back to how it was when the snapshot was taken. None of this
exists unless CLINIC_NAME contains "Practice": in a real clinic it is never shown and never runs.

A snapshot is saved in the app's own storage (kind "practice_snapshot", never in git):
- "latest": {"taken_at", "by", "parts": [ids], "counts": {kind: n}, "resets": [{"at", "by"}]}
- the parts: pieces of one JSON text {kind: {record id: record text}}, each under the size limit of a record.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

import storage

KIND = "practice_snapshot"
LATEST = "latest"
CASE_KINDS = ("pending", "drafts", "cases", "audit", "timelines", "tracker", "research", "knowledge_added")
PART_SIZE = 100_000  # characters per part (a record may hold up to 200,000, and saving it adds escape characters)


class PracticeError(Exception):
    """The message is safe to show."""


def is_practice() -> bool:
    return "practice" in storage.setting("CLINIC_NAME").lower()


def _need_practice():
    if not is_practice():
        raise PracticeError("Only the Practice Clinic can be reset.")


def latest(base=None) -> Optional[dict]:
    return storage.read_json(KIND, LATEST, base)


def take_snapshot(by: str, base=None, now: Optional[datetime] = None) -> dict:
    """Save every practice case record as it is now. Replaces the earlier snapshot (keeping its reset log)."""
    _need_practice()
    backend = storage.backend(base)
    data: Dict[str, Dict[str, str]] = {kind: dict(backend.all(kind)) for kind in CASE_KINDS}
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    parts = []
    for n, start in enumerate(range(0, len(text), PART_SIZE), 1):
        part_id = f"snap-{stamp}-p{n}"
        backend.write(KIND, part_id, json.dumps({"text": text[start:start + PART_SIZE]}, ensure_ascii=False))
        parts.append(part_id)
    old = latest(base) or {}
    manifest = {"taken_at": (now or datetime.now()).isoformat(timespec="minutes"), "by": by, "parts": parts,
                "counts": {kind: len(records) for kind, records in data.items()}, "resets": old.get("resets", [])}
    storage.write_json(KIND, LATEST, manifest, base)
    for part_id in old.get("parts", []):  # the earlier snapshot's pieces are no longer needed
        if part_id not in parts:
            backend.delete(KIND, part_id)
    return manifest


def snapshot_data(base=None) -> Dict[str, Dict[str, str]]:
    manifest = latest(base)
    if not manifest:
        raise PracticeError("No practice snapshot has been saved yet.")
    backend = storage.backend(base)
    pieces: List[str] = []
    for part_id in manifest["parts"]:
        body = backend.read(KIND, part_id)
        if body is None:
            raise PracticeError("The practice snapshot is incomplete, so nothing was changed.")
        pieces.append(json.loads(body)["text"])
    return json.loads("".join(pieces))


def reset(by: str, base=None, now: Optional[datetime] = None) -> dict:
    """Put every practice case back to the snapshot: records added since are removed, changed ones restored.
    Who did it and when is kept in the snapshot's reset log. Returns {kind: records restored}."""
    _need_practice()
    data = snapshot_data(base)  # read it all first: nothing changes if it can't be read
    backend = storage.backend(base)
    restored = {}
    for kind in CASE_KINDS:
        keep = data.get(kind, {})
        for record_id in backend.ids(kind):
            if record_id not in keep:
                backend.delete(kind, record_id)
        for record_id, text in keep.items():
            backend.write(kind, record_id, text)
        restored[kind] = len(keep)
    manifest = latest(base)
    manifest.setdefault("resets", []).append({"at": (now or datetime.now()).isoformat(timespec="minutes"), "by": by})
    storage.write_json(KIND, LATEST, manifest, base)
    return restored
