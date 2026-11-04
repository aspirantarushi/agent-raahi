"""Finding and removing personal numbers. Plain code, no AI.

Used before case notes are sent to the AI, and before drafts are saved.
Names can't be detected reliably, so volunteers are told not to type them.
"""

import re
from typing import Dict, List, Tuple

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?![\w])")
AADHAAR = re.compile(r"(?<![\w])\d{4}[\s-]?\d{4}[\s-]?\d{4}(?![\w])")

# Order matters: emails first (they can contain digits), then Aadhaar (12 digits), then phones.
PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (EMAIL, "an email address", "[email removed]"),
    (AADHAAR, "an Aadhaar number", "[Aadhaar number removed]"),
    (PHONE, "a phone number", "[phone number removed]"),
]


def personal_details_found(text: str) -> List[str]:
    """Labels of the kinds of personal numbers found, for example ['a phone number']."""
    return [label for pattern, label, _ in PATTERNS if pattern.search(text)]


def redact(text: str) -> Tuple[str, Dict[str, int]]:
    """Replace emails, Aadhaar numbers and phone numbers. Returns the clean text and
    how many of each were removed."""
    removed: Dict[str, int] = {}
    for pattern, label, placeholder in PATTERNS:
        text, n = pattern.subn(placeholder, text)
        if n:
            removed[label] = n
    return text, removed
