""""Research this issue" with fake cases and a pretend AI / search (no internet):
an electricity disconnection in Bihar, and a ration card refusal in Uttar Pradesh. Practice data only."""

import io
import json
import urllib.error
from datetime import date

import pytest

import audit
import general
import knowledge
import llm
import research
import store
import tracker
import casework
import storage
from volunteer import calculate, choose_language, language_of, make_drafts  # noqa: F401

R = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
REAL_RESEARCH = llm.research_issue  # tests/conftest.py replaces it in every test; this test file needs it once

# ---------- the fake research: Bihar, electricity cut ----------

BIHAR_BRIEF = """1. Routes
First, write to the Assistant Engineer of the electricity supply sub-division about the disconnection.
If there is no reply, complain to the Consumer Grievance Redressal Forum of the distribution company.
After the Forum, the consumer can approach the Electricity Ombudsman of the Bihar Electricity Regulatory Commission.
2. Documents usually needed
The latest electricity bill, payment receipts and any disconnection notice.
3. Time limits
Not found in official sources.
4. Where and how to file
Complaints to the Forum can be made in writing at its office or through the company's online portal.
Most people win these complaints within a month.
5. Draft letter
To the Assistant Engineer, [Name of sub-division]. Subject: Restoration of electricity connection, consumer number [Consumer number]. I, [Name], of [Address], request ... [Signature]"""

BIHAR_RAW = llm.ResearchRaw(
    brief=BIHAR_BRIEF,
    sources=[{"uri": R + "a", "title": "berc.co.in"}, {"uri": R + "b", "title": "energy.bihar.gov.in"},
             {"uri": R + "c", "title": "lawrato.com"}, {"uri": R + "d", "title": "broken"}],
    supports=[
        {"text": "First, write to the Assistant Engineer of the electricity supply sub-division about the disconnection.",
         "sources": [1, 2]},
        {"text": "If there is no reply, complain to the Consumer Grievance Redressal Forum of the distribution company.",
         "sources": [0]},
        {"text": "The latest electricity bill, payment receipts and any disconnection notice.", "sources": [2]},
        {"text": "Complaints to the Forum can be made in writing at its office or through the company's online portal.",
         "sources": [3]},
    ],
    queries=["Bihar electricity disconnection complaint CGRF ombudsman"], model="gemini-test", sent="")
RESOLVED = {R + "a": "https://berc.co.in/consumer-corner/cgrf", R + "b": "https://energy.bihar.gov.in/complaints",
            R + "c": "https://www.lawrato.com/electricity-disconnection", R + "d": None}
BIHAR_POINTS = [
    {"kind": "route", "text": "Write first to the Assistant Engineer of the supply sub-division.",
     "quote": "First, write to the Assistant Engineer of the electricity supply sub-division about the disconnection."},
    {"kind": "route", "text": "If there is no reply, complain to the Consumer Grievance Redressal Forum.",
     "quote": "If there is no reply, complain to the Consumer Grievance Redressal Forum of the distribution company."},
    {"kind": "route", "text": "After the Forum, approach the Electricity Ombudsman.",  # words never backed by a search result
     "quote": "After the Forum, the consumer can approach the Electricity Ombudsman of the Bihar Electricity Regulatory Commission."},
    {"kind": "documents", "text": "The latest bill, payment receipts and any disconnection notice.",  # backed by a blog only
     "quote": "The latest electricity bill, payment receipts and any disconnection notice."},
    {"kind": "how_to_file", "text": "File in writing at the Forum's office or on the online portal.",  # link can't be resolved
     "quote": "Complaints to the Forum can be made in writing at its office or through the company's online portal."},
    {"kind": "how_to_file", "text": "Most people win these complaints within a month.",
     "quote": "Most people win these complaints within a month."},
    {"kind": "route", "text": "Call the minister's office.", "quote": "Call the minister's office directly."},
    {"kind": "letter", "text": "To the Assistant Engineer, [Name of sub-division]. Subject: Restoration of electricity "
                               "connection, consumer number [Consumer number]. I, [Name], of [Address], request ... "
                               "[Signature]", "quote": "To the Assistant Engineer"},
]

# ---------- the fake research: Uttar Pradesh, ration card refused ----------

UP_BRIEF = """Routes: Apply to the District Supply Officer if the ration card is refused.
A complaint can also be made to the District Grievance Redressal Officer under the food security law.
Where to file: online on the Food and Civil Supplies Department portal of Uttar Pradesh."""
UP_RAW = llm.ResearchRaw(
    brief=UP_BRIEF,
    sources=[{"uri": R + "u1", "title": "fcs.up.gov.in"}, {"uri": R + "u2", "title": "nfsa.gov.in"},
             {"uri": R + "u3", "title": "indiankanoon.org"}],
    supports=[{"text": "Apply to the District Supply Officer if the ration card is refused.", "sources": [0]},
              {"text": "A complaint can also be made to the District Grievance Redressal Officer under the food "
                       "security law.", "sources": [1, 2]},
              {"text": "online on the Food and Civil Supplies Department portal of Uttar Pradesh.", "sources": [2]}],
    queries=["UP ration card refused complaint"], model="gemini-test", sent="")
UP_RESOLVED = {R + "u1": "https://fcs.up.gov.in/", R + "u2": "https://nfsa.gov.in/portal/grievance",
               R + "u3": "https://indiankanoon.org/doc/1/"}
UP_POINTS = [
    {"kind": "route", "text": "Apply to the District Supply Officer.",
     "quote": "Apply to the District Supply Officer if the ration card is refused."},
    {"kind": "route", "text": "Complain to the District Grievance Redressal Officer.",
     "quote": "A complaint can also be made to the District Grievance Redressal Officer under the food security law."},
    {"kind": "how_to_file", "text": "File online on the state Food and Civil Supplies portal.",
     "quote": "online on the Food and Civil Supplies Department portal of Uttar Pradesh."},
]


@pytest.fixture
def fake_ai(monkeypatch):
    """The pretend AI: answers by state. Records what was sent."""
    sent = []

    def research_issue(state, issue):
        sent.append((state, issue))
        return {"Bihar": BIHAR_RAW, "Uttar Pradesh": UP_RAW}[state]

    monkeypatch.setattr(llm, "research_issue", research_issue)
    monkeypatch.setattr(llm, "split_brief", lambda brief: (
        [dict(p) for p in (BIHAR_POINTS if brief == BIHAR_BRIEF else UP_POINTS)], "gemini-test"))
    return sent


def resolve(uri):
    return {**RESOLVED, **UP_RESOLVED}.get(uri)


def new_case(tmp_path, state="Bihar"):
    record = tracker.open_case("General", "Volunteer A", base=tmp_path)
    tracker.merge_facts(record["id"], {"state": state}, "Volunteer A", "story", base=tmp_path)
    return record["id"]


def bihar_research(tmp_path, fake_ai):
    case_id = new_case(tmp_path)
    return case_id, research.run(case_id, "Bihar", "electricity connection cut, department not responding",
                                 "Volunteer A", base=tmp_path, resolve=resolve)


# ---------- links: only official sites, only from the search results ----------

@pytest.mark.parametrize("url, ok", [
    ("https://energy.bihar.gov.in/x", True), ("https://indiacode.nic.in/handle/1", True),
    ("https://nalsa.gov.in/", True), ("https://berc.co.in/cgrf", True), ("https://uperc.org/", True),
    ("https://bslsa.bih.nic.in/", True), ("https://www.lawrato.com/x", False), ("https://gov.in.evil.com/", False),
    ("https://notgov.in/", False), ("ftp://energy.bihar.gov.in/", False), ("", False),
    # Bihar and UP power companies and regulators (confirmed on government pages, see research.py)
    ("https://www.bsphcl.co.in/main.htm", True), ("https://nbpdcl.co.in/frmContactUs.aspx", True),
    ("https://www.sbpdcl.co.in/", True), ("http://www.bsptcl.in/", True), ("https://bspgcl.co.in/", True),
    ("https://www.uppcl.org/uppcl/en/", True), ("https://pvvnl.org/", True), ("http://mvvnl.in/en/", True),
    ("https://www.dvvnl.org/", True), ("https://kesco.org.in/Default", True), ("http://kesco.co.in/", True),
    ("https://upptcl.org/", True), ("https://puvvnl.up.nic.in/", True), ("https://www.uperc.org/Default2.aspx", True),
    ("https://nbpdcl.co.in.example.com/", False), ("https://fake-nbpdcl.co.in/", False),
])
def test_allowed_links(url, ok):
    assert research.allowed_link(url) is ok


def test_grounding_redirect_is_read_without_opening_the_site(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            assert request.full_url.startswith(R)
            raise urllib.error.HTTPError(request.full_url, 302, "Found", {"Location": "https://fcs.up.gov.in/"}, io.BytesIO())
    monkeypatch.setattr(research.urllib.request, "build_opener", lambda *a: Opener())
    assert research.resolve_link(R + "x") == "https://fcs.up.gov.in/"
    assert research.resolve_link("https://nfsa.gov.in/") == "https://nfsa.gov.in/"  # not a redirect: as it is


# ---------- Bihar: the checks keep only points with an official source ----------

def test_bihar_points_without_an_official_source_are_dropped(tmp_path, fake_ai):
    case_id, record = bihar_research(tmp_path, fake_ai)
    assert record["label"] == "AI research, not yet checked: for supervisor approval"
    assert record["status"] == research.WAITING and record["id"] == f"{case_id}.r1"
    kept = {p["kind"] + ":" + p["text"]: p for p in record["points"]}
    assert list(kept) == ["route:Write first to the Assistant Engineer of the supply sub-division.",
                          "route:If there is no reply, complain to the Consumer Grievance Redressal Forum."]
    # the AI's own draft letter is never kept or listed (the app builds the letter itself)
    assert not any(d["kind"] == "letter" for d in record["dropped"])
    first = record["points"][0]
    assert [s["url"] for s in first["sources"]] == ["https://energy.bihar.gov.in/complaints"]  # the blog is left out
    reasons = {d["text"]: d["reason"] for d in record["dropped"]}
    assert reasons["After the Forum, approach the Electricity Ombudsman."] == "no search result backs it"
    assert reasons["The latest bill, payment receipts and any disconnection notice."] == \
        "no official source among its search results"
    assert reasons["File in writing at the Forum's office or on the online portal."] == \
        "no official source among its search results"  # its link could not be resolved
    assert reasons["Most people win these complaints within a month."] == "predicts an outcome"
    assert reasons["Call the minister's office."] == "its words are not in the brief"
    for p in record["points"]:  # every link is one Google Search returned, and official
        assert all(s["url"] in RESOLVED.values() and research.allowed_link(s["url"]) for s in p["sources"])
    event = audit.read_record(case_id, base=tmp_path)["events"][-1]
    assert event["event"] == "research asked" and "2 points kept, 5 dropped" in event["details"]


def test_only_state_and_issue_are_sent_never_numbers(monkeypatch):
    monkeypatch.setattr(llm, "research_issue", REAL_RESEARCH)
    bodies = []
    monkeypatch.setattr(llm, "_generate", lambda body: (bodies.append(body) or (
        {"candidates": [{"content": {"parts": [{"text": "brief"}]},
                         "groundingMetadata": {"groundingChunks": [{"web": {"uri": R + "a", "title": "x"}}]}}]},
        "gemini-test")))
    raw = llm.research_issue("Bihar", "electricity cut; call 9876543210, Aadhaar 2345 6789 0123")
    text = json.dumps(bodies[0])
    assert "9876543210" not in text and "2345 6789 0123" not in text and "Bihar" in text
    assert bodies[0]["tools"] == [{"google_search": {}}]
    assert raw.sources == [{"uri": R + "a", "title": "x"}]


# ---------- on screen: the volunteer asks, the supervisor approves, the summary shows it ----------

STORY = ("Practice case. The person seeking help lives in Bihar. Ramesh from the electricity office cut the line. "
         "She wants the connection restored.")


def test_research_on_screen(monkeypatch, fake_ai):
    from streamlit.testing.v1 import AppTest
    from test_general import MODEL, answer, yn
    raw = answer(what_happened=["The electricity line was cut."],
                 issues=[{"category": "electricity_or_water", "name": "electricity connection cut"}],
                 state={"value": "Bihar", "quote": "lives in Bihar"}, woman=yn("yes", "The person seeking help"),
                 outcome_wanted={"value": "the connection restored", "quote": "She wants the connection restored."})
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "gemini_available", lambda: True)
    monkeypatch.setattr(llm, "read_general_notes",
                        lambda notes, output_lang="en", known=None: llm.NotesReading(raw, notes, {}, MODEL))
    monkeypatch.setattr(research, "resolve_link", resolve)
    monkeypatch.setenv("SUPERVISOR_PASSWORD", "practice-sup")
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    at.text_input(key="volunteer").set_value("Volunteer A").run()
    at.text_area(key="g_notes").set_value(STORY)
    choose_language(at, "g_notes", language_of(STORY))
    next(b for b in at.button if b.label == "Read the story").click().run()
    assert not at.exception, at.exception[0].stack_trace
    # Nothing by itself: research runs when the volunteer presses "Run research", with only the state
    # and the issue in plain words
    assert fake_ai == [] and not at.session_state["shown_drafts"]
    at.button(key="rs-run-go").click().run()
    assert fake_ai == [("Bihar", "electricity connection cut")]
    at.run()
    assert len(fake_ai) == 1                                       # not again on a page reload
    shown = make_drafts(at).session_state["shown_drafts"]          # "Make the drafts", "Draft the letter"
    assert "Not covered by our verified files yet" not in shown[0]   # research was run: the summary says so
    assert "Research from official websites: 2 points, listed with the complaint letter" in shown[0]
    # New order: the research is shown to the volunteer and the letter is drafted straight away from it
    assert len(shown) == 3                                         # summary + draft letter + free legal aid application
    letter = shown[1]
    assert "Write first to the Assistant Engineer" in letter and "AI research, not yet checked by a lawyer" in letter
    assert any("AI research, not yet checked by a lawyer" in w.value for w in at.warning)
    at.button(key="rs-again-go").click().run()                     # "Research again" on request
    assert len(fake_ai) == 2

    case_id = at.session_state["case_id"]
    for r in research.for_case(case_id)[1:]:                       # keep one brief for the review
        storage.backend().delete("research", r["id"])
    at.run()
    rid = research.for_case(case_id)[0]["id"]
    at.checkbox(key=f"rsv-{rid}-p2").uncheck().run()               # the volunteer thinks p2 is wrong
    assert len(at.session_state["shown_drafts"]) == 2              # the letter is cleared until drafted again
    letter = make_drafts(at).session_state["shown_drafts"][1]      # "Draft the letter" again
    assert "Consumer Grievance Redressal Forum" not in letter       # unticked: out of the letter
    at.checkbox(key="g_checked").check().run()
    assert next(b for b in at.button if b.key == "send-g").disabled  # a reason is needed for the left-out point
    at.text_input(key=f"rsvr-{rid}-p2").set_value("the forum is for a later step").run()
    next(b for b in at.button if b.key == "send-g").click().run()
    assert not at.exception, at.exception[0].stack_trace
    assert store.get_pending(case_id)["draft"].count("DRAFT — to be checked by a lawyer") == 3
    record = research.load(rid)
    assert [p["volunteer"] for p in record["points"] if p["kind"] != "letter"] == \
        [research.KEPT, research.LEFT_OUT]
    assert record["points"][1]["volunteer_reason"] == "the forum is for a later step"

    assert any("Sent on" in s.value and "Waiting for review" in s.value for s in at.success)  # the status, after sending
    # One combined review: research points and the drafts together; approval waits for the points
    at.button(key="nav-supervisor").click().run()
    next(t for t in at.text_input if t.label == "Supervisor password").set_value("practice-sup")
    next(b for b in at.button if b.label == "Sign in").click().run()
    at.text_input(key="sup-name").set_value("Supervisor S")  # then the name or initials
    at.button(key="sup-name-go").click().run()
    assert not any(r.key == f"action-{case_id}" for r in at.radio)  # no approve until the points are decided
    assert any("left this point out of the letter. Reason: the forum is for a later step" in w.value for w in at.warning)
    for point, choice in (("p1", "Approve"), ("p2", "Reject")):  # (no AI letter item to decide)
        at.radio(key=f"rsd-{rid}-{point}").set_value(choice).run()
        at.button(key=f"rss-{rid}-{point}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    # not by itself: the supervisor rebuilds the letter from the approved points before approving
    assert not any(r.key == f"action-{case_id}" for r in at.radio)
    at.button(key=f"rebuild-{case_id}").click().run()
    packet = store.get_pending(case_id)["draft"]
    assert packet.count("DRAFT — to be checked by a lawyer") == 3   # the letter, rebuilt from the approved points
    letter = next(p for p in casework.split_bundle(packet) if "Complaint about" in p)
    assert "Write first to the Assistant Engineer" in letter and "energy.bihar.gov.in" in letter
    assert "Consumer Grievance Redressal Forum" not in letter      # rejected: not in the letter
    assert "[Name of the person]" in letter and "[Consumer number]" in letter
    at.radio(key=f"action-{case_id}").set_value("Approve").run()
    next(b for b in at.button if b.key == f"approve-{case_id}").click().run()
    assert not at.exception, at.exception[0].stack_trace
    saved = store.approved_draft(case_id)
    assert "approved by the supervisor on [date]" not in saved      # every draft in the packet is dated
    assert saved.count("the draft was reviewed and approved by the supervisor on") == 3


# ---------- the supervisor: approve, edit, reject; only approved points reach the case ----------

def test_supervisor_decides_each_point(tmp_path, fake_ai):
    case_id, record = bihar_research(tmp_path, fake_ai)
    rid = record["id"]
    research.decide(rid, "p1", research.APPROVE, base=tmp_path, today=date(2026, 11, 5))
    research.decide(rid, "p2", research.EDIT, "If there is no reply in 7 days, complain to the CGRF.", base=tmp_path,
                    today=date(2026, 11, 5))
    with pytest.raises(research.ResearchFailed, match="already decided"):
        research.decide(rid, "p1", research.REJECT, base=tmp_path)
    assert research.load(rid, base=tmp_path)["status"] == research.REVIEWED
    points = research.approved_points(case_id, base=tmp_path)
    assert [p["text"] for p in points] == ["Write first to the Assistant Engineer of the supply sub-division.",
                                           "If there is no reply in 7 days, complain to the CGRF."]
    assert all(p["sources"] and p["approved_on"] == "2026-11-05" for p in points)
    events = [e["event"] for e in audit.read_record(case_id, base=tmp_path)["events"]]
    assert events[-2:] == ["research point approved", "research point approved after editing"]
    assert "->" in audit.read_record(case_id, base=tmp_path)["events"][-1]["details"]  # old -> new (the edit)


def test_approved_points_go_into_the_summary_and_draft_with_sources(tmp_path, fake_ai):
    case_id, record = bihar_research(tmp_path, fake_ai)
    research.decide(record["id"], "p1", research.APPROVE, base=tmp_path, today=date(2026, 11, 5))
    issue = "electricity connection cut, department not responding"
    g = general.GeneralFacts(person="the person seeking help", what_happened=["The electricity line was cut."],
                             timeline=[], coming_dates=[], issues=[("other", issue)], sections=[], documents_held=[],
                             answers=[], still_to_ask=[], facts={"state": "Bihar"}, today="2026-11-05")
    assert general.uncovered_issues(g) == [issue]
    assert "Not covered by our verified files yet" in general.summary_body(g)
    g.research = research.items_for_summary(case_id, "Bihar", [issue], base=tmp_path)
    assert general.uncovered_issues(g) == []
    body = general.summary_body(g)
    assert "Not covered by our verified files yet" not in body
    assert "Route (AI research, approved by the supervisor on 5 November 2026):" in body  # name and long date
    assert "Write first to the Assistant Engineer" in body
    assert "Source: energy.bihar.gov.in (https://energy.bihar.gov.in/complaints)" in body
    assert "Consumer Grievance Redressal Forum" not in body  # not approved: not in the case
    draft = general.make_summary_draft(g, "gemini-test")
    assert draft.startswith("DRAFT — to be checked by a lawyer") and "Write first to the Assistant Engineer" in draft
    hi = general.make_summary_draft(g, "gemini-test", "hi")
    assert "सुपरवाइज़र ने 5 नवंबर 2026 को मंज़ूर किया" in hi and "Source: energy.bihar.gov.in" in hi
    assert general.GeneralFacts.from_dict(g.to_dict()).research == g.research  # saved with the case


def test_saved_knowledge_covers_the_next_similar_case(tmp_path, fake_ai):
    case_id, record = bihar_research(tmp_path, fake_ai)
    with pytest.raises(research.ResearchFailed, match="Only an approved point"):
        research.save_knowledge(record["id"], "p1", "x", base=tmp_path)
    research.decide(record["id"], "p1", research.APPROVE, base=tmp_path, today=date(2026, 11, 5), by="SK")
    entry = research.save_knowledge(record["id"], "p1", "Bihar: electricity disconnection, who to write to first",
                                    ["electricity", "disconnection"], base=tmp_path, today=date(2026, 11, 5))
    assert entry["approved_by"] == "SK" and entry["approved_on"] == "2026-11-05" and entry["lawyer_checked"] == "no"
    assert research.approval_line(entry) == "Approved by the supervisor (SK, 2026-11-05)"
    assert entry["link"].endswith("/complaints")
    assert audit.read_record(case_id, base=tmp_path)["events"][-1]["event"] == "research saved as knowledge"

    later = new_case(tmp_path)  # a new Bihar case: covered now, no research needed
    items = research.items_for_summary(later, "Bihar", ["electricity disconnection at home"], base=tmp_path)
    assert [i["origin"] for i in items] == ["knowledge"] and "Lawyer" not in items[0]["text"]
    assert items[0]["approved_by"] == "SK"
    g_lines = general._research_lines(items)
    assert "(approved by the supervisor (SK, 2026-11-05))" in g_lines[0] and "lawyer checked" not in g_lines[0]
    assert research.items_for_summary(later, "Uttar Pradesh", ["electricity disconnection"], base=tmp_path) == []
    assert research.items_for_summary(later, "Bihar", ["unpaid wages"], base=tmp_path) == []


def test_export_is_in_the_knowledge_file_format(tmp_path, fake_ai, monkeypatch):
    case_id, record = bihar_research(tmp_path, fake_ai)
    research.decide(record["id"], "p1", research.APPROVE, base=tmp_path, today=date(2026, 11, 5), by="SK")
    research.save_knowledge(record["id"], "p1", "Bihar: electricity disconnection, who to write to first",
                            base=tmp_path, today=date(2026, 11, 5))
    folder = tmp_path / "k"
    folder.mkdir()
    (folder / "research_approved.md").write_text(research.export_markdown(base=tmp_path), encoding="utf-8")
    monkeypatch.setattr(knowledge, "KNOWLEDGE", folder)
    knowledge._entries.cache_clear()
    try:
        [entry] = knowledge.entries("research_approved.md")
    finally:
        knowledge._entries.cache_clear()
    assert entry.heading == "Bihar: electricity disconnection, who to write to first"
    assert entry.link == "https://energy.bihar.gov.in/complaints" and "Approved by the supervisor (SK, 2026-11-05)" in entry.checked
    assert "Lawyer checked" not in research.export_markdown(base=tmp_path)
    assert "State: Bihar." in entry.body


# ---------- Uttar Pradesh: ration card refused ----------

def test_up_ration_card(tmp_path, fake_ai):
    case_id = new_case(tmp_path, "Uttar Pradesh")
    record = research.run(case_id, "Uttar Pradesh", "ration card application refused", "Volunteer B", base=tmp_path,
                          resolve=resolve)
    assert fake_ai[-1] == ("Uttar Pradesh", "ration card application refused")
    assert [p["text"] for p in record["points"]] == ["Apply to the District Supply Officer.",
                                                     "Complain to the District Grievance Redressal Officer."]
    assert [s["url"] for s in record["points"][1]["sources"]] == ["https://nfsa.gov.in/portal/grievance"]
    assert record["dropped"][0]["reason"] == "no official source among its search results"  # indiankanoon only
    research.decide(record["id"], "p1", research.REJECT, base=tmp_path)
    research.decide(record["id"], "p2", research.APPROVE, base=tmp_path)
    assert [p["text"] for p in research.approved_points(case_id, base=tmp_path)] == [
        "Complain to the District Grievance Redressal Officer."]
    assert research.waiting(base=tmp_path) == []


# ---------- when research fails ----------

def test_failure_says_so_and_suggests_15100(tmp_path, monkeypatch):
    def busy(*a):
        raise llm.AIUnavailable(llm.BUSY_MESSAGE, busy=True)
    monkeypatch.setattr(llm, "research_issue", busy)
    case_id = new_case(tmp_path)
    with pytest.raises(research.ResearchFailed, match="15100"):
        research.run(case_id, "Bihar", "electricity cut", "Volunteer A", base=tmp_path)
    assert audit.read_record(case_id, base=tmp_path)["events"][-1]["event"] == "research failed"
    assert research.for_case(case_id, base=tmp_path) == []


def test_no_official_point_at_all_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "research_issue", lambda s, i: UP_RAW)
    monkeypatch.setattr(llm, "split_brief", lambda b: ([dict(UP_POINTS[2])], "gemini-test"))
    case_id = new_case(tmp_path, "Uttar Pradesh")
    with pytest.raises(research.ResearchFailed, match="15100"):
        research.run(case_id, "Uttar Pradesh", "ration card refused", "Volunteer A", base=tmp_path, resolve=resolve)


def test_deleting_a_case_removes_its_research(tmp_path, fake_ai):
    case_id, record = bihar_research(tmp_path, fake_ai)
    assert "research" in store.delete_case(case_id, base=tmp_path)
    assert research.for_case(case_id, base=tmp_path) == []


def test_names_in_the_question_are_caught():
    notes = "Ramesh from the electricity office cut the line. She lives in Bihar."
    assert research.names_in("Ramesh cut the electricity connection", notes) == ["Ramesh"]
    assert research.names_in("Electricity connection cut in Bihar", notes) == []


def test_approved_research_shows_in_the_case_file(tmp_path, fake_ai, monkeypatch):
    case_id, record = bihar_research(tmp_path, fake_ai)
    research.decide(record["id"], "p1", research.APPROVE, base=tmp_path, today=date(2026, 11, 5))
    case = tracker.load(case_id, base=tmp_path)
    assert case["research_points"][0]["sources"][0]["url"] == "https://energy.bihar.gov.in/complaints"
