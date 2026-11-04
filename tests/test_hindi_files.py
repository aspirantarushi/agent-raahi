"""Hindi knowledge entries and templates must match the English ones on every number."""

import re
from pathlib import Path

import pytest

import knowledge
import privacy

ROOT = Path(__file__).resolve().parent.parent
HINDI_ENTRIES = knowledge.hindi_entries()
TEMPLATES = ["section479_note.md", "dlsa_application.md"]
MARKER = re.compile(r"^<!-- Hindi translation checked: (yes|no) -->$")


def numbers(text: str):
    """Every number in a text, with section brackets: '479(3)', '2024', '15100', '35(3)'."""
    return sorted(re.findall(r"\d+(?:\(\w+\))*", privacy.normalise_digits(text)))


def test_there_are_hindi_entries_for_every_entry_the_app_shows():
    import general
    shown = {(f, h) for items in general.ISSUE_KNOWLEDGE.values() for f, h in items}
    shown |= set(general.ISSUE_DOCUMENTS.values())
    have = {(e.file, e.english_heading) for e in HINDI_ENTRIES}
    assert shown <= have, shown - have


@pytest.mark.parametrize("entry", HINDI_ENTRIES, ids=lambda e: f"{e.file}:{e.english_heading}")
def test_hindi_entry_matches_english(entry):
    english = knowledge.get(entry.file, entry.english_heading)  # raises if the heading is wrong
    assert english.lang == "en"
    assert numbers(entry.body) == numbers(english.body)
    assert (entry.source, entry.link, entry.checked) == (english.source, english.link, english.checked)
    assert entry.translation_checked is not None, "missing 'Hindi translation checked:' line"
    assert re.search(r"[ऀ-ॿ]", entry.body), "the Hindi entry has no Hindi text"


@pytest.mark.parametrize("name", TEMPLATES)
def test_hindi_template_matches_english(name):
    english = (ROOT / "templates" / name).read_text(encoding="utf-8")
    hindi_lines = (ROOT / "templates_hi" / name).read_text(encoding="utf-8").splitlines()
    assert MARKER.match(hindi_lines[0]), "first line must be the 'Hindi translation checked' marker"
    hindi = "\n".join(hindi_lines[1:])
    assert hindi.startswith("DRAFT — to be checked by a lawyer\n")
    assert numbers(hindi) == numbers(english)


def test_number_check_catches_a_wrong_section():
    assert numbers("धारा 479(3)") != numbers("धारा 479(2)")
    assert numbers("१५ मार्च २०२४") == numbers("15 March 2024")
