"""Translate the screen text (i18n/en.json) into the scheduled languages with Bhashini. Run once:

    .venv/bin/python scripts/translate_ui.py            # every language Bhashini supports
    .venv/bin/python scripts/translate_ui.py ta bn      # only these

Writes i18n/<code>.json, marked "machine translated by Bhashini, not checked". Hindi keeps our own
i18n/hi.json and is never overwritten.

Kept exactly as in English: {placeholders}, numbers (including 112, 1930, 15100), web addresses,
abbreviations (IPC, BNS, DLSA, CNR...), markdown ** and emoji. Only the words between them are sent
for translation, so they cannot be changed. Legal wording (Section 479 reasons, draft phrases,
summaries, eligibility) is NOT translated here: those keys stay English in these files' languages,
and legal text is shown only as a labelled reading copy (see README).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bhashini  # noqa: E402
import lang  # noqa: E402

LEGAL_PREFIXES = ("s479.", "sec.", "draft.", "disclosure.", "elig.", "group.", "next:", "doc:", "sum.", "intake.q.")
PROTECTED = re.compile(
    r"\{\w+\}"                              # {placeholders}
    r"|https?://\S+|\b[\w.-]+\.(?:gov|org|com|in)(?:\.in)?\b"  # web addresses
    r"|\b(?:IPC|BNS|BNSS|DLSA|NALSA|CNR|FIR|SLSA|UPI|OTP|PIN|SMS|AI|SC/ST|SC|ST|ID|Google Gemini|Gemini|"
    r"Bhashini|SUPERVISOR_PASSWORD|\.streamlit/secrets\.toml)\b"
    r"|\d+(?:\(\w+\))*(?:[,.]\d+)*"         # numbers and section numbers: 112, 1930, 15100, 479(2), 1,50,000
    r"|\*\*|[←-⯿☀-➿\U0001F000-\U0001FAFF️—·×₹]"  # markdown, symbols
)


def pieces(text: str):
    """Split text into (is_protected, piece)."""
    out, pos = [], 0
    for m in PROTECTED.finditer(text):
        if m.start() > pos:
            out.append((False, text[pos:m.start()]))
        out.append((True, m.group(0)))
        pos = m.end()
    if pos < len(text):
        out.append((False, text[pos:]))
    return out


def translate_value(text: str, code: str, translate=bhashini.translate) -> str:
    result = []
    for protected, piece in pieces(text):
        stripped = piece.strip()
        if protected or not re.search(r"[A-Za-z]", stripped):
            result.append(piece)
            continue
        lead, trail = piece[:len(piece) - len(piece.lstrip())], piece[len(piece.rstrip()):]
        result.append(lead + translate(stripped, "en", code).text.strip() + trail)
    return "".join(result)


def translate_file(code: str, translate=bhashini.translate) -> dict:
    english = lang.strings("en")
    out = {"_status": lang.MACHINE_STATUS}
    for key, value in english.items():
        if key.startswith(LEGAL_PREFIXES):
            continue  # stays English (see the module note)
        out[key] = translate_value(value, code, translate)
    return out


def main(codes):
    if not bhashini.configured():
        sys.exit("Bhashini is not set up: add BHASHINI_USER_ID and BHASHINI_API_KEY to .env")
    for code in codes or [c for c in bhashini.LANGUAGES if c != "hi"]:
        if code == "hi":
            print("hi: skipped (our own Hindi file is kept)")
            continue
        try:
            data = translate_file(code)
        except bhashini.BhashiniUnavailable as err:
            print(f"{code}: not done ({err})")
            continue
        (ROOT / "i18n" / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{code}: {len(data) - 1} texts written")


if __name__ == "__main__":
    main(sys.argv[1:])
