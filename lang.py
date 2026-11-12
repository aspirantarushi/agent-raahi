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
# Every scheduled language, named in its own script (shown in the language switch).
NATIVE_NAMES: Dict[str, str] = {
    "en": "English", "hi": "हिंदी", "as": "অসমীয়া", "bn": "বাংলা", "brx": "बड़ो", "doi": "डोगरी",
    "gu": "ગુજરાતી", "kn": "ಕನ್ನಡ", "ks": "كٲشُر", "gom": "कोंकणी", "mai": "मैथिली", "ml": "മലയാളം",
    "mni": "ꯃꯤꯇꯩꯂꯣꯟ", "mr": "मराठी", "ne": "नेपाली", "or": "ଓଡ଼ିଆ", "pa": "ਪੰਜਾਬੀ", "sa": "संस्कृतम्",
    "sat": "ᱥᱟᱱᱛᱟᱲᱤ", "sd": "سنڌي", "ta": "தமிழ்", "te": "తెలుగు", "ur": "اردو",
}
CHECKED_LANGUAGES = ("en", "hi")  # our own, checked wording; the others are machine translated
MACHINE_STATUS = "machine translated by Bhashini, not checked"
DEFAULT = "en"


def _available() -> Dict[str, str]:
    """English, Hindi, then every language with an i18n/<code>.json file, each in its own script."""
    codes = ["en", "hi"] + sorted(p.stem for p in FOLDER.glob("*.json")
                                  if p.stem in NATIVE_NAMES and p.stem not in ("en", "hi"))
    return {c: NATIVE_NAMES[c] for c in codes}


# For the planned pilot, languages are frozen at English and Hindi. The Bhashini code stays; set this to False (and run
# scripts/translate_ui.py) to offer the machine-translated languages again.
PILOT_FREEZE = True
PILOT_LANGUAGES = ("en", "hi")


def _offered() -> Dict[str, str]:
    found = _available()
    return {c: n for c, n in found.items() if c in PILOT_LANGUAGES} if PILOT_FREEZE else found


LANGUAGES: Dict[str, str] = _offered()


def is_machine_translated(code: str) -> bool:
    return code not in CHECKED_LANGUAGES

HINDI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च",
                "अप्रैल", "मई", "जून", "जुलाई",
                "अगस्त", "सितंबर", "अक्टूबर",
                "नवंबर", "दिसंबर"]


@lru_cache(maxsize=None)
def strings(code: str) -> Dict[str, str]:
    path = FOLDER / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# The count that decides singular or plural, when it is not {n}
PLURAL_BY = {"aud.count": "total", "tr.count": "total"}


def t(key: str, code: str = DEFAULT, **params) -> str:
    """The text for a key in a language (English if the language lacks it). A count of exactly 1 uses the
    key's ".one" form when there is one ("1 case still at intake", not "1 cases")."""
    count = params.get(PLURAL_BY.get(key, "n"))
    if count == 1 and f"{key}.one" in strings(DEFAULT):
        key = f"{key}.one"
    text = strings(code).get(key) if code in LANGUAGES else None
    if text is None:
        text = strings(DEFAULT)[key]  # a key missing from English is a bug: fail loudly
    return text.format(**params) if params else text


def show_date(d: date, code: str = DEFAULT) -> str:
    """15 July 2026 / 15 जुलाई 2026 (digits stay 0-9, so they can be checked against English)."""
    if code == "hi":
        return f"{d.day} {HINDI_MONTHS[d.month - 1]} {d.year}"
    return f"{d.day} {d.strftime('%B %Y')}"
