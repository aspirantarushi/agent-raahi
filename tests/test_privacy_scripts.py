"""Phone, Aadhaar and email numbers are caught in every Indian script, before anything leaves the app."""

import pytest

import privacy

PHONE = "9876543210"
AADHAAR = "234567890123"
SCRIPTS = {  # the digits 0-9 in each script
    "Devanagari": "०१२३४५६७८९", "Bengali/Assamese": "০১২৩৪৫৬৭৮৯", "Gurmukhi": "੦੧੨੩੪੫੬੭੮੯",
    "Gujarati": "૦૧૨૩૪૫૬૭૮૯", "Odia": "୦୧୨୩୪୫୬୭୮୯", "Tamil": "௦௧௨௩௪௫௬௭௮௯", "Telugu": "౦౧౨౩౪౫౬౭౮౯",
    "Kannada": "೦೧೨೩೪೫೬೭೮೯", "Malayalam": "൦൧൨൩൪൫൬൭൮൯", "Ol Chiki (Santali)": "᱐᱑᱒᱓᱔᱕᱖᱗᱘᱙",
    "Meetei Mayek (Manipuri)": "꯰꯱꯲꯳꯴꯵꯶꯷꯸꯹", "Extended Arabic-Indic (Urdu, Kashmiri)": "۰۱۲۳۴۵۶۷۸۹",
    "Arabic-Indic (Sindhi)": "٠١٢٣٤٥٦٧٨٩", "Limbu": "᥆᥇᥈᥉᥊᥋᥌᥍᥎᥏", "Lepcha": "᱀᱁᱂᱃᱄᱅᱆᱇᱈᱉",
}


def in_script(number: str, digits: str) -> str:
    return "".join(digits[int(d)] for d in number)


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("number, kind", [(PHONE, "a phone number"), (AADHAAR, "an Aadhaar number")])
def test_numbers_in_every_script_are_removed(script, number, kind):
    written = in_script(number, SCRIPTS[script])
    for text in (f"number {written} here", f"{written[:5]} {written[5:]}", " ".join(written)):
        clean, removed = privacy.redact(text)
        assert removed == {kind: 1}, (script, text)
        assert not privacy.personal_details_found(clean)


@pytest.mark.parametrize("text", ["नंबर९८७६५४३२१०", "எண்௯௮௭௬௫௪௩௨௧௦", "ফোন৯৮৭৬৫৪৩২১০ আছে", "فون۹۸۷۶۵۴۳۲۱۰"])
def test_numbers_written_straight_after_a_word_are_removed(text):
    assert privacy.redact(text)[1] == {"a phone number": 1}


@pytest.mark.parametrize("text", ["CNR DLCT010012342024", "FIR 123/2024", "case U-20261103-k7f1", "₹৪০,০০০",
                                  "১৫ মার্চ ২০২৪", "2024 2025 2026", "IPC ৩৮০", "84 months"])
def test_case_numbers_dates_and_amounts_are_kept(text):
    assert privacy.redact(text)[1] == {}


def test_every_unicode_digit_is_covered():
    import unicodedata
    for cp, value in privacy.ALL_DIGITS.items():
        assert unicodedata.decimal(chr(cp)) == int(value)
    assert len(privacy.ALL_DIGITS) > 600


def test_emails_in_any_language_text():
    assert privacy.redact("ইমেল didi@example.com দিন")[1] == {"an email address": 1}
