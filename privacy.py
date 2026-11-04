"""Finding and removing personal numbers. Plain code, no AI.

Used before case notes are sent to the AI, and before drafts are saved.
Names can't be detected reliably, so volunteers are told not to type them.
"""

import re
from typing import Dict, List, Tuple

import sys
import unicodedata


def _all_digits_table() -> dict:
    """Every decimal digit in Unicode (Devanagari, Bengali/Assamese, Gurmukhi, Gujarati, Odia, Tamil,
    Telugu, Kannada, Malayalam, Ol Chiki, Meetei Mayek, Arabic-Indic for Urdu/Kashmiri/Sindhi, and
    every other script) mapped to 0-9, so numbers are checked the same in every language."""
    table = {}
    for cp in range(sys.maxunicode + 1):
        ch = chr(cp)
        if unicodedata.category(ch) == "Nd" and not ("0" <= ch <= "9"):
            table[cp] = str(unicodedata.decimal(ch))
    return table


ALL_DIGITS = _all_digits_table()
DEVANAGARI_DIGITS = ALL_DIGITS  # kept for older code: it now covers every script

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Digits may be split by single spaces, hyphens or dots anywhere ("98 76 54 32 10", "9876-543-210").
_SEP = r"[ .-]?"
# Only English letters and digits next to a number stop a match (so "CNR DLCT010012342024" is kept), while a
# number written straight after a word in any Indian script ("नंबर९८७६५४३२१०") is still caught.
_B, _A = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"
PHONE_INTL = re.compile(rf"\+{_SEP}9{_SEP}1{_SEP}[6-9](?:{_SEP}[0-9]){{9}}{_A}")  # +91 ...
PHONE = re.compile(rf"{_B}(?:9{_SEP}1{_SEP}|0{_SEP})?[6-9](?:{_SEP}[0-9]){{9}}{_A}")
# Any 12 digits (real Aadhaar numbers start with 2-9, but a mistyped one should still be caught).
AADHAAR = re.compile(rf"{_B}[0-9](?:{_SEP}[0-9]){{11}}{_A}")
_THREE_YEARS = re.compile(r"(?:19|20)\d\d[ .-](?:19|20)\d\d[ .-](?:19|20)\d\d")

# Order matters: emails first (they can contain digits), "+91" phones, then Aadhaar (12 digits), then phones.
PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (EMAIL, "an email address", "[email removed]"),
    (PHONE_INTL, "a phone number", "[phone number removed]"),
    (AADHAAR, "an Aadhaar number", "[Aadhaar number removed]"),
    (PHONE, "a phone number", "[phone number removed]"),
]


def _is_personal(match: re.Match) -> bool:
    return not _THREE_YEARS.fullmatch(match.group(0))  # "2024 2025 2026" is three years, not Aadhaar


def normalise_digits(text: str) -> str:
    """Digits of every script become 0-9 (for example ৯৮৭, ੯੮੭, ૯૮૭, ୯୮୭, ௯௮௭, ౯౮౭, ೯೮೭, ൯൮൭, ᱙᱘᱗)."""
    return text.translate(ALL_DIGITS)


# Hindi letters with a dot below (ज़, फ़, ड़ ...) can be typed two ways; for comparing words, drop the dot.
_NUKTA = str.maketrans({"\u093c": None, "\u0958": "\u0915", "\u0959": "\u0916", "\u095a": "\u0917",
                        "\u095b": "\u091c", "\u095c": "\u0921", "\u095d": "\u0922", "\u095e": "\u092b",
                        "\u095f": "\u092f"})


def comparable(text: str) -> str:
    """Text for comparing words: 0-9 digits, no Hindi dot-below, lower case, single spaces."""
    import re as _re
    return _re.sub(r"\s+", " ", normalise_digits(text or "").translate(_NUKTA)).strip().casefold()


def personal_details_found(text: str) -> List[str]:
    """Labels of the kinds of personal numbers found, for example ['a phone number']."""
    return list(redact(text)[1])  # the same steps as redact, so the two always agree


def redact(text: str) -> Tuple[str, Dict[str, int]]:
    """Replace emails, Aadhaar numbers and phone numbers. Returns the clean text and
    how many of each were removed."""
    removed: Dict[str, int] = {}
    text = normalise_digits(text)  # Devanagari digits become 0-9, so they are checked like any other
    for pattern, label, placeholder in PATTERNS:
        count = 0

        def replace(m: re.Match) -> str:
            nonlocal count
            if not _is_personal(m):
                return m.group(0)
            count += 1
            return placeholder

        text = pattern.sub(replace, text)
        if count:
            removed[label] = removed.get(label, 0) + count
    return text, removed
