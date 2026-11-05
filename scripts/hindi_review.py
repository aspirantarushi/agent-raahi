"""Build docs/hindi_review.csv: every Hindi line not yet marked checked, for a Hindi speaker to review.

    .venv/bin/python scripts/hindi_review.py

Columns: Where (file and key), English, Hindi now, Type, Checked (blank), Suggested fix (blank).
Rows: legal content first (knowledge_hi/ entries, the Home facts, legal wording in i18n/hi.json), then
drafts (templates_hi/ line by line, draft phrases), then screen text, then practice stories.
Lines that are English on purpose (for example "Home", "Case tracker") are left out. The file is saved
with a byte-order mark, so Excel shows the Devanagari correctly; Google Sheets opens it as it is.
When a line is checked, mark it in the source file (for knowledge_hi/ and templates_hi/, change
"Hindi translation checked: no" to "yes") and run this again.
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import home  # noqa: E402
import knowledge  # noqa: E402

OUT = ROOT / "docs" / "hindi_review.csv"
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LEGAL_KEYS = ("s479.", "elig.", "group.", "next:", "doc:", "intake.q.", "sec.", "step.", "safety.")
DRAFT_KEYS = ("draft.", "disclosure.", "sum.", "cw.", "ready.block_", "q.year", "q.outcome", "q.person")
ORDER = {"legal content": 0, "draft": 1, "screen text": 2, "practice story": 3}
APPLIED = {  # fixes already made from a review, noted so the reviewer can confirm them
    "knowledge_hi/cyber_fraud.md · Call 1930 at once: report immediately":
        "Applied 5 Nov 2026: \"ताकि पैसे धोखेबाज़ों के हाथ लगने से पहले ही रोके जा सकें\"",
    "home.py · Home fact: Call 1930 at once: report immediately":
        "Applied 5 Nov 2026: \"ताकि पैसे धोखेबाज़ों के हाथ लगने से पहले ही रोके जा सकें\"",
}


def i18n_rows():
    en = json.loads((ROOT / "i18n" / "en.json").read_text(encoding="utf-8"))
    hi = json.loads((ROOT / "i18n" / "hi.json").read_text(encoding="utf-8"))
    checked = {k[len("meta.hi_checked."):] for k, v in hi.items() if k.startswith("meta.hi_checked.") and v == "yes"}
    for key, text in hi.items():
        if key.startswith("meta.") or key in checked or not DEVANAGARI.search(text):
            continue
        kind = "legal content" if key.startswith(LEGAL_KEYS) else "draft" if key.startswith(DRAFT_KEYS) \
            else "screen text"
        yield [f"i18n/hi.json · {key}", en.get(key, ""), text, kind]


def knowledge_rows():
    for path in sorted((ROOT / "knowledge_hi").glob("*.md")):
        if path.name == "README.md":
            continue
        knowledge._entries.cache_clear()
        for e in knowledge._entries(path.name, "hi"):
            if e.translation_checked:
                continue
            english = knowledge.get(path.name, e.english_heading)
            yield [f"knowledge_hi/{path.name} · {e.english_heading}", f"{english.heading}\n{english.body}",
                   f"{e.heading}\n{e.body}", "legal content"]


def home_rows():
    for file, heading, _, english, hindi in home.FACTS:
        if english and hindi:
            yield [f"home.py · Home fact: {heading}", english, hindi, "legal content"]


def template_rows():
    for path in sorted((ROOT / "templates_hi").glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines and "checked: yes" in lines[0].lower():
            continue
        english = (ROOT / "templates" / path.name).read_text(encoding="utf-8").splitlines()
        hindi = lines[1:2] + lines[3:]  # without the marker line and the extra Hindi DRAFT line
        pairs = zip(english, hindi) if len(english) == len(hindi) else [("(whole template)", "\n".join(lines[1:]))]
        if len(lines) > 2:
            yield [f"templates_hi/{path.name} · line 2 (Hindi DRAFT line)", "DRAFT — to be checked by a lawyer",
                   lines[2], "draft"]
        for n, (en_line, hi_line) in enumerate(pairs, 1):
            if DEVANAGARI.search(hi_line):
                yield [f"templates_hi/{path.name} · line {n}", en_line, hi_line, "draft"]


def story_rows():
    for path in [ROOT / "case_notes_hi.txt", *sorted((ROOT / "practice_stories").glob("*hinglish*.txt"))]:
        if path.exists():
            yield [f"{path.relative_to(ROOT)}", "(fake practice story; check that it reads naturally)",
                   path.read_text(encoding="utf-8").strip(), "practice story"]


def main():
    rows = [*knowledge_rows(), *home_rows(), *template_rows(), *i18n_rows(), *story_rows()]
    rows.sort(key=lambda r: (ORDER[r[3]], r[0].split(" · ")[0]))
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Where (file and key)", "English", "Hindi now", "Type", "Checked", "Suggested fix"])
        for r in rows:
            w.writerow(r + ["", APPLIED.get(r[0], "")])
    counts = {}
    for r in rows:
        counts[r[3]] = counts.get(r[3], 0) + 1
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} lines", counts)


if __name__ == "__main__":
    main()
