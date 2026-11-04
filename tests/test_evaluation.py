"""Evaluation mode: 10 fictional cases with answer keys, timed sessions, reviewer scores, raw CSV."""

import csv
import functools
import io
import json
import subprocess
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import evaluation
import privacy

ROOT = Path(__file__).resolve().parent.parent


def test_ten_fictional_cases_of_each_kind():
    cases = evaluation.cases()
    assert len(cases) == 10
    kinds = {c["category"] for c in cases}
    assert kinds == {"easy", "incomplete", "contradictory", "out of scope"}
    for c in cases:
        assert c["story"].startswith("Practice case (fictional).")
        assert c["required"] and c["must_not"] and c["workflow"] in ("Any case", "Section 479 aid")
        assert not privacy.personal_details_found(c["story"])


def test_answer_keys_agree_with_the_calculator():
    from datetime import date
    import section479
    for case_id, law, sec, custody, offence, third, half in [
            ("E1", "BNS", "115(2)", date(2026, 1, 10), date(2026, 1, 5), "10 May 2026", "10 July 2026"),
            ("O2", "BNS", "305", date(2025, 6, 3), date(2025, 6, 1), "3 October 2027", "3 December 2028")]:
        r = section479.calculate(section479.find_offences(law, sec)[0], custody, date(2026, 11, 4), True, False, False,
                                 offence_date=offence)
        key = json.dumps(evaluation.case(case_id)["required"])
        assert f"{r.one_third.when.day} {r.one_third.when:%B %Y}" == third and third in key
        assert f"{r.one_half.when.day} {r.one_half.when:%B %Y}" == half and half in key


def test_by_hand_session_timed_and_scored(tmp_path, monkeypatch):
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "cases").symlink_to(ROOT / "evaluation" / "cases")
    s = evaluation.start("E2", evaluation.BY_HAND, "Volunteer 1", base=tmp_path, started="2026-11-05T10:00:00")
    evaluation.finish(s["session_id"], {"Problem": "wages", "notes": "call 9876543210"}, base=tmp_path,
                      finished="2026-11-05T10:12:30")
    done = evaluation.load(s["session_id"], base=tmp_path)
    assert evaluation.minutes(done) == 12.5
    assert "9876543210" not in json.dumps(done)  # personal numbers filtered even in practice
    evaluation.score(s["session_id"], "Reviewer R", 4, 1, 0, True, base=tmp_path)
    rows = list(csv.reader(io.StringIO(evaluation.export_csv(base=tmp_path))))
    assert rows == [evaluation.CSV_COLUMNS, ["E2", "by hand", "Reviewer R", "12.5", "2", "1", "0", "yes"]]


def test_export_has_only_raw_counts_no_averages(tmp_path):
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "cases").symlink_to(ROOT / "evaluation" / "cases")
    assert evaluation.export_csv(base=tmp_path).strip() == ",".join(evaluation.CSV_COLUMNS)  # nothing invented
    for method, volunteer in ((evaluation.BY_HAND, "Volunteer 1"), (evaluation.WITH_AGENT, "Volunteer 2")):
        s = evaluation.start("C1", method, volunteer, base=tmp_path)
        evaluation.finish(s["session_id"], {"x": "y"}, base=tmp_path)
    assert len(evaluation.export_csv(base=tmp_path).strip().splitlines()) == 1  # unscored: no rows
    text = evaluation.export_csv(base=tmp_path).lower()
    assert "average" not in text and "mean" not in text


def test_rules_for_sessions_and_scores(tmp_path):
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "cases").symlink_to(ROOT / "evaluation" / "cases")
    with pytest.raises(ValueError, match="pseudonym"):
        evaluation.start("E1", evaluation.BY_HAND, " ", base=tmp_path)
    with pytest.raises(ValueError, match="No such evaluation case"):
        evaluation.start("Z9", evaluation.BY_HAND, "V1", base=tmp_path)
    s = evaluation.start("E1", evaluation.BY_HAND, "V1", base=tmp_path)
    with pytest.raises(ValueError, match="only after it is finished"):
        evaluation.score(s["session_id"], "R", 1, 0, 0, True, base=tmp_path)
    evaluation.finish(s["session_id"], {}, base=tmp_path)
    with pytest.raises(ValueError, match="already finished"):
        evaluation.finish(s["session_id"], {}, base=tmp_path)
    with pytest.raises(ValueError, match="8 required fields"):
        evaluation.score(s["session_id"], "R", 9, 0, 0, True, base=tmp_path)
    evaluation.score(s["session_id"], "R", 8, 0, 0, True, base=tmp_path)
    evaluation.score(s["session_id"], "R", 7, 1, 1, False, base=tmp_path)  # the same reviewer revises
    assert len(evaluation.load(s["session_id"], base=tmp_path)["scores"]) == 1


def test_sessions_stay_out_of_git():
    assert subprocess.run(["git", "check-ignore", "-q", "evaluation/sessions/S-1.json"], cwd=ROOT).returncode == 0
    assert subprocess.run(["git", "check-ignore", "-q", "evaluation/cases/E1.json"], cwd=ROOT).returncode == 1


@pytest.fixture
def eval_folder(monkeypatch, tmp_path):
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "cases").symlink_to(ROOT / "evaluation" / "cases")
    for name in ("cases", "case", "start", "load", "finish", "sessions", "score", "export_csv"):
        monkeypatch.setattr(evaluation, name, functools.partial(getattr(evaluation, name), base=tmp_path))
    return tmp_path


def test_screen_by_hand(eval_folder):
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.sidebar.radio[0].set_value("Evaluation").run()
    at.selectbox(key="ev-case").set_value("E2")
    at.radio(key="ev-method").set_value("by hand")
    at.text_input(key="ev-volunteer").set_value("Volunteer 1").run()
    next(b for b in at.button if b.label.startswith("Start (records")).click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert "domestic worker" in at.code[0].value
    at.text_input(key="ev-field-0").set_value("unpaid wages").run()
    next(b for b in at.button if b.label.startswith("Finish")).click().run()
    [session] = evaluation.sessions(finished_only=True)
    assert session["submission"]["Problem"] == "unpaid wages"


def test_screen_with_agent_stops_when_sent(eval_folder, monkeypatch, tmp_path):
    from datetime import date
    import store
    original = store.submit
    monkeypatch.setattr(store, "submit", lambda *a, **k: original(*a, base=tmp_path, **k))
    at = AppTest.from_file("../app.py", default_timeout=20).run()
    at.sidebar.radio[0].set_value("Evaluation").run()
    at.selectbox(key="ev-case").set_value("O2")
    at.radio(key="ev-method").set_value("with the agent")
    at.text_input(key="ev-volunteer").set_value("Volunteer 2").run()
    next(b for b in at.button if b.label.startswith("Start (records")).click().run()
    at.sidebar.radio[0].set_value("New case").run()
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_input(key="f_section").set_value("305")
    at.selectbox(key="f_law").set_value("BNS")
    at.date_input(key="f_offence_date").set_value(date(2025, 6, 1))
    at.date_input(key="f_custody").set_value(date(2025, 6, 3))
    at.checkbox(key="f_never").check().run()
    at.radio(key="f_lawyer").set_value("Legal aid lawyer").run()
    next(b for b in at.button if b.label == "Make draft").click().run()
    at.button(key="send-f").click().run()
    assert not at.exception, at.exception[0].stack_trace
    [session] = evaluation.sessions(finished_only=True)
    assert session["method"] == "with the agent" and session["submission"]["agent_case"].startswith("U-")
