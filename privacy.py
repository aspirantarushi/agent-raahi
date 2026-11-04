"""Finding and removing personal numbers. Plain code, no AI.

Used before case notes are sent to the AI, and before drafts are saved.
Names can't be detected reliably, so volunteers are told not to type them.
"""

import re
from typing import Dict, List, Tuple

# Devanagari digits ० १ २ ३ ४ ५ ६ ७ ८ ९ are read as 0-9 before checking.
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Digits may be split by single spaces, hyphens or dots anywhere ("98 76 54 32 10", "9876-543-210").
_SEP = r"[ .-]?"
PHONE_INTL = re.compile(rf"\+{_SEP}9{_SEP}1{_SEP}[6-9](?:{_SEP}\d){{9}}(?![\w])")  # +91 ...
PHONE = re.compile(rf"(?<![\w])(?:9{_SEP}1{_SEP}|0{_SEP})?[6-9](?:{_SEP}\d){{9}}(?![\w])")
# Any 12 digits (real Aadhaar numbers start with 2-9, but a mistyped one should still be caught).
AADHAAR = re.compile(rf"(?<![\w])\d(?:{_SEP}\d){{11}}(?![\w])")
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
    return text.translate(DEVANAGARI_DIGITS)


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
