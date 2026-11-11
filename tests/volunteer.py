"""What a volunteer presses, for screen tests: nothing that produces a result happens by itself."""

import multilingual


def language_of(text: str) -> str:
    """The language a volunteer would confirm for these notes (the app's suggestion, or English)."""
    return multilingual.detect_language(text or "") or "en"


def choose_language(at, text_key: str = "g_notes", language: str = None):
    """Confirm the notes' language (the app only suggests it)."""
    key = {"g_notes": "g_notes_lang", "f_notes": "f_notes_lang"}[text_key]
    if any(s.key == key for s in at.selectbox):
        at.selectbox(key=key).set_value(language or language_of(at.session_state[text_key]
                                                                 if text_key in at.session_state else ""))
    return at


def _press(at, key):
    found = [b for b in at.button if b.key == key]
    if found and not found[0].disabled:
        found[0].click().run()
        return True
    return False


def calculate(at):
    """Section 479: "Calculate the dates" (after "I have checked every field")."""
    _press(at, "f-calc")
    return at


def make_drafts(at, letter: bool = True):
    """Step 3: "Make the drafts", and "Draft the letter" when there is one to draft."""
    _press(at, "drafts-go")
    if letter:
        _press(at, "letter-go")
    return at
