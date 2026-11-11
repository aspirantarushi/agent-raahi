"""The Learn page's three guides, read from learner/ (plain code, no AI).

Each guide: the read-aloud explainer and the quiz and practice cases from learner/<file>.md, plus the
key points from the matching verified file in knowledge/, each with its Source line (in Hindi from
knowledge_hi/ where a Hindi version exists; otherwise the English entry is shown).
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List

import knowledge

HERE = Path(__file__).resolve().parent
LEARNER = HERE / "learner"


@dataclass(frozen=True)
class Guide:
    key: str            # "legal_aid", "undertrial", "fraud" (also in the page address: ?guide=...)
    learner_file: str   # in learner/
    knowledge_file: str  # in knowledge/ (and knowledge_hi/)
    icon: str
    number: int         # 1..3: the matching Home card ("home.learn1".."home.learn3")


GUIDES = [
    Guide("legal_aid", "legal_aid.md", "legal_aid_eligibility.md", "volunteer_activism", 1),
    Guide("undertrial", "undertrial_bail.md", "undertrial_bail.md", "gavel", 2),
    Guide("fraud", "cyber_fraud.md", "cyber_fraud.md", "phishing", 3),
]


def by_key(key: str):
    return next((g for g in GUIDES if g.key == key), None)


@dataclass
class Question:
    text: str
    options: str
    answer: str


@dataclass
class Content:
    lawyer_checked: str
    explainer: str
    quiz: List[Question] = field(default_factory=list)
    practice: List[tuple] = field(default_factory=list)  # (title, text as written)


def _sections(text: str) -> dict:
    found, title = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            found[title] = []
        elif title:
            found[title].append(line)
    return {k: "\n".join(v).strip() for k, v in found.items()}


@lru_cache(maxsize=None)
def content(guide_key: str) -> Content:
    """The guide's text exactly as written in learner/ (nothing added or reworded)."""
    guide = by_key(guide_key)
    text = (LEARNER / guide.learner_file).read_text(encoding="utf-8")
    checked = re.search(r"^Lawyer checked: ([^.\n]+)", text, re.M)
    parts = _sections(text)
    explainer = next((v for k, v in parts.items() if k.startswith("Explainer")), "")
    quiz_text = next((v for k, v in parts.items() if k.startswith("Quiz")), "")
    quiz = []
    for block in re.split(r"\n\s*\n", quiz_text):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if len(lines) >= 3 and re.match(r"\d+\.", lines[0]) and lines[-1].startswith("Answer:"):
            quiz.append(Question(re.sub(r"^\d+\.\s*", "", lines[0]), " ".join(lines[1:-1]),
                                 lines[-1][len("Answer:"):].strip()))
    practice = [(k, v) for k, v in parts.items() if k.startswith("Practice case")]
    return Content(checked.group(1).strip() if checked else "no", explainer, quiz, practice)


def key_points(guide_key: str, lang: str = "en") -> List[knowledge.Entry]:
    """Every entry of the guide's verified knowledge file, with its Source line. In Hindi, the Hindi
    version from knowledge_hi/ where there is one (it keeps the same Source, Link and Checked lines)."""
    guide = by_key(guide_key)
    return [knowledge.get(guide.knowledge_file, e.heading, lang) for e in knowledge.entries(guide.knowledge_file)]
