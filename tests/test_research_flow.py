"""The new order for problems our files don't cover: research -> shown to the volunteer (who can untick
points, never add or edit them) -> letter drafted from the ticked points -> everything to the supervisor,
who decides each point; the letter is then rebuilt from the approved points. Fake data only."""

import casework
import general
import research
import store
import tracker
from test_research import BIHAR_POINTS, BIHAR_RAW, resolve  # noqa: F401

G = general.GeneralFacts(person="a woman", what_happened=["The electricity line was cut without notice."],
                         timeline=[("1 October 2026", "connection cut")], coming_dates=[],
                         issues=[("electricity_or_water", "electricity connection cut")], sections=[],
                         documents_held=["latest bill"], answers=[], still_to_ask=[],
                         facts={"state": "Bihar", "woman": True}, today="2026-11-06", outcome="the connection restored")


def brief(tmp_path, monkeypatch):
    import llm
    monkeypatch.setattr(llm, "research_issue", lambda s, i: BIHAR_RAW)
    monkeypatch.setattr(llm, "split_brief", lambda b: ([dict(p) for p in BIHAR_POINTS], "gemini-test"))
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    return case_id, research.run(case_id, "Bihar", "electricity connection cut", "Volunteer A", base=tmp_path,
                                 resolve=resolve)


def test_letter_is_drafted_from_the_ticked_points_only(tmp_path, monkeypatch):
    _, record = brief(tmp_path, monkeypatch)
    ids = [p["id"] for p in record["points"] if p["kind"] != "letter"]
    points = research.points_for_letter(record, {ids[0]: True, ids[1]: False})
    assert [p["text"] for p in points] == [record["points"][0]["text"]]
    letter = casework.complaint_letter(G, points, "electricity connection cut", "gemini-test")
    assert letter.startswith("DRAFT — to be checked by a lawyer")
    assert record["points"][0]["text"] in letter and record["points"][1]["text"] not in letter
    assert "AI research, not yet checked by a lawyer" in letter
    # No legal claim in the letter beyond the ticked point
    body = letter.split("---")[0]
    assert casework.legal_claims(body) == [] or all(c in points[0]["text"] for c in casework.legal_claims(body))


def test_points_naming_a_replaced_law_start_unticked(tmp_path, monkeypatch):
    _, record = brief(tmp_path, monkeypatch)
    p = dict(record["points"][0], warnings=[{"kind": "replaced", "text": "x", "old": "a", "new": "b"}])
    assert research.default_keep(p) is False and research.default_keep(record["points"][1]) is True


def test_the_volunteers_choices_reach_the_supervisor_and_the_audit(tmp_path, monkeypatch):
    case_id, record = brief(tmp_path, monkeypatch)
    ids = [p["id"] for p in record["points"] if p["kind"] != "letter"]
    research.volunteer_review(record["id"], {ids[0]: True, ids[1]: False}, {ids[1]: "wrong office"}, "Volunteer A",
                              base=tmp_path)
    saved = research.load(record["id"], tmp_path)
    assert saved["points"][0]["volunteer"] == research.KEPT
    assert saved["points"][1]["volunteer"] == research.LEFT_OUT and saved["points"][1]["volunteer_reason"] == "wrong office"
    assert saved["status"] == research.WAITING  # nothing is final: the supervisor still decides each point
    import audit
    assert any(e["event"] == "research looked at by the volunteer" for e in audit.read_record(case_id, base=tmp_path)["events"])


def test_letter_is_taken_out_when_every_point_is_rejected(tmp_path):
    case_id = tracker.open_case("General", "Volunteer A", base=tmp_path)["id"]
    letter = casework.complaint_letter(G, [{"kind": "route", "text": "Write to the office.", "unchecked": True,
                                            "sources": [{"title": "t", "url": "https://energy.bihar.gov.in/"}]}],
                                       "electricity connection cut", None)
    summary = general.make_summary_draft(G, None)
    store.submit(casework.bundle([("s", summary), ("l", letter)]), G, base=tmp_path, case_id=case_id, by="Volunteer A")
    assert store.get_pending(case_id, tmp_path)["draft"].count("DRAFT — to be checked by a lawyer") == 2
    store.remove_letter(case_id, tmp_path)
    assert store.get_pending(case_id, tmp_path)["draft"].count("DRAFT — to be checked by a lawyer") == 1


def test_a_point_whose_source_is_a_replaced_law_is_flagged_and_starts_unticked():
    p = {"kind": "route", "text": "A single application may be presented under section 15 of the Act.",
         "sources": [{"title": "10 (1) THE PAYMENT OF WAGES ACT, 1936", "url": "https://www.indiacode.nic.in/x"}]}
    [w] = research.point_warnings(p, "Punjab")
    assert w["kind"] == "replaced" and w.get("in_source") and "Code on Wages, 2019" in w["text"]
    assert research.default_keep(dict(p, warnings=[w])) is False and research.blocked(dict(p, warnings=[w]))
    haryana = {"kind": "route", "text": "x", "sources": [{"title": "t", "url": "https://hrylabour.gov.in/a.pdf"}]}
    assert [w["kind"] for w in research.point_warnings(haryana, "Punjab")] == ["other_state"]
