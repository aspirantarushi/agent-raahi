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


def check_points(raw: "llm.ResearchRaw", points: List[dict], resolve: Optional[Callable[[str], Optional[str]]] = None,
                 state: str = ""):
    """(kept points, dropped points, sources). A point is kept only if the words of the brief it comes
    from are backed by search results with an allowed official address. Links come only from the
    search results (raw.sources), never from the AI's own text."""
    brief = _norm(raw.brief)
    resolve = resolve or resolve_link
    sources = []
    for i, s in enumerate(raw.sources):
        url = resolve(s.get("uri", ""))
        sources.append({"index": i, "title": clean_title(s.get("title", ""), url), "url": url,
                        "allowed": bool(url) and allowed_link(url)})
    kept, dropped = [], []
    for p in points:
        kind = p.get("kind") if p.get("kind") in KINDS else "route"
        text = privacy.redact(_norm(str(p.get("text", ""))))[0][:2000 if kind == "letter" else 600]
        if not text:
            continue
        if kind == "letter":  # the app builds the letter itself: the AI's own letter is never shown to anyone
            continue
        if PREDICTION.search(text):
            dropped.append({"kind": kind, "text": text, "reason": "predicts an outcome"})
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
            if s["allowed"] and same_link(s["url"]) not in [same_link(o["url"]) for o in official]:
                official.append({"url": s["url"], "title": s["title"] or host(s["url"])})
        if not backing:
            dropped.append({"kind": kind, "text": text, "reason": "no search result backs it"})
        elif not official:
            dropped.append({"kind": kind, "text": text, "reason": "no official source among its search results"})
        else:
            kept.append({"kind": kind, "text": text, "sources": official})
    kept = merge_duplicates(kept)
    for n, p in enumerate(kept, 1):
        p.update(id=f"p{n}", status=WAITING, decided_on=None, decided_by=None, original=p["text"],
                 warnings=point_warnings(p, state))
    return kept, dropped, sources


def merge_duplicates(points: List[dict]) -> List[dict]:
    """Points of the same kind with the same sources say the same thing: keep one, with the more specific
    (longer) text, so the supervisor decides it once and the counts match what is shown."""
    out = []
    for p in points:
        links = frozenset(same_link(s["url"]) for s in p["sources"])
        twin = next((q for q in out if q["kind"] == p["kind"]
                     and frozenset(same_link(s["url"]) for s in q["sources"]) == links), None)
        if twin is None:
            out.append(p)
        elif len(p["text"]) > len(twin["text"]):
            twin["text"] = p["text"]
    return out


# ---------- checks shown to the supervisor ----------

def clean_title(title, url: Optional[str]) -> str:
    """A short readable source title: no site name tails ("... | Press Information Bureau"), no
    file-name noise, never empty (falls back to the site's address)."""
    t = privacy.redact(_norm(str(title or "")))[0]
    parts = [x.strip(" -|:") for x in re.split(r"\s*[|–—]\s*|\s+-\s+(?=[A-Z])", t) if x.strip(" -|:")]
    t = (parts[0] if len(parts[0]) >= 12 or len(parts) == 1 else f"{parts[0]}: {parts[1]}") if parts else ""
    t = re.sub(r"\.(pdf|aspx?|html?)$", "", t, flags=re.I).replace("_", " ").strip()
    if not t or t.casefold() in ("view", "home", "index", "page", "press release page"):
        t = host(url or "") or "source"
    return t[:100]


def same_link(url: str) -> str:
    """The same page written two ways (http/https, www, a trailing slash) counts once."""
    u = (url or "").strip().casefold()
    u = re.sub(r"^https?://(www\.)?", "", u).rstrip("/")
    return u


BLANK = re.compile(r"\[[^\]]*\]")


def only_blanks(letter: str) -> bool:
    """A "draft letter" point with no real words once the [blanks] and greetings are taken out."""
    words = re.findall(r"[A-Za-z\u0900-\u097F]{3,}", BLANK.sub(" ", letter))
    filler = {"dear", "sir", "madam", "subject", "date", "yours", "faithfully", "sincerely", "the", "and", "to",
              "from", "regards", "name", "address", "signature", "draft", "letter"}
    return len([w for w in words if w.casefold() not in filler]) < 8


LAW_NAME = re.compile(r"((?:[A-Z][A-Za-z()'’\-]+\s+(?:(?:of|and|the|for|on|to)\s+)*){1,7}"
                      r"(?:Act|Rules|Code|Regulations|Order))")
LAW_STOP = {"the", "of", "and", "act", "rules", "code", "regulations", "order", "in", "for", "on", "under", "a"}


# Parts of official web addresses that name a state ("labour.and.nic.in" is Andaman and Nicobar, "pblabour"...)
STATE_SITES = {
    "Andaman and Nicobar Islands": ["and", "andaman"], "Andhra Pradesh": ["ap", "andhra", "aponline"],
    "Arunachal Pradesh": ["arunachal", "arn"], "Assam": ["assam"], "Bihar": ["bihar", "bih", "br"],
    "Chandigarh": ["chandigarh", "chd"], "Chhattisgarh": ["cg", "chhattisgarh"], "Delhi": ["delhi"],
    "Goa": ["goa"], "Gujarat": ["gujarat", "gj"], "Haryana": ["haryana", "hr", "hry", "hrylabour"],
    "Himachal Pradesh": ["hp", "himachal"], "Jammu and Kashmir": ["jk", "jammu", "jkgad"],
    "Jharkhand": ["jharkhand", "jh"], "Karnataka": ["karnataka", "kar"], "Kerala": ["kerala"],
    "Ladakh": ["ladakh"], "Madhya Pradesh": ["mp", "mponline"], "Maharashtra": ["maharashtra", "mahakamgar", "mh"],
    "Manipur": ["manipur"], "Meghalaya": ["meghalaya"], "Mizoram": ["mizoram"], "Nagaland": ["nagaland"],
    "Odisha": ["odisha", "orissa"], "Puducherry": ["py", "puducherry"], "Punjab": ["punjab", "pb", "pblabour"],
    "Rajasthan": ["rajasthan", "raj"], "Sikkim": ["sikkim"], "Tamil Nadu": ["tn", "tamilnadu"],
    "Telangana": ["telangana", "ts"], "Tripura": ["tripura"], "Uttar Pradesh": ["up", "uplabour", "uttarpradesh"],
    "Uttarakhand": ["uk", "uttarakhand"], "West Bengal": ["wb", "westbengal", "wblc"],
}


def site_state(url: str) -> Optional[str]:
    """The state an official address belongs to, if a part of it names one; None for central sites."""
    labels = (host(url) or "").casefold().split(".")
    for state, codes in STATE_SITES.items():
        if any(c in labels[:-2] for c in codes):  # never the "gov.in" / "nic.in" ending
            return state
    return None


def point_warnings(p: dict, state: str = "") -> List[dict]:
    """Warnings the supervisor must see: a replaced law (cannot be approved without editing), or a
    source that is about a different law than the one the point names."""
    import replaced_laws
    out = [{"kind": "replaced", "text": r.warning(), "old": r.old, "new": r.new, "since": r.since.isoformat()}
           for r in replaced_laws.found_in(p["text"])]
    named = {w["old"] for w in out}
    titles = " | ".join(s.get("title", "") for s in p.get("sources", []))
    for r in replaced_laws.found_in(titles):  # the point may say only "the Act": its source shows which
        if r.old not in named:
            out.append({"kind": "replaced", "in_source": True, "old": r.old, "new": r.new, "since": r.since.isoformat(),
                        "text": f"Its source is the {r.old} (or rules under it), replaced by the {r.new} on "
                                f"{r.since.day} {r.since:%B %Y}: check before approving."})
    for name in dict.fromkeys(m.group(1).strip() for m in LAW_NAME.finditer(p["text"])):
        keys = [w for w in re.findall(r"[A-Za-z]{3,}", name.casefold()) if w not in LAW_STOP]
        titled = [s for s in p.get("sources", []) if re.search(r"\b(Act|Rules|Code|Regulations)\b", s.get("title", ""))]
        if keys and titled and not any(all(k in (s["title"] + " " + s["url"]).casefold() for k in keys) for s in titled):
            out.append({"kind": "mismatch", "text": f"The point names the {name}, but its source is "
                        f"\u201c{titled[0]['title']}\u201d: check that the source matches the law.",
                        "law": name, "title": titled[0]["title"]})
    if state:
        for s in p.get("sources", []):
            other = site_state(s["url"])
            if other and other.casefold() != state.casefold():
                out.append({"kind": "other_state", "text": f"This source is a website of {other}, but the case is "
                            f"in {state}: check that the rule applies in {state}.", "other": other, "state": state})
                break
    return out


def blocked(point: dict) -> List[str]:
    return [w["text"] for w in point.get("warnings", []) if w["kind"] == "replaced"]


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
    import replaced_laws
    asked = replaced_laws.search_text(issue)  # names the law in force today, so its pages come first
    try:
        raw = llm.research_issue(state, asked)
    except llm.AIUnavailable as google_err:
        if not llm.tavily_key():
            audit.add_event(case_id, "research failed", audit.VOLUNTEER, f"{search}: {google_err} (by {by})", base=base)
            raise ResearchFailed(FAILED) from None
        # Backup: Tavily on the official-site list, then a brief written only from those results
        search = llm.TAVILY_LABEL
        audit.log_research_search(case_id, search, f"{llm.GOOGLE_LABEL} did not work: {google_err}", base=base)
        try:
            raw = llm.research_issue_tavily(state, asked)
        except llm.AIUnavailable as err:
            audit.add_event(case_id, "research failed", audit.VOLUNTEER,
                            f"{llm.GOOGLE_LABEL}: {google_err}; {search}: {err} (by {by})", base=base)
            raise ResearchFailed(FAILED) from None
    try:
        points, split_model = llm.split_brief(raw.brief)
    except llm.AIUnavailable as err:
        audit.add_event(case_id, "research failed", audit.VOLUNTEER, f"{search}: {err} (by {by})", base=base)
        raise ResearchFailed(FAILED) from None
    kept, dropped, sources = check_points(raw, points, resolve or resolve_link, state)
    if not kept:
        audit.add_event(case_id, "research failed", audit.VOLUNTEER,
                        f"no point had an official source ({len(dropped)} dropped; by {by})", base=base)
        raise ResearchFailed(FAILED)
    record = {"id": _new_id(case_id, base), "case_id": case_id, "label": LABEL, "status": WAITING,
              "state": privacy.redact(state)[0][:60], "issue": privacy.redact(issue)[0][:300], "sent": raw.sent,
              "searched_as": privacy.redact(asked)[0][:360],
              "asked_by": by, "asked_at": tracker.now(), "model": raw.model, "split_model": split_model,
              "search": search,
              "queries": [privacy.redact(q)[0][:200] for q in raw.queries][:10],
              "sources_found": len(sources), "sources_official": sum(1 for s in sources if s["allowed"]),
              "points": kept, "dropped": dropped}
    storage.write_json("research", record["id"], record, base)
    audit.add_event(case_id, "research asked", audit.VOLUNTEER,
                    f"{LABEL}; search: {search}; model {raw.model}; {len(sources)} search results, "
                    f"{record['sources_official']} official; {len(kept)} points kept, {len(dropped)} dropped "
                    f"{_dropped_reasons(dropped)}; sites searched: {_sites(sources)} (by {by})", base=base)
    return record


def _sites(sources: List[dict]) -> str:
    """The official websites the points came from (site names only), for "What the agent did"."""
    names = sorted({urllib.parse.urlparse(x["url"]).netloc.lower().removeprefix("www.")
                    for x in sources if x.get("allowed") and x.get("url")})
    return ", ".join(names[:8]) or "none"


def _dropped_reasons(dropped: List[dict]) -> str:
    counts: Dict[str, int] = {}
    for d in dropped:
        counts[d.get("reason") or "no reason"] = counts.get(d.get("reason") or "no reason", 0) + 1
    return "(" + "; ".join(f"{r} ×{n}" for r, n in counts.items()) + ")" if counts else ""


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
           today: Optional[date] = None, by: str = "") -> dict:
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
    if decision == APPROVE and blocked(point):
        raise ResearchFailed("This point names a replaced law: edit it (to the current law) before approving.")
    if decision == EDIT:
        edited = privacy.redact(_norm(text or ""))[0][:2000]
        if not edited:
            raise ResearchFailed("Write the corrected point first.")
        import replaced_laws
        still = replaced_laws.still_relies_on_old(edited)
        if still:
            raise ResearchFailed(f"The edited point still names the {still[0].old} without the {still[0].new}.")
        point["text"] = edited
        point["warnings"] = [w for w in point.get("warnings", []) if w["kind"] != "replaced"]
    point.update(status={APPROVE: "approved", EDIT: "approved after editing", REJECT: "rejected"}[decision],
                 decided_on=today.isoformat(), decided_by=_norm(by)[:40] or audit.SUPERVISOR)
    if decision != REJECT:
        case = tracker.load(record["case_id"], base)
        if case is not None:
            case.setdefault("research_points", []).append({
                "research_id": research_id, "point_id": point_id, "issue": record["issue"], "state": record["state"],
                "kind": point["kind"], "text": point["text"], "sources": point["sources"],
                "approved_on": today.isoformat(), "approved_by": point["decided_by"]})
            tracker._note(case, "supervisor", f"research point approved ({research_id} {point_id})", volunteer=False)
            tracker._save(case, base)
    if all(p["status"] != WAITING for p in record["points"] if p.get("kind") != "letter"):
        record["status"] = REVIEWED
    storage.write_json("research", research_id, record, base)
    details = f"{research_id} {point_id} ({KINDS[point['kind']]})"
    if decision == EDIT:
        details += f": {point['original']} -> {point['text']}"
    audit.add_event(record["case_id"], f"research point {point['status']}", _norm(by)[:40] or audit.SUPERVISOR, details,
                    base=base, role="supervisor" if by else "")
    return point


# ---------- the volunteer's look at the research, before it goes to the supervisor ----------

VOLUNTEER_LABEL = "AI research, not yet checked by a lawyer"
KEPT, LEFT_OUT = "kept by the volunteer", "left out by the volunteer"


def waiting_for_case(case_id: Optional[str], base: Path = HERE) -> Optional[dict]:
    """The case's latest research still waiting for the supervisor (the one the volunteer sees)."""
    briefs = [r for r in (for_case(case_id, base) if case_id else []) if r.get("status") == WAITING]
    return briefs[-1] if briefs else None


def default_keep(point: dict) -> bool:
    """Pre-ticked for the letter unless it names a replaced law (the volunteer can still change it)."""
    return point.get("kind") != "letter" and not blocked(point)


def points_for_letter(record: Optional[dict], ticks: Dict[str, bool]) -> List[dict]:
    """The points the volunteer kept ({point id: ticked}), labelled as not yet checked by a lawyer.
    Draft-letter points from the AI are never used: the letter is made by code from the case facts."""
    if not record:
        return []
    return [dict(p, unchecked=True) for p in record["points"]
            if p.get("kind") != "letter" and ticks.get(p["id"], default_keep(p))]


def volunteer_review(research_id: str, ticks: Dict[str, bool], reasons: Dict[str, str], by: str,
                     base: Path = HERE) -> dict:
    """Saved when the volunteer sends the case: which points they kept for the letter and which they
    left out, with their reason. The volunteer never edits a point; the supervisor still decides each."""
    record = load(research_id, base)
    left = []
    for p in record["points"]:
        if p.get("kind") == "letter":  # the AI's own letter text is never used (the letter is made by code)
            continue
        keep = ticks.get(p["id"], default_keep(p))
        p["volunteer"] = KEPT if keep else LEFT_OUT
        p["volunteer_reason"] = "" if keep else privacy.redact(_norm(reasons.get(p["id"], "")))[0][:200]
        if not keep:
            left.append(f"{p['id']} ({p['volunteer_reason'] or 'no reason given'})")
    record["volunteer_reviewed"] = {"by": by, "on": date.today().isoformat()}
    storage.write_json("research", research_id, record, base)
    audit.add_event(record["case_id"], "research looked at by the volunteer", audit.VOLUNTEER,
                    f"{research_id}: kept {sum(p.get('volunteer') == KEPT for p in record['points'])}; "
                    f"left out: {', '.join(left) or 'none'}", base=base)
    return record


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
    """Save an approved point as a knowledge entry for its state, with Source, Link and "Approved by the
    supervisor (<name>, <date>)" (the supervisor may not be a lawyer). The next case in that state with a
    matching issue is then covered."""
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
             "approved_by": point.get("decided_by") or audit.SUPERVISOR, "lawyer_checked": "no",
             "approved_on": point.get("decided_on") or today.isoformat(), "keywords": words,
             "from_case": record["case_id"], "from_research": research_id, "point_id": point_id}
    storage.write_json("knowledge_added", entry["id"], entry, base)
    point["knowledge_id"] = entry["id"]
    storage.write_json("research", research_id, record, base)
    audit.add_event(record["case_id"], "research saved as knowledge", audit.SUPERVISOR,
                    f"{entry['id']} for {entry['state']}: {heading}", base=base)
    return entry


def approved_by(entry: dict) -> str:
    """Who approved a saved entry ("supervisor" for entries saved before names were kept)."""
    return entry.get("approved_by") or audit.SUPERVISOR


def approval_line(entry: dict) -> str:
    """"Approved by the supervisor (SK, 2026-11-05)": never "Lawyer checked", since the supervisor may not
    be a lawyer."""
    return f"Approved by the supervisor ({approved_by(entry)}, {entry.get('approved_on') or entry['checked']})"


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
                          "approved_on": e["checked"], "approved_by": approved_by(e)})
    for p in approved_points(case_id, base) if case_id else []:
        target = p["issue"] if p["issue"] in issues else (issues[0] if issues else p["issue"])
        if any(i["text"] == p["text"] and i["issue"] == target for i in items):
            continue
        items.append({"issue": target, "origin": "research", "kind": p["kind"], "heading": KINDS[p["kind"]],
                      "text": p["text"], "source_line": source_line(p["sources"]), "approved_on": p["approved_on"],
                      "approved_by": p.get("approved_by", "")})
    return items


def export_markdown(base: Path = HERE, today: Optional[date] = None) -> str:
    """Every saved entry in the knowledge/ file format, to add to knowledge/ by hand after a check."""
    today = today or date.today()
    out = ["# Approved research (exported from Agent Raahi)", "",
           f"Module: research · Exported: {today.isoformat()} · Each entry was approved by the supervisor.",
           "", "---", ""]
    for e in learned(base):
        out += [f"### {e['heading']}", f"State: {e['state']}.", e["body"], f"Source: {e['source']}",
                f"Link: {e['link']}", f"Checked: {e['checked']} · {approval_line(e)}", ""]
    return "\n".join(out)
