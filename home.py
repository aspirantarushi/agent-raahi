"""Home page facts: exact sentences from knowledge/ with their Source lines. Plain code.

Each fact names a knowledge entry and a sentence that must appear in it word for word. If an entry
changes and the sentence no longer appears, an error is raised (and a test fails) instead of
showing a legal point that is not in our verified files. No pilot figures until they are measured.
"""

from typing import List, Optional, Tuple

import knowledge

# (file, English heading, English sentence, Hindi sentence from knowledge_hi/ or None)
FACTS = [
    ("legal_aid_eligibility.md", "Who qualifies for free legal aid",
     "Women, children and people in custody qualify whatever their income.", None),
    ("legal_aid_eligibility.md", "How long a decision takes",
     "A decision must be taken immediately, and within seven days of receiving the application at most.", None),
    ("undertrial_bail.md", "Section 479: release after a share of the maximum sentence",
     "No undertrial can be held beyond the full maximum term.", None),
    ("cyber_fraud.md", "Call 1930 at once: the first hours matter most",
     "Report as early as possible, ideally within a few hours: the faster the report, the better the chance "
     "the money can be stopped before the fraudster withdraws it.",
     "जितनी जल्दी हो सके शिकायत करें, हो सके तो कुछ घंटों के अंदर: शिकायत जितनी जल्दी होगी, धोखेबाज़ के पैसे "
     "निकालने से पहले उन्हें रोकने का मौक़ा उतना ज़्यादा होगा।"),
]


def facts(code: str = "en") -> List[Tuple[str, str]]:
    """[(sentence, Source line)] in the language when a Hindi entry has it, else in English."""
    out = []
    for file, heading, english, hindi in FACTS:
        entry = knowledge.get(file, heading)
        if english not in " ".join(entry.body.split()):
            raise ValueError(f"Home fact not found word for word in knowledge/{file}: {heading}")
        sentence = english
        if code == "hi" and hindi:
            hi_entry = knowledge.get(file, heading, "hi")
            if hi_entry.lang == "hi" and hindi in " ".join(hi_entry.body.split()):
                sentence = hindi
        out.append((sentence, entry.source_line))
    return out
