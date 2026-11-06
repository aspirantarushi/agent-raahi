"""Research searches under the law in force today, and a facts-only request letter when no research
point is ticked. Fake data only; no real search."""

import casework
import general
import llm
import replaced_laws
import research
import tracker
from test_research import BIHAR_POINTS, BIHAR_RAW, resolve  # noqa: F401

WAGES = general.GeneralFacts(
    person="the worker", what_happened=["The employer stopped paying salary after 30 September.",
                                        "A complaint can be made under Section 15 of the Act."],
    timeline=[("30 September 2026", "salary stopped")], coming_dates=[], issues=[("wages_or_work", "unpaid wages")],
    sections=[], documents_held=["attendance card photo"], answers=[], still_to_ask=[], facts={"state": "Punjab"},
    today="2026-11-06", outcome="his three months' wages paid")


def test_the_search_names_the_law_in_force_today():
    assert replaced_laws.search_text("unpaid wages") == "unpaid wages (current law: Code on Wages, 2019)"
    assert "Code on Wages, 2019" in replaced_laws.search_text("teen mahine ki tankhwah nahi mili")
    assert "Bharatiya Nagarik Suraksha Sanhita, 2023" in replaced_laws.search_text("brother arrested, needs bail")
    assert replaced_laws.search_text("electricity connection cut") == "electricity connection cut"
    assert replaced_laws.search_text("claim under the Code on Wages") == "claim under the Code on Wages"  # once only


def test_research_run_sends_the_current_law_with_the_problem(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "research_issue", lambda s, i: sent.append((s, i)) or BIHAR_RAW)
    monkeypatch.setattr(llm, "split_brief", lambda b: ([dict(p) for p in BIHAR_POINTS], "gemini-test"))
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    record = research.run(case_id, "Punjab", "unpaid wages", "Volunteer A", base=tmp_path, resolve=resolve)
    assert sent == [("Punjab", "unpaid wages (current law: Code on Wages, 2019)")]
    assert record["issue"] == "unpaid wages" and record["searched_as"].endswith("(current law: Code on Wages, 2019)")


def test_facts_only_letter_has_no_legal_points():
    letter = casework.facts_only_letter(WAGES, "unpaid wages", "gemini-test")
    assert letter.startswith("DRAFT — to be checked by a lawyer\n\nFacts-only letter: no legal points yet; "
                             "the supervisor may add them.")
    assert "[Name and address of the Labour Department office for the district]" in letter
    assert "Section 15" not in letter and casework.legal_claims(letter.split("---")[0]) == []
    assert "The employer stopped paying salary after 30 September." in letter
    assert "I request: his three months' wages paid" in letter
    assert "[Name of the person]" in letter and "[Signature or thumb impression]" in letter
    hi = casework.facts_only_letter(WAGES, "unpaid wages", "gemini-test", "hi")
    assert "सिर्फ़ तथ्यों वाला पत्र" in hi and "श्रम विभाग" in hi


def test_facts_only_letter_names_the_office_type_for_electricity():
    g = general.GeneralFacts(person="a woman", what_happened=["The electricity line was cut."],
                             timeline=[], coming_dates=[], issues=[("electricity_or_water", "electricity connection cut")],
                             sections=[], documents_held=[], answers=[], still_to_ask=[], facts={"state": "Bihar"},
                             today="2026-11-06", outcome="")
    letter = casework.facts_only_letter(g, "electricity connection cut", None)
    assert "electricity company's grievance office" in letter
    assert "[What the person asks the office to do]" in letter  # what they want is not known: a visible blank
