"""Reading entries from the verified knowledge files. Plain code.

Each entry in knowledge/*.md starts with "### Heading", has some text, and ends with
"Source:", "Link:" and "Checked:" lines. Legal points shown to users come only from here.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
KNOWLEDGE = HERE / "knowledge"
KNOWLEDGE_HI = HERE / "knowledge_hi"


@dataclass(frozen=True)
class Entry:
    file: str      # e.g. "cyber_fraud.md"
    heading: str
    body: str      # the entry's text, without the Source / Link / Checked lines
    source: str
    link: str
    checked: str
    lang: str = "en"
    english_heading: str = ""                 # Hindi entries: the English entry they translate
    translation_checked: Optional[bool] = None  # Hindi entries: "Hindi translation checked: yes/no"

    @property
    def source_line(self) -> str:
        line = f"Source: {self.source}"
        if self.link and self.link.lower() != "none":
            line += f" ({self.link})"
        return line

    def excerpt(self, max_lines: int = 6) -> str:
        """The first lines of the entry, as written in the file."""
        lines = [l for l in self.body.splitlines() if l.strip()]
        return "\n".join(lines[:max_lines])


@lru_cache(maxsize=None)
def _entries(file: str, lang: str = "en") -> Tuple[Entry, ...]:
    path = (KNOWLEDGE_HI if lang == "hi" else KNOWLEDGE) / file
    if not path.exists():
        return ()
    text = path.read_text(encoding="utf-8")
    entries, heading, body, meta = [], None, [], {}

    def close():
        if heading is not None and meta.get("source"):
            checked = meta.get("hindi translation checked")
            entries.append(Entry(file, heading, "\n".join(body).strip(), meta.get("source", ""),
                                 meta.get("link", ""), meta.get("checked", ""), lang,
                                 meta.get("english heading", ""),
                                 None if checked is None else checked.strip().lower() == "yes"))

    for line in text.splitlines():
        if line.startswith("### "):
            close()
            heading, body, meta = line[4:].strip(), [], {}
        elif heading is not None:
            for key in ("English heading", "Source", "Link", "Checked", "Hindi translation checked"):
                if line.startswith(key + ":"):
                    meta[key.lower()] = line[len(key) + 1:].strip()
                    break
            else:
                if not (set(meta) - {"english heading"}):  # text after the Source line belongs to no entry
                    body.append(line)
    close()
    return tuple(entries)


def entries(file: str) -> List[Entry]:
    return list(_entries(file))


def get(file: str, heading: str, lang: str = "en") -> Entry:
    """The entry with this (English) heading. With lang="hi", its Hindi version from knowledge_hi/
    if there is one, otherwise the English entry."""
    if lang == "hi":
        for e in _entries(file, "hi"):
            if e.english_heading == heading:
                return e
    for e in _entries(file):
        if e.heading == heading:
            return e
    raise KeyError(f"No entry '{heading}' with a Source line in knowledge/{file}")


def hindi_entries() -> List[Entry]:
    return [e for path in sorted(KNOWLEDGE_HI.glob("*.md")) if path.name != "README.md"
            for e in _entries(path.name, "hi")]


def all_text() -> str:
    """Every knowledge entry's text and Source line (used to check where legal references come from)."""
    parts = []
    for path in sorted(KNOWLEDGE.glob("*.md")):
        parts.append(path.read_text(encoding="utf-8"))
    for path in sorted(KNOWLEDGE.glob("*.csv")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
