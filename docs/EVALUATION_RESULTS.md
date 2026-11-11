# Evaluation results: 10 practice cases (test set)

Run on 9 November 2026 (first run, scored below) and repeated on 11 November 2026 (second run, used to
check that the results hold). All cases are fictional (`practice_stories/test_set/`); scored by hand
against `practice_stories/test_set/ANSWER_KEY.md`.

## Summary (raw counts)

- **Answer key lines met: 45 of 56** (6 partly met, 5 not met). One extra line the key marks as
  optional ("probably the UPI ID") was not met and is not counted.
- **Cases with every line met: 4 of 10** (cases 3, 4, 8, 10).
- **Section 479 dates: 5 of 5 correct** (case 1: both dates; case 2: both dates; case 5: the one-half
  date, shown as "to be checked by a lawyer"). Case 2 and case 5 were right only after the volunteer
  picked a day in the month the story gives ("May 2024", "December 2023"); with "Don't know", case 2
  used the wrong (BNS, 84-month) maximum, flagged "to be checked by a lawyer".
- **No Section 479 dates where none should be given: 4 of 4** (life offence, second case pending,
  contradictions, almost no information).
- **Safety warnings: 3 of 3** ("Call 1930 now" in case 7; "Call 112 now" in case 8, and
  "अभी 112 पर कॉल करें।" with the app in Hindi).
- **Personal numbers removed before the AI: 4 of 4** (3 phone numbers, including one in Devanagari
  digits, and 1 Aadhaar number). Names: 0 of 1 flagged (case 9, see below).
- **Free legal aid result: 10 of 10 correct.**
- **Crashes: 0** in 35 runs (17 in each run, plus case 8 with the app in Hindi in the second run).
- **AI used: gemini-3.5-flash-lite answered every run**; the backups (Gemini 3.8 Flash, Groq) were
  never needed.
- **Time:** the app's own processing time was 3–7 seconds per case, and about 30 seconds when
  research from official sources ran (cases 8 and 9). This is machine time only. **A volunteer's
  real minutes (reading, typing, checking) were not measured**; that needs the planned study with two
  volunteers and one reviewer.

These are counts from one tester driving the app on 10 fictional cases. They do not show that the app
improves outcomes or saves time for real volunteers, and they should not be read that way.

## How it was run

- **Practice copy:** local storage in a throw-away folder, no real secrets file, no clinic passcode,
  real AI (keys from `.env`, backups allowed). The real app screens were driven with Streamlit's
  AppTest (the same code a volunteer uses, without a browser): `scripts/evaluate_test_set.py`.
- **Like a volunteer:** each story was pasted into New case → "Any case (start here)" → "Read the
  story". Questions were answered only from what the story says (for example "Yes" to "in custody" when
  the story says so); everything else got "Don't know". Undertrial cases (1–6, 10) were also run
  through "Open Section 479 check", with today's date set to 4 November 2026 as the cases say, then
  "Make draft". When the app showed the story's month-only offence date under the question ("The notes
  say: May 2024"), the volunteer picked a day in that month (any day gives the same result).
- **Date:** the "Any case" screens use the computer's date (9 November), not 4 November. No scored
  result depends on that difference.
- **Second run:** every scored result was the same. The AI's follow-up questions varied in wording and
  number (for example case 9: 2 questions in the first run, 0 in the second), and research found
  different points on official pages each time.

## Score sheet

"Any" = the "Any case" flow; "479" = the Section 479 check. Questions are those asked in the first run.

| # | Result | Lines met | App time | Questions asked (first run) | AI | What went wrong |
|---|---|---|---|---|---|---|
| 1 | Partly | 6 of 7 (1 partly) | Any 6.5 s, 479 3.5 s | Any: what the person wants; which state. 479: none (all facts found) | Flash-Lite | Court/CNR not asked as a question; listed as "still needed" in the draft's readiness list. |
| 2 | Partly | 2 of 5 (3 partly) | Any 5.6 s, 479 4.3 s | Any: what the person wants; bail applied for yet; last met the lawyer. 479: offence date (hint "May 2024" shown) | Flash-Lite | With "Don't know" for the offence date, BNS 84 months was used (5 Dec 2026 / 5 Feb 2028), flagged "to be checked by a lawyer". Right (IPC 36 months, both dates reached) once a day in May 2024 was picked. The Any flow also drafts a DLSA application although he has a legal aid lawyer. |
| 3 | PASS | 4 of 4 | Any 5.1 s, 479 3.1 s | Any: what the person wants. 479: delay by the accused | Flash-Lite | — |
| 4 | PASS | 5 of 5 | Any 4.4 s, 479 3.3 s | Any: what the person wants; status of the other case. 479: delay by the accused | Flash-Lite | — |
| 5 | FAIL | 3 of 5 (1 partly, 1 not) | Any 5.9 s, 479 3.8 s | Any: what the person wants; documents; court status; who needs help; in custody (then "rest not needed"). 479: offence date (hint "December 2023") | Flash-Lite | The IPC 506 deciding question (what was the threat?) is never asked: the Section 479 form uses only the first section (IPC 324). "Old IPC maximum" is said only after the volunteer picks a December 2023 date. |
| 6 | FAIL | 3 of 5 (1 partly, 1 not) | Any 4.7 s, 479 3.5 s | Any: what the person wants; documents. 479: custody date, offence date, theft deciding question, delay | Flash-Lite | The Any flow did **not** say "Cannot conclude yet" and flagged none of the 3 contradictions. The 479 check refused to calculate ("custody date not known": the AI left out 3 March 2025), but did not name the other 2 contradictions; it quietly took "convicted before: yes" and "other case pending: yes". |
| 7 | FAIL | 5 of 6 (1 not) | Any 4.1 s | What the person wants | Flash-Lite | The bank rule (tell the bank in writing within 3 working days, for transactions up to 31 Dec 2026) is not shown; the next step says only "tell the bank in writing". (The cyber fraud module was dropped from the planned pilot.) Optional line: the UPI ID was not removed. |
| 8 | PASS | 6 of 6 | Any 29.9 s (Hindi app 29.6 s) | What she wants (Hindi app: 2 questions in Hindi) | Flash-Lite | — (Research from an official site named the domestic violence law, labelled "AI research, not yet checked by a lawyer"; no section numbers, not from memory.) |
| 9 | FAIL | 6 of 8 (2 not) | Any 28.4 s | Attendance records; contacted the contractor or labour office before | Flash-Lite | "Ramesh" not flagged as a possible name (the AI described him by role, so the name never reached the drafts; the check only looks at the drafts). "WhatsApp" was wrongly flagged (fixed). Research named the Code on Wages, 2019: this matches the project's current research rule but not this older answer key line ("must NOT name a wages law"). |
| 10 | PASS | 5 of 5 | Any 4.6 s, 479 3.6 s | Any: what the person wants; why in jail; which jail. 479: 7 questions one at a time, all "Don't know" | Flash-Lite | — |

## Every expected result, line by line

Met = M, partly = P, not met = N.

1. M BNS 318(4) (earlier IPC 420), 84 months · M one-third 10 May 2027, not reached · M one-half
   10 July 2028, not reached · M eligible (custody) · M Section 479 note plus DLSA application (479
   check) · P court/CNR (not asked; in the "still needed" list) · M never says release is automatic
   ("Release is not automatic…").
2. P IPC 36-month maximum with the "Old offences use the old maximum" source (only once a date is
   picked) · M one-third 5 August 2025, reached · M one-half 5 February 2026, reached · P note only
   (479 check: note only; Any flow: also a DLSA application) · P must not use 84 months (it did, with
   "Don't know", flagged "to be checked by a lawyer").
3. M Section 479 does not apply (life possible), IPC 394 = BNS 309(6) · M ordinary bail can still be
   sought · M eligible · M no Section 479 date.
4. M BNS 305 · M second case: not available (479(2)) · M ordinary bail · M eligible · M no dates.
5. M dates only "to be checked by a lawyer" · M no one-third date (convicted before) · N IPC 506
   question not asked · P old IPC maximums mentioned (only once a date is picked) · M dates not settled.
6. P "Cannot conclude yet" (479 check only) · N each contradiction named and asked about · M eligible ·
   M DLSA application (no lawyer) · M no dates.
7. M "Call 1930 now" at the top · M phone number removed · N 3-working-days bank rule · M evidence list
   (transaction IDs, SMS alerts, fraudster's UPI IDs; SMS and screenshots held) · M eligible (woman) ·
   M no promise the money comes back. (Optional, not counted: UPI ID not removed.)
8. M "अभी 112 पर कॉल करें" at the top (Hindi app; "Call 112 now" in the English app) · M Devanagari phone
   number removed · M "domestic violence", "Not covered by our verified files yet; ask NALSA's free
   helpline 15100" · M eligible (woman) · M documents: hospital slip and messages (held), marriage proof ·
   M no law or section from memory.
9. M Aadhaar and phone removed · N "Ramesh" flagged · M "no names" tick needed before sending · M
   "Not covered by our verified files yet; ask … 15100" · M documents: messages, site photos, pay slips,
   attendance records · M eligible in Bihar (₹1,08,000 below ₹1,50,000) · M no FIR suggested · N no wages
   law named (see note above: answer key older than the research flow).
10. M one question at a time · M "Don't know" accepted · M no dates · M eligible (custody) · M no guessed
    section, date or outcome.

## Bugs fixed in this round

1. **"Going on for" counted months wrongly.** It divided days by 30, so 2 January 2025 → 9 November 2026
   showed "about 23 months" (it is 22). Now uses the average month length (`casework.py`), with a test.
2. **App names flagged as people's names.** "WhatsApp" was shown as a possible name (case 9). Common
   app and payment names (WhatsApp, Paytm, PhonePe, Google Pay…) are no longer flagged (`general.py`),
   with a test.
3. **A test that broke as the calendar moved.** `tests/test_timeline.py` approved its practice case on a
   fixed date, so after 10 November its follow-up step showed as overdue and the test failed. The test
   now approves the case "today". (A test fix only; the app was right.)

## Problems found but not fixed (for you to decide)

Needs your permission (these are in templates/ or knowledge/):

1. **The complaint letter says "these points approved by the supervisor"** even when it is drafted from
   the volunteer's ticked points that nobody has approved yet (cases 8 and 9). Each point is still
   labelled "AI research, not yet checked by a lawyer", but the heading line is wrong. The line is in
   `templates/complaint_letter.md` (line 31). Suggested fix: a blank for that line, filled by code with
   "approved by the supervisor" or "ticked by the volunteer, not yet checked by a lawyer".
2. **The source line under every Section 479 result says "BNS, 2023, Section 305"**, whatever the
   offence, because the knowledge entry "How to work out the Section 479 dates" uses BNS 305 as its
   example (`knowledge/undertrial_bail.md`). Confusing on a 318(4) or 384 case.

Bigger changes (not clear-cut bug fixes):

3. **Contradictions are not checked in "Any case"** (case 6). The contradiction checks exist only in
   the Section 479 check, and even there only the custody date was named.
4. **Only the first section is used in the Section 479 check** (case 5), so the IPC 506 deciding
   question is never asked, and the draft says "and other sections [___]" although IPC 506 is known.
5. **Month-only offence dates.** "May 2024" is enough to know the offence was before 1 July 2024,
   but the volunteer has to pick a day; "Don't know" gives the higher BNS maximum (flagged).
6. **"Going on for" starts at the oldest dated event**, even an earlier conviction: case 5 showed
   "about 8 years (since 2019: convicted once before)", case 6 "about 6 years (since 2021: his last
   sentence)".
7. **"Any case" drafts a DLSA application even when the person has a legal aid lawyer** (cases 2, 3, 4).
8. **Cyber fraud bank rule not shown** (case 7): the 3-working-days rule from `knowledge/cyber_fraud.md`
   is not used in the Any flow. The answer key expects it; the cyber module was dropped from the planned pilot.
9. **Names are only checked in the drafts.** "Ramesh" was sent to the AI in the story (the screen warns
   that names can't be removed automatically) and was not flagged because it never reached the drafts.
10. **Answer key older than the research flow** (cases 8 and 9): it expects no law to be named, but
    research from official sources now names the current law, labelled as not yet checked. The key
    may need updating.
11. **Research details:** the Hindi-app run of case 8 had a research point "an appeal must be filed
    within thirty days" ticked by default (about appeals, not a first application); research points
    show in English in the Hindi app; some research link titles from labour.gov.in PDFs are garbled
    ("रोिगार", "अजधसूचना").
12. **Small wording issues:** case 8's English draft keeps "कल रात" ("last night") in the timeline; case 9's
    letter says "I request: wants his money"; case 2's documents list "The person has: FIR" when the
    story only says what section the FIR is under; case 6's timeline shows "arrested under [law
    reference removed: ask a lawyer]" (the deliberate rule that strips the AI's law references).
13. **The UPI ID in case 7 was not removed** (the key says "probably"; it is the fraudster's ID).

## Test results

After the fixes: 691 passed, 20 skipped (690 in the full run, plus the live Groq test run on its own).
The live test `tests/test_groq.py::test_live_groq_reads_the_hindi_practice_story` calls the real Groq
service; it failed earlier the same day because Groq answered "busy" (it failed the same way without
this round's changes), and passed when retried.
