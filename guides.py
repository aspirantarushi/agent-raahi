"""The Learn page's guides, read from learner/ (plain code, no AI).

Each guide (learner/<file>.md), in this order:
- "You will be able to": two lines
- "Key idea": five short points
- "Worked example": a situation, then numbered steps
- "Practice case ...": core facts, then a model answer
- "Check (5 questions)": each with options, the answer, why, and its source

Every point, step, model-answer line and answer names the knowledge/ entry it comes from, as
[[entry heading]] (an entry of the guide's own knowledge file) or [[file.md#entry heading]]. Plain code
resolves each one to the entry, so its source can be shown as a clickable link; a test fails if an entry
is missing. A guide marked "Status: coming soon" is not shown, only named.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import knowledge

HERE = Path(__file__).resolve().parent
LEARNER = HERE / "learner"
REF = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass(frozen=True)
class Guide:
    key: str            # "legal_aid", "undertrial", "fraud" (also in the page address: ?guide=...)
    learner_file: str   # in learner/
    knowledge_file: str  # in knowledge/
    icon: str
    number: int         # 1..3: the matching Home card ("home.learn1".."home.learn3")


GUIDES = [
    Guide("legal_aid", "legal_aid.md", "legal_aid_eligibility.md", "volunteer_activism", 1),
    Guide("undertrial", "undertrial_bail.md", "undertrial_bail.md", "gavel", 2),
    Guide("fraud", "cyber_fraud.md", "cyber_fraud.md", "phishing", 3),
]
COMING_SOON_TOPICS = ["domestic violence", "wages", "land", "consumer complaints"]


def by_key(key: str):
    return next((g for g in GUIDES if g.key == key), None)


@dataclass
class Source:
    """Where a point comes from: the Act/section as written, and the knowledge/ entries it names."""
    text: str
    refs: List[Tuple[str, str]] = field(default_factory=list)  # (knowledge file, entry heading)

    def links(self) -> List[Tuple[str, str]]:
        """[(label, link or "")]: each named entry's own source and link (no link when it has none)."""
        out = []
        for file, heading in self.refs:
            entry = knowledge.get(file, heading)
            link = entry.link if entry.link and entry.link.lower() != "none" else ""
            out.append((entry.source, link))
        return out


@dataclass
class Point:
    text: str
    source: Source


@dataclass
class Question:
    text: str
    options: List[Tuple[str, str]]  # [("a", "text"), ...]
    answer: str                     # "a".."d"
    why: str
    source: Source


@dataclass
class Practice:
    title: str
    facts: List[str]
    answer: List[Point]


@dataclass
class Content:
    status: str                 # "ready" or "coming soon"
    lawyer_checked: str
    outcomes: List[str] = field(default_factory=list)
    points: List[Point] = field(default_factory=list)
    example_intro: str = ""
    steps: List[Point] = field(default_factory=list)
    practice: List[Practice] = field(default_factory=list)
    quiz: List[Question] = field(default_factory=list)
    why_not_ready: str = ""

    @property
    def ready(self) -> bool:
        return self.status == "ready"


def _sections(text: str) -> List[Tuple[str, List[str]]]:
    found, title = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            found.append((title, []))
        elif title:
            found[-1][1].append(line)
    return found


def _source(text: str, own_file: str) -> Source:
    refs = []
    for ref in REF.findall(text):
        file, _, heading = ref.partition("#") if "#" in ref else (own_file, "", ref)
        refs.append((file.strip(), heading.strip()))
    plain = REF.sub("", text).strip().rstrip(".").strip()
    return Source(plain, refs)


def _numbered(lines: List[str], own_file: str) -> List[Point]:
    """'1. text' then an indented 'Source: ... [[entry]]' line."""
    items, text = [], None
    for line in lines:
        s = line.strip()
        if re.match(r"\d+\.\s", s):
            text = re.sub(r"^\d+\.\s*", "", s)
        elif s.startswith("Source:") and text is not None:
            items.append(Point(text, _source(s[len("Source:"):], own_file)))
            text = None
    return items


def _bullets_with_refs(lines: List[str], own_file: str) -> List[Point]:
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("- "):
            body = s[2:]
            out.append(Point(REF.sub("", body).strip(), _source("".join(f"[[{r}]]" for r in REF.findall(body)), own_file)))
    return out


def _quiz(lines: List[str], own_file: str) -> List[Question]:
    questions = []
    for block in re.split(r"\n\s*\n", "\n".join(lines)):
        rows = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not rows or not re.match(r"\d+\.", rows[0]):
            continue
        get = {k: next((r[len(k) + 1:].strip() for r in rows if r.startswith(k + ":")), "")
               for k in ("Answer", "Why", "Source")}
        options_line = next(r for r in rows[1:] if re.match(r"a\)", r))
        options = [(m.group(1), m.group(2).strip())
                   for m in re.finditer(r"([a-d])\)\s*(.*?)(?=\s+[a-d]\)\s|$)", options_line)]
        questions.append(Question(re.sub(r"^\d+\.\s*", "", rows[0]), options, get["Answer"][:1].lower(),
                                  get["Why"], _source(get["Source"], own_file)))
    return questions


@lru_cache(maxsize=None)
def content(guide_key: str) -> Content:
    """The guide exactly as written in learner/ (nothing added or reworded)."""
    guide = by_key(guide_key)
    text = (LEARNER / guide.learner_file).read_text(encoding="utf-8")
    status = (re.search(r"^Status: (.+)$", text, re.M) or [None, "ready"])[1].strip().lower()
    checked = re.search(r"^Lawyer checked: ([^.\n]+)", text, re.M)
    why = re.search(r"^Why: (.+)$", text, re.M)
    c = Content(status, checked.group(1).strip() if checked else "no", why_not_ready=why.group(1) if why else "")
    if not c.ready:
        return c
    own = guide.knowledge_file
    for title, lines in _sections(text):
        if title.startswith("You will be able to"):
            c.outcomes = [l.strip()[2:] for l in lines if l.strip().startswith("- ")]
        elif title.startswith("Key idea"):
            c.points = _numbered(lines, own)
        elif title.startswith("Worked example"):
            body = [l for l in lines if l.strip()]
            c.example_intro = next((l.strip() for l in body if not re.match(r"\s*(\d+\.|Source:)", l)), "")
            c.steps = _numbered(lines, own)
        elif title.startswith("Practice case"):
            part, facts, answer = None, [], []
            for line in lines:
                s = line.strip()
                if s.startswith("Core facts:"):
                    part = facts
                elif s.startswith("Model answer:"):
                    part = answer
                elif s.startswith("- ") and part is not None:
                    part.append(line)
            c.practice.append(Practice(re.sub(r"^Practice case\s*\d*:\s*", "", title),
                                       [f.strip()[2:] for f in facts], _bullets_with_refs(answer, own)))
        elif title.startswith("Check"):
            c.quiz = _quiz(lines, own)
    return c


def ready_guides() -> List[Guide]:
    return [g for g in GUIDES if content(g.key).ready]


def all_sources(guide_key: str) -> List[Source]:
    """Every source a guide names (for the test that each one resolves to a knowledge/ entry)."""
    c = content(guide_key)
    return ([p.source for p in c.points] + [s.source for s in c.steps] + [q.source for q in c.quiz]
            + [a.source for pr in c.practice for a in pr.answer if not a.text.startswith("Must not")])


def check_answer(q: Question, choice: Optional[str]) -> Optional[bool]:
    """True / False once an option is chosen (plain code: the letter in learner/), None before."""
    return None if not choice else choice == q.answer
