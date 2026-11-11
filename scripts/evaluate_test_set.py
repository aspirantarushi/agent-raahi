"""Run the 10 practice cases in practice_stories/test_set/ through the real app screens, like a volunteer.

Practice copy only: local storage in a throw-away folder, no real secrets file, no clinic passcode.
The real AI is used (keys from .env; backups allowed). The volunteer's answers come only from what each
story says; anything else is answered "Don't know". The app's screens are driven with Streamlit's
AppTest, so this is the same code a volunteer uses, without a browser.

Usage:  .venv/bin/python scripts/evaluate_test_set.py <output folder>
Writes one JSON transcript per run (what each screen showed, questions and answers, drafts, the AI
model, seconds taken). Score the transcripts by hand against practice_stories/test_set/ANSWER_KEY.md;
this script never scores or invents results. Today's date in the cases is 4 November 2026: the
Section 479 check is given that date; the "Any case" flow uses the computer's date.
"""

import json
import os
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.update(RAAHI_TEST="1", RAAHI_STORAGE="local", RAAHI_START_SCREEN="New case",
                  RAAHI_DATA_DIR=tempfile.mkdtemp(prefix="raahi-eval-"))
os.environ.pop("CLINIC_PASSCODE", None)
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import llm  # noqa: E402,F401  (reads the AI keys from .env)
from streamlit.testing.v1 import AppTest  # noqa: E402

TEST_SET = REPO / "practice_stories" / "test_set"
UNDERTRIAL = ("case01", "case02", "case03", "case04", "case05", "case06", "case10")
# Free legal aid questions: answered only from what the story says.
ELIGIBILITY = {
    "case01": {"in_custody": "Yes"}, "case02": {"in_custody": "Yes"}, "case03": {"in_custody": "Yes"},
    "case04": {"in_custody": "Yes"}, "case05": {"in_custody": "Yes"}, "case06": {"in_custody": "Yes"},
    "case07": {"woman": "Yes", "state": "Uttar Pradesh"}, "case08": {"woman": "Yes", "state": "Bihar"},
    "case09": {"state": "Bihar", "in_custody": "No", "woman": "No"}, "case10": {"in_custody": "Yes"},
}
# Section 479 check: the story gives only a month ("May 2024", "December 2023") and the app shows it
# under the question; the volunteer picks a day in that month (any day gives the same result).
DATES_479 = {"case02": {"offence_date": date(2024, 5, 31)}, "case05": {"offence_date": date(2023, 12, 31)}}


def screen(at) -> dict:
    values = lambda els: [e.value for e in els]  # noqa: E731
    return {"error": values(at.error), "warning": values(at.warning), "info": values(at.info),
            "success": values(at.success), "markdown": values(at.markdown), "caption": values(at.caption),
            "exceptions": [e.value for e in at.exception],
            "checkbox": [f"[{'x' if c.value else ' '}] {c.label}" for c in at.checkbox]}


def bold_text(at) -> str:
    return next((m.value.strip("*") for m in at.markdown if m.value.startswith("**") and m.value.endswith("**")), "?")


def any_case(at, key: str, log: dict) -> None:
    at.button(key="g-read").click().run()
    for _ in range(25):  # the questions, one at a time
        if any(b.key == "q-not-needed-go" for b in at.button):
            log["questions"].append({"q": "(the rest are not needed)", "a": "continue"})
            at.button(key="q-not-needed-go").click().run()
            continue
        count = next((m.value for m in at.markdown if 'class="q-count"' in m.value), None)
        if not count:
            break
        question, given = bold_text(at), None
        radios = [w for w in at.radio if w.key and w.key.startswith("ge-")]
        states = [w for w in at.selectbox if w.key == "ge-state"]
        if states and ELIGIBILITY[key].get("state"):
            given = ELIGIBILITY[key]["state"]
            states[0].set_value(given)
        elif radios and ELIGIBILITY[key].get(radios[0].key[3:]):
            given = ELIGIBILITY[key][radios[0].key[3:]]
            radios[0].set_value(given)
        log["questions"].append({"count": re.sub("<[^>]+>", "", count), "q": question, "a": given or "Don't know"})
        prefix = "gnext-" if given else "gskip-"
        next(b for b in at.button if b.key and b.key.startswith(prefix) and b.key != "gskip-all").click().run()
    at.run()  # research runs by itself after the cards: run again so its result is on screen
    gen = at.session_state["gen"] if "gen" in at.session_state else None
    log["model"] = gen.get("model") if gen else None
    log["removed"] = gen.get("removed") if gen else None
    log["drafts"] = list(at.session_state["shown_drafts"]) if "shown_drafts" in at.session_state else []


def section_479(at, key: str, log: dict) -> None:
    at.radio(key="case_type").set_value("Undertrial").run()
    at.text_area(key="f_notes").set_value(log["story"])
    at.button(key="f-read").click().run()
    ai = at.session_state["ai"] if "ai" in at.session_state else None
    if ai:
        log["model"], log["removed"] = ai.get("model"), ai.get("removed")
        log["ai_values"] = {k: str(v) for k, v in ai["values"].items()}
    for _ in range(12):
        skip = [b for b in at.button if b.key and b.key.startswith("skip-") and b.key != "skip-all"]
        if not skip:
            break
        fact = skip[0].key[5:]
        hint = [c.value for c in at.caption if c.value.startswith("The notes say")]
        given = DATES_479.get(key, {}).get(fact)
        log["questions"].append({"q": bold_text(at), "fact": fact, "hint": hint,
                                 "a": str(given) if given else "Don't know"})
        if given:
            at.date_input(key=f"q-{fact}").set_value(given)
            at.button(key=f"next-{fact}").click().run()
        else:
            skip[0].click().run()
    if any(c.key == "f_checked" for c in at.checkbox):
        at.checkbox(key="f_checked").check().run()
    at.session_state["f_today"] = date(2026, 11, 4)
    at.run()
    lawyer = [r for r in at.radio if r.key == "f_lawyer"]
    if lawyer and lawyer[0].value is None:
        lawyer[0].set_value("Don't know").run()
    make = next((b for b in at.button if b.label.startswith("Make draft")), None)
    if make:
        make.click().run()
        draft = at.session_state["draft"] if "draft" in at.session_state else None
        log["drafts"] = [draft["text"]] if draft and draft.get("text") else []


def run(case_file: Path, mode: str, ui_lang: str = "en") -> dict:
    key = case_file.stem[:6]
    log = {"case": case_file.stem, "mode": mode, "ui_lang": ui_lang, "questions": [],
           "story": case_file.read_text(encoding="utf-8")}
    started = time.time()
    at = AppTest.from_file(str(REPO / "app.py"), default_timeout=240).run()
    if ui_lang != "en":
        at.radio(key="ui_lang").set_value(ui_lang).run()
    if mode == "any":
        at.text_area(key="g_notes").set_value(log["story"])
        any_case(at, key, log)
    else:
        section_479(at, key, log)
    log["seconds"] = round(time.time() - started, 1)
    log["screen"] = screen(at)
    return log


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for case_file in sorted(TEST_SET.glob("case*.txt")):
        jobs.append((case_file, "any", "en"))
        if case_file.stem[:6] in UNDERTRIAL:
            jobs.append((case_file, "479", "en"))
        if case_file.stem.startswith("case08"):
            jobs.append((case_file, "any", "hi"))  # the Hindi story with the app in Hindi
    for case_file, mode, ui_lang in jobs:
        log = run(case_file, mode, ui_lang)
        name = f"{case_file.stem}_{mode}{'' if ui_lang == 'en' else '_' + ui_lang}.json"
        (out / name).write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"{name}: {log['seconds']} s, AI: {log.get('model')}, questions: {len(log['questions'])}, "
              f"crashes: {len(log['screen']['exceptions'])}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="raahi-eval-out-")))
