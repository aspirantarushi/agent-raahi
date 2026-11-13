# Practice run, 13 November 2026

**This was a practice run with fictional cases, not a real deployment.** No real person, case or document was
used. Every story came from [docs/practice_run/stories.md](practice_run/stories.md), written for this exercise.

## What it was

- **When:** 13 November 2026 (the supervisor's review was done afterwards, the same night).
- **Who:** five law-school volunteers, called *Volunteer A* to *Volunteer E*, and one *Supervisor*. No real names
  were used anywhere in the app.
- **Where:** the live app, running as the *Agent Raahi Practice Clinic* (practice data only).
- **What they did:** each volunteer took the fictional stories in their sheet
  ([docs/practice_run/](practice_run/README.md)): read the story with the agent, answered its questions, ran
  research on official websites where our files did not cover the problem, made the drafts and sent them to the
  supervisor. The supervisor then reviewed the research points and the drafts, and approved or sent them back.

## The numbers

Counts and timings only, from the Practice Clinic's own records (no story text). All cases are fictional.

**Cases**

| | |
| --- | --- |
| Cases started | 15 (14 "Any problem" story cases, 1 Section 479 form case) |
| Sent to the supervisor | 7 |
| Approved by the supervisor | 6 |
| Drafts sent back to the volunteer | 1 |
| Closed | 0 |
| Started but not sent | 8 |

**Time from "Story read" to "Sent to the supervisor":** median **4.4 minutes** over 5 cases (2.6, 4.3, 4.4,
4.5 and 6.1 minutes). Left out: one case continued about five hours later with "Continue a case", and the
Section 479 case, which used the form and had no story to read (opened to sent: 3.6 minutes).

**Questions the agent asked per case:** median **1** (from 0 to 4) over the 14 story cases; 20 in all.

**Research on official websites**
- 12 searches on 11 cases: 9 found points, 3 found nothing usable.
- 30 research points in all. On the 5 sent cases that had research, volunteers kept 18 points and left out 0.
  The other 12 points were on 4 cases that were never sent, so no volunteer looked at them.
- The supervisor approved 28, rejected 0 and left 2 not decided (on a case that was never sent). 12 of the 28
  approvals were on cases that were never sent.

**Self-approval:** the app never lets the person who sent a case (or asked for its research) approve it. It
blocks this on screen but does not log attempts, so there is no count.

**AI services:** Gemini's free daily limit was reached during the run. Reading the stories still worked every
time (7 readings answered by Gemini after retries, 1 by the Groq backup). Gemini's web-search research hit the
limit on all 12 searches, so every search used the backup search service (Tavily, official sites only); 9 found
points and 3 found nothing usable. Before real use the clinic should use a paid AI tier.

(The problems log at the time recorded these 12 searches as "the form opened instead"; that wording was wrong for
research and now reads "research used the backup search".)

## What volunteers told us

[to fill]

- [to fill]
- [to fill]
- [to fill]

## What we changed after the practice run

All in the public repository, from commit `fdf8ed6` onwards (13–14 November 2026).

**Reading the story and the facts**
- A case is marked "in custody" only when the story itself mentions jail, arrest, custody or police lock-up
  (one practice story about an electricity bill was wrongly marked "in custody").
- Repeated facts are joined, every amount, age and place in the story is kept, and the "Problem" line says what
  went wrong ("electricity cut off despite a paid bill"), not just a topic.
- "Going on for" counts from when the problem began (the cut, the stop), not from an earlier ordinary event, and
  never writes "since after April 2026".
- "What the person wants" holds only the request ("The pension restarted with arrears"), not "The person wants …".
- Each kind of problem has its own list of papers; pensions now ask for the pension order, the bank passbook and
  the last payment entry, never a ration card receipt. Paper names start with a capital letter, and nobody in a
  free legal aid group (in custody, a woman, a child …) is asked for an income affidavit.

**The volunteer's steps**
- Clearer numbered steps ("Done", "Now", "Not yet"), one filled button for the next step, and on phones a "Next:"
  bar at the bottom.
- One readiness checklist with the documents in it (each "Has it", "Still to get" or "Can't get" with a reason),
  the same red required mark in every case type, and next steps written plainly with only the date in bold
  ("Dates are suggested follow-ups, not legal deadlines.").
- A research point left out of the letter needs a short reason, chosen with one tap; one "Send anyway" box covers
  all of them, so the Send button is never stuck.
- When drafts are sent back, the volunteer sees "Sent back: <reason>" on the case and in the Case tracker.

**The supervisor's page**
- One list, "Waiting for you", then one case at a time, in one box, in three steps: understand the case, check
  the research points, decide on the drafts.
- Research points are one tick list (tick = approve, untick = reject with a reason, "Approve all points"); points
  not decided stay out of the letter, and the letter is rebuilt from the approved points only.
- Two different decisions, clearly named everywhere: "Point rejected" (only out of the letter) and "Drafts sent
  back" (the case goes back to the volunteer).
- Drafts can be approved with points still undecided, in one click; the supervisor who sent a case or asked for
  its research still can never approve it.
- Cases with research but no drafts are labelled "Research only — no drafts yet" and show the case from its
  tracker record.

**Phones and layout**
- Checked on a 375-pixel phone screen: no overlapping boxes, no sideways scrolling, a compact top bar, and no box
  drawn inside another box.
- A bug that printed a block of Streamlit's own documentation on the Case tracker was fixed, with a test that
  stops it coming back.
- The problems log now says what really happens when the AI gives up: for research, "research used the backup
  search"; for reading a story, "the form opened instead".

**Trying it**
- The README has a "Try the Practice Clinic" section with the practice passcodes and a 3-minute path, and the
  supervisor can reset the Practice Clinic to a saved snapshot of the practice cases.

All of these changes have tests; the full test suite runs on every change.
