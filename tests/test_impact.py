"""Impact log for real use: only with permission; practice cases refused; facts from the app's records."""

import csv
import io
import subprocess
from datetime import date
from pathlib import Path

import pytest

import evaluation
import impact
import timeline
from test_timeline import approve_undertrial

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def base(tmp_path):
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "cases").symlink_to(ROOT / "evaluation" / "cases")
    return tmp_path


def test_logged_with_permission_and_facts_from_records(base):
    case_id = approve_undertrial(base)
    timeline.record_submission(case_id, "Para-legal volunteer", date(2026, 11, 6), "in person", base=base)
    timeline.record_acknowledgement(case_id, "DLSA", date(2026, 11, 7), "Diary 451/2026", "PLV", base=base)
    entry = impact.log(case_id, "Practice Clinic Alpha", True, "letter of 5 Nov 2026", "Clear draft", base=base)
    assert entry["permission"] == "given" and entry["workflow"] == "Section 479 aid"
    assert entry["review_outcome"] == "approved"
    assert (entry["referral_by_authorised_worker"], entry["referral_on"]) == ("yes", "2026-11-06")
    assert (entry["external_acknowledgement"], entry["acknowledgement_reference"]) == ("yes", "Diary 451/2026")
    assert entry["started"] and entry["ended"]
    rows = list(csv.DictReader(io.StringIO(impact.export_csv(base))))
    assert rows[0]["case_id"] == case_id and rows[0]["permission_reference"] == "letter of 5 Nov 2026"


def test_refused_without_permission(base):
    case_id = approve_undertrial(base)
    with pytest.raises(ValueError, match="permission"):
        impact.log(case_id, "Clinic", False, "letter", base=base)
    with pytest.raises(ValueError, match="how permission was given"):
        impact.log(case_id, "Clinic", True, " ", base=base)
    assert impact.entries(base) == []


def test_practice_cases_are_refused(base):
    case_id = approve_undertrial(base)
    s = evaluation.start("E1", evaluation.WITH_AGENT, "Volunteer 1", base=base)
    evaluation.finish(s["session_id"], {"agent_case": case_id, "draft": "x"}, base=base)
    with pytest.raises(ValueError, match="practice"):
        impact.log(case_id, "Clinic", True, "letter", base=base)


def test_no_duplicates_and_privacy(base):
    case_id = approve_undertrial(base)
    impact.log(case_id, "Clinic", True, "letter", "call 9876543210", base=base)
    assert "9876543210" not in impact.export_csv(base)
    with pytest.raises(ValueError, match="already"):
        impact.log(case_id, "Clinic", True, "letter", base=base)


def test_impact_log_out_of_git():
    assert subprocess.run(["git", "check-ignore", "-q", "impact/log.jsonl"], cwd=ROOT).returncode == 0
