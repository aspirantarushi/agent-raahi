"""Screen and draft text in more than one language. Plain code.

All text the app shows (labels, buttons, warnings, questions, safety messages) and the fixed
phrases in drafts come from one file per language: i18n/en.json, i18n/hi.json. To add a
language, copy en.json to a new file (for example i18n/bn.json), translate the values, and add
it to LANGUAGES. A key missing from a translation falls back to English.
"""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Dict

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "i18n"
LANGUAGES: Dict[str, str] = {"en": "English", "hi": "हिंदी"}  # हिंदी
DEFAULT = "en"

HINDI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च",
                "अप्रैल", "मई", "जून", "जुलाई",
                "अगस्त", "सितंबर", "अक्टूबर",
                "नवंबर", "दिसंबर"]


@lru_cache(maxsize=None)
def strings(code: str) -> Dict[str, str]:
    path = FOLDER / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def t(key: str, code: str = DEFAULT, **params) -> str:
    """The text for a key in a language (English if the language lacks it)."""
    text = strings(code).get(key) if code in LANGUAGES else None
    if text is None:
        text = strings(DEFAULT)[key]  # a key missing from English is a bug: fail loudly
    return text.format(**params) if params else text


def show_date(d: date, code: str = DEFAULT) -> str:
    """15 July 2026 / 15 जुलाई 2026 (digits stay 0-9, so they can be checked against English)."""
    if code == "hi":
        return f"{d.day} {HINDI_MONTHS[d.month - 1]} {d.year}"
    return f"{d.day} {d.strftime('%B %Y')}"
