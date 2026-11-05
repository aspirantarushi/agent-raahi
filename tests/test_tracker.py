"""The shared case tracker (plain code): slip codes, facts known, contradictions, visits, camps, list."""

from datetime import date

import pytest

import storage
import store
import tracker
from test_drafts import practice_facts


def opened(tmp_path, case_type="General", by="AS"):
    return tracker.open_case(case_type, by, base=tmp_path)


# ---------- slip code ----------

def test_code_is_six_easy_characters():
    for _ in range(300):
        code = tracker.new_code(set())
        assert len(code) == 6 and not set(code) & set("0O1I")
        assert set(code) <= set(tracker.CODE_ALPHABET)


def test_codes_are_unique_and_typed_codes_are_tidied(tmp_path):
    codes = {opened(tmp_path)["code"] for _ in range(25)}
    assert len(codes) == 25
    assert tracker.normalise_code(" k7m-2qx ") == "K7M2QX"
    with pytest.raises(tracker.TrackerError, match="never use 0, O, 1 or I"):
        tracker.normalise_code("K7M0QX")
    with pytest.raises(tracker.TrackerError, match="6 letters"):
        tracker.normalise_code("K7M2")


def test_find_by_code(tmp_path):
    record = opened(tmp_path)
    assert tracker.find_by_code(record["code"].lower(), base=tmp_path)["id"] == record["id"]
    with pytest.raises(tracker.TrackerError, match="No case has this code"):
        tracker.find_by_code("ZZZZZZ", base=tmp_path)


def test_opening_needs_a_volunteer_and_is_audited(tmp_path):
    with pytest.raises(tracker.TrackerError, match="name or initials"):
        tracker.open_case("General", "  ", base=tmp_path)
    record = opened(tmp_path)
    assert record["created_by"] == "AS" and store.ID_PATTERN.match(record["id"])
    assert (tmp_path / "tracker" / f"{record['id']}.json").exists()
    import audit
    assert audit.read_record(record["id"], base=tmp_path)["events"][0]["event"] == "case opened (intake started)"


# ---------- facts ----------

def test_second_volunteer_sees_facts_and_is_not_asked_again(tmp_path):
    import general
    record = opened(tmp_path, by="Volunteer A")
    tracker.merge_facts(record["id"], {"state": "Bihar", "woman": True, "today": date(2026, 11, 5)},
                        "Volunteer A", "notes", base=tmp_path)
    again = tracker.load(record["id"], base=tmp_path)
    facts = tracker.known_for_form(again)
    assert facts == {"state": "Bihar", "woman": True}   # today's date is never saved as a fact
    assert again["facts"]["state"]["by"] == "Volunteer A"
    # Volunteer B continues: only facts still missing are asked; "woman" settles eligibility.
    assert general.check_eligibility(facts).missing == []
    tracker.merge_facts(record["id"], {"state": "Bihar", "annual_income": 90000}, "Volunteer B", "answer",
                        base=tmp_path)
    after = tracker.load(record["id"], base=tmp_path)
    assert after["facts"]["state"]["by"] == "Volunteer A"           # unchanged, not re-added
    assert after["facts"]["annual_income"]["by"] == "Volunteer B"
    assert tracker.volunteers(after) == ["Volunteer A", "Volunteer B"]


def test_undertrial_known_facts_are_not_asked_again(tmp_path):
    import intake
    record = opened(tmp_path, "Undertrial")
    tracker.merge_facts(record["id"], {"custody_began": date(2024, 3, 15), "law": "IPC", "section": "380",
                                       "never_convicted": True}, "AS", "notes", base=tmp_path)
    values = tracker.known_for_form(tracker.load(record["id"], base=tmp_path))
    assert values["custody_began"] == date(2024, 3, 15)
    missing = intake.missing_facts(values)
    assert "custody_began" not in missing and "section" not in missing and "never_convicted" not in missing
    assert "other_cases_pending" in missing


def test_a_contradiction_is_flagged_not_saved_over(tmp_path):
    record = opened(tmp_path, "Undertrial", by="Volunteer A")
    tracker.merge_facts(record["id"], {"custody_began": date(2024, 3, 15)}, "Volunteer A", "notes", base=tmp_path)
    conflicts = tracker.merge_facts(record["id"], {"custody_began": date(2024, 4, 15)}, "Volunteer B", "notes",
                                    base=tmp_path)
    assert len(conflicts) == 1 and conflicts[0]["earlier"]["value"] == "2024-03-15"
    assert conflicts[0]["new"]["value"] == "2024-04-15" and conflicts[0]["new"]["by"] == "Volunteer B"
    saved = tracker.load(record["id"], base=tmp_path)
    assert saved["facts"]["custody_began"]["value"] == "2024-03-15"     # earlier value kept until resolved
    assert len(tracker.open_conflicts(saved)) == 1
    # the same new value again doesn't add a second contradiction
    tracker.merge_facts(record["id"], {"custody_began": date(2024, 4, 15)}, "Volunteer B", "notes", base=tmp_path)
    assert len(tracker.open_conflicts(tracker.load(record["id"], base=tmp_path))) == 1

    tracker.resolve(record["id"], "custody_began", "new", "Volunteer B", base=tmp_path)
    saved = tracker.load(record["id"], base=tmp_path)
    assert saved["facts"]["custody_began"]["value"] == "2024-04-15" and not tracker.open_conflicts(saved)
    import audit
    events = [e["event"] for e in audit.read_record(record["id"], base=tmp_path)["events"]]
    assert "contradiction found" in events and "contradiction resolved" in events


def test_text_is_cleaned_of_personal_numbers(tmp_path):
    record = opened(tmp_path)
    tracker.add_answers(record["id"], [("Who has the papers?", "Call 9876543210 for them")], "AS", base=tmp_path)
    tracker.add_visit(record["id"], date(2026, 11, 4), "AS", "phone call", learned="Email x@y.com was given",
                      base=tmp_path, today=date(2026, 11, 5))
    text = (tmp_path / "tracker" / f"{record['id']}.json").read_text(encoding="utf-8")
    assert "9876543210" not in text and "x@y.com" not in text


def test_confirm_facts_records_corrections(tmp_path):
    record = opened(tmp_path, "Undertrial")
    tracker.merge_facts(record["id"], {"section": "380"}, "AS", "notes", base=tmp_path)
    changed = tracker.confirm_facts(record["id"], {"section": "379", "law": "IPC"}, "RK", base=tmp_path)
    assert changed == ["section: 380 → 379"]
    assert tracker.load(record["id"], base=tmp_path)["facts"]["section"]["by"] == "RK"


# ---------- visits and camps ----------

def test_visit_log(tmp_path):
    record = opened(tmp_path)
    tracker.add_visit(record["id"], date(2026, 11, 4), "AS", "camp visit", learned="Wages unpaid since June",
                      done="Listed documents", next_step="Bring the attendance photos", next_due=date(2026, 11, 10),
                      base=tmp_path, today=date(2026, 11, 5))
    visit = tracker.load(record["id"], base=tmp_path)["visits"][0]
    assert (visit["on"], visit["by"], visit["how"], visit["next_due"]) == ("2026-11-04", "AS", "camp visit", "2026-11-10")
    with pytest.raises(tracker.TrackerError, match="future"):
        tracker.add_visit(record["id"], date(2026, 12, 1), "AS", "phone call", learned="x", base=tmp_path,
                          today=date(2026, 11, 5))
    with pytest.raises(tracker.TrackerError, match="Choose how"):
        tracker.add_visit(record["id"], date(2026, 11, 4), "AS", "letter", learned="x", base=tmp_path)
    with pytest.raises(tracker.TrackerError, match="Write what"):
        tracker.add_visit(record["id"], date(2026, 11, 4), "AS", "phone call", base=tmp_path)


def test_camp_tag(tmp_path):
    record = opened(tmp_path)
    camp = tracker.set_camp(record["id"], "Rampur", "Patna", date(2026, 11, 2), "AS", base=tmp_path)
    assert tracker.camp_label(camp) == "Rampur, Patna (2026-11-02)"
    with pytest.raises(tracker.TrackerError, match="village and district"):
        tracker.set_camp(record["id"], "", "Patna", date(2026, 11, 2), "AS", base=tmp_path)


# ---------- the tracker list ----------

def test_rows_status_next_step_overdue_and_filters(tmp_path):
    today = date(2026, 11, 5)
    a = opened(tmp_path, by="AS")                              # intake not finished, overdue visit step
    tracker.add_visit(a["id"], date(2026, 10, 20), "AS", "camp visit", next_step="Collect the FIR copy",
                      next_due=date(2026, 10, 30), base=tmp_path, today=today)
    tracker.set_camp(a["id"], "Rampur", "Patna", date(2026, 10, 20), "AS", base=tmp_path)
    b = opened(tmp_path, "Undertrial", by="RK")                # sent to the supervisor
    facts = practice_facts()
    store.submit("DRAFT — to be checked by a lawyer\n\nx", facts, base=tmp_path, case_id=b["id"], by="RK")
    rows = {r["id"]: r for r in tracker.rows(base=tmp_path, today=today)}
    assert rows[a["id"]]["status"] == tracker.INTAKE and rows[a["id"]]["overdue"] is True
    assert rows[a["id"]]["next_step"] == "Collect the FIR copy" and rows[a["id"]]["camp"].startswith("Rampur")
    assert rows[b["id"]]["status"] == store.WAITING and rows[b["id"]]["overdue"] is False
    every = list(rows.values())
    assert [r["id"] for r in tracker.filter_rows(every, hide_intake=True)] == [b["id"]]
    assert [r["id"] for r in tracker.filter_rows(every, volunteer="AS")] == [a["id"]]
    assert [r["id"] for r in tracker.filter_rows(every, camp=rows[a["id"]]["camp"])] == [a["id"]]
    assert [r["id"] for r in tracker.filter_rows(every, status=store.WAITING)] == [b["id"]]


def test_send_uses_the_case_number_from_the_slip(tmp_path):
    record = opened(tmp_path, "Undertrial")
    case_id = store.submit("DRAFT — to be checked by a lawyer\n\nx", practice_facts(), base=tmp_path,
                           case_id=record["id"], by="AS")
    assert case_id == record["id"]
    with pytest.raises(ValueError, match="already has a draft"):
        store.submit("DRAFT — to be checked by a lawyer\n\nx", practice_facts(), base=tmp_path,
                     case_id=record["id"], by="AS")


def test_delete_removes_the_tracker_record(tmp_path):
    record = opened(tmp_path)
    store.delete_case(record["id"], base=tmp_path)
    assert tracker.load(record["id"], base=tmp_path) is None


# ---------- the slip ----------

def test_slip_never_shows_the_case_type_or_problem(tmp_path):
    record = opened(tmp_path)
    tracker.add_summary(record["id"], ["The husband hits her."], [("other", "domestic violence")], [], "AS",
                        base=tmp_path)
    tracker.merge_facts(record["id"], {"woman": True, "danger_now": False}, "AS", "notes", base=tmp_path)
    record = tracker.load(record["id"], base=tmp_path)
    lines = tracker.slip_lines(record, "Rampur legal aid clinic")
    assert set(lines) == {"clinic", "case_id", "code", "bring_en", "bring_hi", "help_112", "help_15100"}
    shown = " ".join(lines.values()).casefold()
    for word in ("general", "undertrial", "violence", "husband", "domestic", "woman", "479", "bail"):
        assert word not in shown
    assert lines["bring_en"] == "Bring this next time" and lines["bring_hi"] == "अगली बार यह साथ लाएँ"


def test_qr_holds_only_the_link_with_the_code():
    assert tracker.continue_link("https://raahi.example.app/", "K7M2QX") == "https://raahi.example.app/?code=K7M2QX"
    assert tracker.continue_link("", "K7M2QX") == "K7M2QX"
    assert tracker.qr_png_data_uri("https://raahi.example.app", "K7M2QX").startswith("data:image/png;base64,")


# ---------- storage choice ----------

def test_tests_never_use_supabase(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_fake")
    assert storage.online() is False                        # RAAHI_STORAGE=local in conftest
    assert isinstance(storage.backend(tmp_path), storage.LocalFiles)
    monkeypatch.setenv("RAAHI_STORAGE", "")
    assert storage.online() is True and isinstance(storage.backend(), storage.Supabase)
    assert isinstance(storage.backend(tmp_path), storage.LocalFiles)   # another folder: always local


def test_address_pasted_with_rest_v1_is_accepted(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_fake")
    for pasted in ("https://abc.supabase.co/rest/v1/", "https://abc.supabase.co/rest/v1", "https://abc.supabase.co/"):
        monkeypatch.setenv("SUPABASE_URL", pasted)
        assert storage.supabase_settings()[0] == "https://abc.supabase.co"


def test_publishable_key_is_refused_as_the_secret_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_publishable_abc")
    with pytest.raises(storage.StorageError, match="secret key"):
        storage.supabase_settings()


def test_supabase_requests_are_built_safely(monkeypatch):
    """No network: check what would be sent (table, filters, upsert) with a fake connection."""
    import json
    import urllib.request
    sent = []

    class Reply:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.body

    def fake_urlopen(request, timeout, context):
        sent.append((request.get_method(), request.full_url, request.headers, request.data))
        if request.get_method() == "GET":
            return Reply(json.dumps([{"id": "U-20261105-k7f1", "body": "{\"a\": 1}"}]).encode())
        return Reply(b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    db = storage.Supabase("https://example.supabase.co/", "sb_secret_fake")
    db.write("tracker", "U-20261105-k7f1", "{\"a\": 1}")
    assert db.read("tracker", "U-20261105-k7f1") == "{\"a\": 1}"
    method, url, headers, data = sent[0]
    assert method == "POST" and url == "https://example.supabase.co/rest/v1/raahi_records?on_conflict=kind,id"
    assert "resolution=merge-duplicates" in headers["Prefer"] and headers["Apikey"] == "sb_secret_fake"
    assert "Authorization" not in headers                  # new-style secret key: apikey header only
    assert json.loads(data)[0]["kind"] == "tracker"
    assert sent[1][1].endswith("kind=eq.tracker&id=eq.U-20261105-k7f1&select=body")


def test_finish_intake_saves_next_step_and_date(tmp_path):
    import audit
    record = opened(tmp_path)
    today = date(2026, 11, 5)
    done = tracker.finish_intake(record["id"], "AS", base=tmp_path, today=today)
    assert done == {"step": tracker.NEXT_AFTER_INTAKE, "due": "2026-11-12"}  # a follow-up in 7 days
    assert tracker.status_of(record["id"], base=tmp_path) == tracker.INTAKE_DONE
    row = next(r for r in tracker.rows(base=tmp_path, today=today) if r["id"] == record["id"])
    assert row["status"] == tracker.INTAKE_DONE and row["next_step"] == tracker.NEXT_AFTER_INTAKE
    assert row["due"] == "2026-11-12" and not row["overdue"]
    assert audit.read_record(record["id"], base=tmp_path)["events"][-1]["event"] == "intake finished"
    tracker.finish_intake(record["id"], "AS", "Collect the FIR copy", date(2026, 11, 9), base=tmp_path, today=today)
    assert tracker.load(record["id"], base=tmp_path)["next"]["step"] == "Collect the FIR copy"
