""""Research this issue": for problems our knowledge files don't cover. Plain code around two AI calls.

1. llm.research_issue sends ONLY the state and the issue in plain words (personal numbers removed) to
   Gemini with Google Search grounding, which writes a brief; llm.split_brief splits it into points,
   each with the exact words of the brief it comes from.
2. This file keeps a point only if the words it comes from are backed by search results (Google's
   grounding data, never links the AI writes itself) whose real address is on an allowed official
   site. Points without one, and points that predict an outcome, are dropped (and counted).
3. The brief is saved as "AI research, not yet checked: for supervisor approval". The supervisor
   approves, edits or rejects each point. Only approved points go into the case and its drafts,
   with their sources. An approved point can be saved as a knowledge entry for that state (kept in
   the shared database; export_markdown() writes them in the knowledge/ format to add by hand).
4. Every step goes into the case's audit record. If research fails, the volunteer is told so and
   pointed to NALSA's free helpline 15100.
"""

import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import audit
import llm
import privacy
import storage
import store
import tracker

HERE = Path(__file__).resolve().parent
LABEL = "AI research, not yet checked: for supervisor approval"
FAILED = "Research didn't work this time. Ask NALSA's free helpline 15100."
WAITING, REVIEWED = "waiting for the supervisor", "reviewed"
APPROVE, EDIT, REJECT = "approve", "edit", "reject"
KINDS = {"route": "Route", "documents": "Documents usually needed", "time_limit": "Time limit",
         "how_to_file": "Where and how to file", "letter": "Draft letter"}

from official import ALLOWED_HOSTS, ALLOWED_SUFFIXES, allowed_link, host  # noqa: F401  (one list)
REDIRECT_HOSTS = ("vertexaisearch.cloud.google.com",)  # Google's grounding links point here first
PREDICTION = re.compile(r"\b(chances?|likely|unlikely|guarantee[sd]?|surely|certainly|definitely|assured|"
                        r"win|wins|winning|won|succeed|succeeds|success(?:ful)?|"
                        r"will (?:win|succeed|get (?:the )?(?:money|connection|card|relief)|be (?:released|restored|"
                        r"granted|approved|reconnected|issued)))\b", re.I)


class ResearchFailed(Exception):
    """Research could not be done. The message is safe to show."""


# ---------- names: never sent ----------

def names_in(question: str, notes: str) -> List[str]:
    """Capitalised words in the research question that are also capitalised in the story (anywhere,
    also at the start of a sentence), other than states and common words. A strict check, because
    the question leaves the clinic; the volunteer rewrites the question in plain words."""
    import general
    ordinary = general._NOT_NAMES | {w.casefold() for s in general.state_names() for w in s.split()}
    in_notes = set(re.findall(r"\b[A-Z][a-z'’-]{2,}\b", notes or ""))
    return list(dict.fromkeys(w for w in re.findall(r"\b[A-Z][a-z'’-]{2,}\b", question or "")
                              if w in in_notes and w.casefold() not in ordinary))


# ---------- links ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # don't follow: we only want the address it points to


def resolve_link(uri: str, timeout: int = 10) -> Optional[str]:
    """The real address behind a Google grounding link (read from the redirect, without opening the
    government site itself). Other links are returned as they are. None if it can't be found."""
    if host(uri) not in REDIRECT_HOSTS:
        return uri or None
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(uri, method="GET", headers={"User-Agent": "AgentRaahi/1.0"})
    try:
        opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as err:
        if err.code in (301, 302, 303, 307, 308):
            return err.headers.get("Location") or None
        return None
    except Exception:
        return None
    return None


# ---------- checking the AI's points against the search results ----------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _span(haystack: str, needle: str):
    needle = _norm(needle)
    if not needle:
        return None
    i = haystack.find(needle)
    if i < 0:
        i = haystack.casefold().find(needle.casefold())
    return (i, i + len(needle)) if i >= 0 else None


def check_points(raw: "llm.ResearchRaw", points: List[dict], resolve: Optional[Callable[[str], Optional[str]]] = None):
    """(kept points, dropped points, sources). A point is kept only if the words of the brief it comes
    from are backed by search results with an allowed official address. Links come only from the
    search results (raw.sources), never from the AI's own text."""
    brief = _norm(raw.brief)
    resolve = resolve or resolve_link
    sources = []
    for i, s in enumerate(raw.sources):
        url = resolve(s.get("uri", ""))
        sources.append({"index": i, "title": privacy.redact(str(s.get("title", "")))[0][:120], "url": url,
                        "allowed": bool(url) and allowed_link(url)})
    kept, dropped = [], []
    for p in points:
        kind = p.get("kind") if p.get("kind") in KINDS else "route"
        text = privacy.redact(_norm(str(p.get("text", ""))))[0][:2000 if kind == "letter" else 600]
        if not text:
            continue
        if kind != "letter" and PREDICTION.search(text):
            dropped.append({"kind": kind, "text": text, "reason": "predicts an outcome"})
            continue
        if kind == "letter":
            kept.append({"kind": kind, "text": text, "sources": []})  # sources given below
            continue
        span = _span(brief, p.get("quote", ""))
        if span is None:
            dropped.append({"kind": kind, "text": text, "reason": "its words are not in the brief"})
            continue
        backing = []
        for support in raw.supports:
            seg = _span(brief, support.get("text", ""))
            if seg and seg[0] < span[1] and span[0] < seg[1]:
                backing += [i for i in support.get("sources", []) if isinstance(i, int) and 0 <= i < len(sources)]
        official = []
        for i in dict.fromkeys(backing):
            s = sources[i]
            if s["allowed"] and s["url"] not in [o["url"] for o in official]:
                official.append({"url": s["url"], "title": s["title"] or host(s["url"])})
        if not backing:
            dropped.append({"kind": kind, "text": text, "reason": "no search result backs it"})
        elif not official:
            dropped.append({"kind": kind, "text": text, "reason": "no official source among its search results"})
        else:
            kept.append({"kind": kind, "text": text, "sources": official})
    # The draft letter rests on the routes and filing points kept above: it cites their sources.
    basis = []
    for p in kept:
        if p["kind"] in ("route", "how_to_file"):
            basis += [s for s in p["sources"] if s not in basis]
    for p in [p for p in kept if p["kind"] == "letter"]:
        if basis:
            p["sources"] = basis
        else:
            kept.remove(p)
            dropped.append({"kind": "letter", "text": p["text"], "reason": "no official route kept to base it on"})
    for n, p in enumerate(kept, 1):
        p.update(id=f"p{n}", status=WAITING, decided_on=None, decided_by=None, original=p["text"])
    return kept, dropped, sources


# ---------- running research for a case ----------

def _new_id(case_id: str, base: Path) -> str:
    taken = {r["id"] for r in all_records(base)}
    n = 1
    while f"{case_id}.r{n}" in taken:
        n += 1
    return f"{case_id}.r{n}"


def run(case_id: str, state: str, issue: str, by: str, base: Path = HERE,
        resolve: Optional[Callable[[str], Optional[str]]] = None) -> dict:
    """Research one issue for a case. Returns the saved brief (waiting for the supervisor).
    Raises ResearchFailed (with the 15100 suggestion) if it can't be done."""
    store._check_id(case_id)
    by = tracker.clean_name(by)
    search = llm.GOOGLE_LABEL
    try:
        raw = llm.research_issue(state, issue)
    except llm.AIUnavailable as google_err:
        if not llm.tavily_key():
            audit.add_event(case_id, "research failed", audit.VOLUNTEER, f"{search}: {google_err} (by {by})", base=base)
            raise ResearchFailed(FAILED) from None
        # Backup: Tavily on the official-site list, then a brief written only from those results
        search = llm.TAVILY_LABEL
        audit.log_research_search(case_id, search, f"{llm.GOOGLE_LABEL} did not work: {google_err}", base=base)
        try:
            raw = llm.research_issue_tavily(state, issue)
        except llm.AIUnavailable as err:
            audit.add_event(case_id, "research failed", audit.VOLUNTEER,
                            f"{llm.GOOGLE_LABEL}: {google_err}; {search}: {err} (by {by})", base=base)
            raise ResearchFailed(FAILED) from None
    try:
        points, split_model = llm.split_brief(raw.brief)
    except llm.AIUnavailable as err:
        audit.add_event(case_id, "research failed", audit.VOLUNTEER, f"{search}: {err} (by {by})", base=base)
        raise ResearchFailed(FAILED) from None
    kept, dropped, sources = check_points(raw, points, resolve or resolve_link)
    if not kept:
        audit.add_event(case_id, "research failed", audit.VOLUNTEER,
                        f"no point had an official source ({len(dropped)} dropped; by {by})", base=base)
        raise ResearchFailed(FAILED)
    record = {"id": _new_id(case_id, base), "case_id": case_id, "label": LABEL, "status": WAITING,
              "state": privacy.redact(state)[0][:60], "issue": privacy.redact(issue)[0][:300], "sent": raw.sent,
              "asked_by": by, "asked_at": tracker.now(), "model": raw.model, "split_model": split_model,
              "search": search,
              "queries": [privacy.redact(q)[0][:200] for q in raw.queries][:10],
              "sources_found": len(sources), "sources_official": sum(1 for s in sources if s["allowed"]),
              "points": kept, "dropped": dropped}
    storage.write_json("research", record["id"], record, base)
    audit.add_event(case_id, "research asked", audit.VOLUNTEER,
                    f"{LABEL}; search: {search}; model {raw.model}; {len(sources)} search results, "
                    f"{record['sources_official']} official; {len(kept)} points kept, {len(dropped)} dropped "
                    f"(by {by})", base=base)
    return record


# ---------- reading ----------

def all_records(base: Path = HERE) -> List[dict]:
    return storage.all_json("research", base)


def load(research_id: str, base: Path = HERE) -> dict:
    record = storage.read_json("research", research_id, base)
    if record is None:
        raise ResearchFailed("No such research brief.")
    return record


def for_case(case_id: str, base: Path = HERE) -> List[dict]:
    return [r for r in all_records(base) if r.get("case_id") == case_id]


def waiting(base: Path = HERE) -> List[dict]:
    return [r for r in all_records(base) if r.get("status") == WAITING]


# ---------- the supervisor's decisions ----------

def decide(research_id: str, point_id: str, decision: str, text: Optional[str] = None, base: Path = HERE,
           today: Optional[date] = None) -> dict:
    """Approve, edit (then approve) or reject one point. Approved points go into the case with their
    sources. Every decision is in the audit record."""
    if decision not in (APPROVE, EDIT, REJECT):
        raise ResearchFailed("Choose approve, edit or reject.")
    today = today or date.today()
    record = load(research_id, base)
    point = next((p for p in record["points"] if p["id"] == point_id), None)
    if point is None:
        raise ResearchFailed("No such point.")
    if point["status"] != WAITING:
        raise ResearchFailed("This point was already decided.")
    if decision == EDIT:
        edited = privacy.redact(_norm(text or ""))[0][:2000]
        if not edited:
            raise ResearchFailed("Write the corrected point first.")
        point["text"] = edited
    point.update(status={APPROVE: "approved", EDIT: "approved after editing", REJECT: "rejected"}[decision],
                 decided_on=today.isoformat(), decided_by=audit.SUPERVISOR)
    if decision != REJECT:
        case = tracker.load(record["case_id"], base)
        if case is not None:
            case.setdefault("research_points", []).append({
                "research_id": research_id, "point_id": point_id, "issue": record["issue"], "state": record["state"],
                "kind": point["kind"], "text": point["text"], "sources": point["sources"],
                "approved_on": today.isoformat()})
            tracker._note(case, "supervisor", f"research point approved ({research_id} {point_id})")
            tracker._save(case, base)
    if all(p["status"] != WAITING for p in record["points"]):
        record["status"] = REVIEWED
    storage.write_json("research", research_id, record, base)
    details = f"{research_id} {point_id} ({KINDS[point['kind']]})"
    if decision == EDIT:
        details += f": {point['original']} -> {point['text']}"
    audit.add_event(record["case_id"], f"research point {point['status']}", audit.SUPERVISOR, details, base=base)
    return point


def approved_points(case_id: str, base: Path = HERE) -> List[dict]:
    case = tracker.load(case_id, base)
    return list((case or {}).get("research_points", []))


# ---------- approved points as knowledge entries (shared database) ----------

STOP = {"with", "from", "that", "this", "their", "they", "have", "been", "were", "after", "about", "into", "isn't",
        "isnt", "doesn't", "does", "said", "says", "the", "and", "not", "for", "our", "his", "her", "them",
        "problem", "issue", "person", "department", "office", "listening", "anyone", "someone"}


def keywords(text: str) -> List[str]:
    words = re.findall(r"[a-z]{4,}", (text or "").casefold())
    return list(dict.fromkeys(w for w in words if w not in STOP))[:8]


def save_knowledge(research_id: str, point_id: str, heading: str, words: Optional[List[str]] = None,
                   base: Path = HERE, today: Optional[date] = None) -> dict:
    """Save an approved point as a knowledge entry for its state, with Source, Link and
    "Lawyer checked: yes". The next case in that state with a matching issue is then covered."""
    today = today or date.today()
    record = load(research_id, base)
    point = next((p for p in record["points"] if p["id"] == point_id), None)
    if point is None or not point["status"].startswith("approved"):
        raise ResearchFailed("Only an approved point can be saved as knowledge.")
    heading = privacy.redact(_norm(heading))[0][:150]
    if not heading:
        raise ResearchFailed("Give the entry a short heading.")
    words = [w.casefold() for w in (words if words is not None else keywords(record["issue"])) if w.strip()]
    if not words:
        raise ResearchFailed("Give at least one keyword, so similar cases can be matched.")
    first = point["sources"][0]
    entry = {"id": f"K-{re.sub(r'[^a-z]', '', record['state'].casefold())[:20] or 'state'}-{secrets.token_hex(3)}",
             "state": record["state"], "heading": heading, "body": point["text"],
             "source": "; ".join(s["title"] for s in point["sources"]), "link": first["url"],
             "links": [s["url"] for s in point["sources"]], "checked": today.isoformat(),
             "lawyer_checked": f"yes (supervisor, {today.isoformat()})", "keywords": words,
             "from_case": record["case_id"], "from_research": research_id, "point_id": point_id}
    storage.write_json("knowledge_added", entry["id"], entry, base)
    point["knowledge_id"] = entry["id"]
    storage.write_json("research", research_id, record, base)
    audit.add_event(record["case_id"], "research saved as knowledge", audit.SUPERVISOR,
                    f"{entry['id']} for {entry['state']}: {heading}", base=base)
    return entry


def learned(base: Path = HERE) -> List[dict]:
    return sorted(storage.all_json("knowledge_added", base), key=lambda e: e["id"])


def matching(state: Optional[str], issue: str, base: Path = HERE) -> List[dict]:
    """Saved entries for this state whose keywords appear in the issue (plain words)."""
    if not state:
        return []
    words = set(re.findall(r"[a-z]{4,}", (issue or "").casefold()))
    return [e for e in learned(base) if e["state"].casefold() == state.casefold() and words & set(e["keywords"])]


def source_line(sources: List[dict]) -> str:
    return "Source: " + "; ".join(f"{s['title']} ({s['url']})" for s in sources)


def items_for_summary(case_id: Optional[str], state: Optional[str], issues: List[str],
                      base: Path = HERE) -> List[dict]:
    """What the summary shows under each issue our files don't cover: saved knowledge entries for the
    state, then this case's approved research points. [{"issue", "origin", "kind", "heading", "text",
    "source_line", "approved_on"}]"""
    items = []
    for issue in issues:
        for e in matching(state, issue, base):
            items.append({"issue": issue, "origin": "knowledge", "kind": "", "heading": e["heading"],
                          "text": e["body"], "source_line": f"Source: {e['source']} ({e['link']})",
                          "approved_on": e["checked"]})
    for p in approved_points(case_id, base) if case_id else []:
        target = p["issue"] if p["issue"] in issues else (issues[0] if issues else p["issue"])
        if any(i["text"] == p["text"] and i["issue"] == target for i in items):
            continue
        items.append({"issue": target, "origin": "research", "kind": p["kind"], "heading": KINDS[p["kind"]],
                      "text": p["text"], "source_line": source_line(p["sources"]), "approved_on": p["approved_on"]})
    return items


def export_markdown(base: Path = HERE, today: Optional[date] = None) -> str:
    """Every saved entry in the knowledge/ file format, to add to knowledge/ by hand after a check."""
    today = today or date.today()
    out = ["# Approved research (exported from Agent Raahi)", "",
           f"Module: research · Exported: {today.isoformat()} · Each entry was approved by the supervising lawyer.",
           "", "---", ""]
    for e in learned(base):
        out += [f"### {e['heading']}", f"State: {e['state']}.", e["body"], f"Source: {e['source']}",
                f"Link: {e['link']}", f"Checked: {e['checked']} · Lawyer checked: {e['lawyer_checked']}", ""]
    return "\n".join(out)
