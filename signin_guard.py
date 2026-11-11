"""Too many wrong passwords: lock the sign-in for a while. Plain code, kept in the app's memory.

After 5 wrong tries the sign-in is locked for 5 minutes ("Too many tries; wait 5 minutes"). Tries are
counted for the browser session and, as a second check, for the device's network address, so reloading
the page does not start again from zero. The address limit is higher (20), because volunteers at a
camp often share one phone hotspot: one person's typos should not lock everyone out.

Nothing is saved to disk; a restart of the app clears the counts.
"""

import math
import threading
import time
from typing import Dict, Iterable, Optional

MAX_TRIES = 5
SHARED_MAX_TRIES = 20  # per network address (shared by everyone on one hotspot)
LOCK_SECONDS = 5 * 60

_lock = threading.Lock()
_tries: Dict[str, dict] = {}  # key -> {"fails": [times], "until": time or 0}


def _limit(key: str) -> int:
    return SHARED_MAX_TRIES if key.startswith("ip:") else MAX_TRIES


def seconds_locked(keys: Iterable[Optional[str]], now: Optional[float] = None) -> int:
    """How long the sign-in stays locked for any of these keys (0 = not locked)."""
    now = time.time() if now is None else now
    with _lock:
        left = [_tries[k]["until"] - now for k in keys if k and k in _tries]
    return max([0] + [math.ceil(x) for x in left if x > 0])


def failed(keys: Iterable[Optional[str]], now: Optional[float] = None) -> bool:
    """Count one wrong try. True if this try locked the sign-in."""
    now = time.time() if now is None else now
    locked_now = False
    with _lock:
        for k in filter(None, keys):
            entry = _tries.setdefault(k, {"fails": [], "until": 0})
            entry["fails"] = [t for t in entry["fails"] if now - t < LOCK_SECONDS] + [now]
            if len(entry["fails"]) >= _limit(k):
                entry.update(until=now + LOCK_SECONDS, fails=[])
                locked_now = True
    return locked_now


def succeeded(keys: Iterable[Optional[str]]) -> None:
    """A right password: the session's count starts again (the shared address count is kept)."""
    with _lock:
        for k in filter(None, keys):
            if not k.startswith("ip:"):
                _tries.pop(k, None)


def reset_all() -> None:
    """For tests."""
    with _lock:
        _tries.clear()
