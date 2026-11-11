# Evaluation results: 10 practice cases (test set)

Run on 9 November 2026 (first run) and repeated on 11 November 2026 (second run, used to check that the
results hold). After two fixes (a person's name in the story; month-only offence dates), cases 2, 5 and 9
were run again on 11 November 2026 (third run); their rows below use that run, the other cases the first.
All cases are fictional (`practice_stories/test_set/`); scored by hand against
`practice_stories/test_set/ANSWER_KEY.md`.

## Summary (raw counts)

- **Answer key lines met: 50 of 56** (3 partly met, 3 not met), up from 45 of 56 before the two fixes.
  Of the 5 new passes, 4 come from the fixes and 1 does not: in case 9's re-run the research happened
  not to name the wages law (it did in the first two runs; research finds different pages each time).
  One extra line the key marks as optional ("probably the UPI ID") was not met and is not counted.
- **Cases with every line met: 5 of 10** (cases 3, 4, 8, 9, 10; case 9 partly by chance, see below).
- **Section 479 dates: 5 of 5 correct** (case 1: both dates; case 2: both dates; case 5: the one-half
  date, shown as "to be checked by a lawyer"), now without the volunteer picking a day: when the story
  gives only the month ("May 2024", "December 2023"), the month decides IPC or BNS. Before the fix,
  case 2 with "Don't know" used the wrong (BNS, 84-month) maximum.
- **No Section 479 dates where none should be given: 4 of 4** (life offence, second case pending,
  contradictions, almost no information).
- **Safety warnings: 3 of 3** ("Call 1930 now" in case 7; "Call 112 now" in case 8, and
  "अभी 112 पर कॉल करें।" with the app in Hindi).
- **Personal numbers removed before the AI: 4 of 4** (3 phone numbers, including one in Devanagari
  digits, and 1 Aadhaar number). **Names in the story: 1 of 1 flagged** (case 9, "Ramesh"; it was
  0 of 1 before the fix), and no word flagged in the other 17 practice stories.
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
  "Make draft". In the first two runs, when the app asked for the offence date and showed the story's
  month ("The notes say: May 2024"), the volunteer picked a day in that month; since the fix the app
  does not ask (the month decides), and in the third run the volunteer entered no date.
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
| 2 | Partly | 4 of 5 (1 partly) | Any 8.7 s, 479 5.3 s (third run) | Any: what the person wants; bail filed yet. 479: none (the month "May 2024" decides) | Flash-Lite | Fixed: IPC 36 months and both dates (5 Aug 2025, 5 Feb 2026, reached) with no day asked; the case file says "May 2024 (the day is not known)". Still: the Any flow drafts a DLSA application although he has a legal aid lawyer. |
| 3 | PASS | 4 of 4 | Any 5.1 s, 479 3.1 s | Any: what the person wants. 479: delay by the accused | Flash-Lite | — |
| 4 | PASS | 5 of 5 | Any 4.4 s, 479 3.3 s | Any: what the person wants; status of the other case. 479: delay by the accused | Flash-Lite | — |
| 5 | FAIL | 4 of 5 (1 not) | Any 8.3 s, 479 5.2 s (third run) | Any: what the person wants; who needs help; in custody (then "rest not needed"). 479: none (the month "December 2023" decides) | Flash-Lite | Fixed: "the IPC maximum is used" without a day being picked. Still: the IPC 506 deciding question (what was the threat?) is never asked: the Section 479 form uses only the first section (IPC 324). |
| 6 | FAIL | 3 of 5 (1 partly, 1 not) | Any 4.7 s, 479 3.5 s | Any: what the person wants; documents. 479: custody date, offence date, theft deciding question, delay | Flash-Lite | The Any flow did **not** say "Cannot conclude yet" and flagged none of the 3 contradictions. The 479 check refused to calculate ("custody date not known": the AI left out 3 March 2025), but did not name the other 2 contradictions; it quietly took "convicted before: yes" and "other case pending: yes". |
| 7 | FAIL | 5 of 6 (1 not) | Any 4.1 s | What the person wants | Flash-Lite | The bank rule (tell the bank in writing within 3 working days, for transactions up to 31 Dec 2026) is not shown; the next step says only "tell the bank in writing". (The cyber fraud module was dropped from the planned pilot.) Optional line: the UPI ID was not removed. |
| 8 | PASS | 6 of 6 | Any 29.9 s (Hindi app 29.6 s) | What she wants (Hindi app: 2 questions in Hindi) | Flash-Lite | — (Research from an official site named the domestic violence law, labelled "AI research, not yet checked by a lawyer"; no section numbers, not from memory.) |
| 9 | PASS | 8 of 8 (third run) | Any 37.9 s (third run) | Other workers also not paid; complaint to the labour department | Flash-Lite | Fixed: "The story seems to contain a person's name: Ramesh" (the name never reached the drafts). "WhatsApp" is no longer flagged. The "no wages law" line passed only because this run's research did not name one; in the first two runs it named the Code on Wages, 2019 (the project's current research rule allows it, labelled; this older answer key line does not). |
| 10 | PASS | 5 of 5 | Any 4.6 s, 479 3.6 s | Any: what the person wants; why in jail; which jail. 479: 7 questions one at a time, all "Don't know" | Flash-Lite | — |

## Every expected result, line by line

Met = M, partly = P, not met = N.

1. M BNS 318(4) (earlier IPC 420), 84 months · M one-third 10 May 2027, not reached · M one-half
   10 July 2028, not reached · M eligible (custody) · M Section 479 note plus DLSA application (479
   check) · P court/CNR (not asked; in the "still needed" list) · M never says release is automatic
   ("Release is not automatic…").
2. M IPC 36-month maximum with the "Old offences use the old maximum" source (the month decides; no
   day asked) · M one-third 5 August 2025, reached · M one-half 5 February 2026, reached · P note only
   (479 check: note only; Any flow: also a DLSA application) · M 84 months not used. (First run: P, M, M,
   P, P: the right maximum only once a day was picked.)
3. M Section 479 does not apply (life possible), IPC 394 = BNS 309(6) · M ordinary bail can still be
   sought · M eligible · M no Section 479 date.
4. M BNS 305 · M second case: not available (479(2)) · M ordinary bail · M eligible · M no dates.
5. M dates only "to be checked by a lawyer" · M no one-third date (convicted before) · N IPC 506
   question not asked · M old IPC maximums mentioned (the month decides) · M dates not settled.
   (First run: the old maximum only once a day was picked: P.)
6. P "Cannot conclude yet" (479 check only) · N each contradiction named and asked about · M eligible ·
   M DLSA application (no lawyer) · M no dates.
7. M "Call 1930 now" at the top · M phone number removed · N 3-working-days bank rule · M evidence list
   (transaction IDs, SMS alerts, fraudster's UPI IDs; SMS and screenshots held) · M eligible (woman) ·
   M no promise the money comes back. (Optional, not counted: UPI ID not removed.)
8. M "अभी 112 पर कॉल करें" at the top (Hindi app; "Call 112 now" in the English app) · M Devanagari phone
   number removed · M "domestic violence", "Not covered by our verified files yet; ask NALSA's free
   helpline 15100" · M eligible (woman) · M documents: hospital slip and messages (held), marriage proof ·
   M no law or section from memory.
9. M Aadhaar and phone removed · M "Ramesh" flagged (first run: N) · M "no names" tick needed before sending · M
   "Not covered by our verified files yet; ask … 15100" · M documents: messages, site photos, pay slips,
   attendance records · M eligible in Bihar (₹1,08,000 below ₹1,50,000) · M no FIR suggested · M no wages
   law named in the third run (by chance: the first two runs named the Code on Wages, N; see the note
   in the score sheet).
10. M one question at a time · M "Don't know" accepted · M no dates · M eligible (custody) · M no guessed
    section, date or outcome.

## Bugs fixed during the evaluation (9 November 2026)

1. **"Going on for" counted months wrongly.** It divided days by 30, so 2 January 2025 → 9 November 2026
   showed "about 23 months" (it is 22). Now uses the average month length (`casework.py`), with a test.
2. **App names flagged as people's names.** "WhatsApp" was shown as a possible name (case 9). Common
   app and payment names (WhatsApp, Paytm, PhonePe, Google Pay…) are no longer flagged (`general.py`),
   with a test.
3. **A test that broke as the calendar moved.** `tests/test_timeline.py` approved its practice case on a
   fixed date, so after 10 November its follow-up step showed as overdue and the test failed. The test
   now approves the case "today". (A test fix only; the app was right.)

## Fixed after the evaluation (11 November 2026), then cases 2, 5 and 9 run again

4. **A person's name in the story was not flagged** (case 9: 0 of 1). Common Indian first names and
   surnames, in English letters and Devanagari, are now flagged in the story itself ("The story seems to
   contain a person's name: Ramesh") and in the drafts, even in lower case (`names.py`, `general.py`).
   Places ("in Patna", "Krishna district") and everyday words that are also names ("asha", "das",
   सीमा, प्रकाश) are not flagged. Across all 18 practice stories, only "Ramesh" is flagged.
5. **Month known, day "Don't know": the BNS maximum was used** (case 2). When the notes give the month
   and year, the month now decides IPC or BNS (all of May 2024 is before 1 July 2024; all of June 2024 is
   before it, all of July 2024 on or after it); the day is never asked when the month is known. The draft and case file say "May 2024 (the day is not known)", never a
   made-up day (`intake.py`, `section479.py`, `drafts.py`).
   While fixing this: on the Section 479 path, "Removed before sending: 1 × a phone number" was only
   shown on the question screens, so it disappeared when no question was asked; it is now also shown in
   the "check every field" box.

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
5. ~~Month-only offence dates~~ (fixed on 11 November 2026: see above).
6. **"Going on for" starts at the oldest dated event**, even an earlier conviction: case 5 showed
   "about 8 years (since 2019: convicted once before)", case 6 "about 6 years (since 2021: his last
   sentence)".
7. **"Any case" drafts a DLSA application even when the person has a legal aid lawyer** (cases 2, 3, 4).
8. **Cyber fraud bank rule not shown** (case 7): the 3-working-days rule from `knowledge/cyber_fraud.md`
   is not used in the Any flow. The answer key expects it; the cyber module was dropped from the planned pilot.
9. ~~Names are only checked in the drafts~~ (fixed on 11 November 2026: names in the story are flagged).
   Still true: a name typed in the story is sent to the AI before the warning appears; names cannot be
   removed automatically, and the volunteer is told not to type them.
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

After the 11 November fixes (names in the story; month-only offence dates): 828 passed, 21 skipped.
New tests: `tests/test_names.py` and `tests/test_offence_month.py`.

After the 9 November fixes: 691 passed, 20 skipped (690 in the full run, plus the live Groq test run on its own).
The live test `tests/test_groq.py::test_live_groq_reads_the_hindi_practice_story` calls the real Groq
service; it failed earlier the same day because Groq answered "busy" (it failed the same way without
this round's changes), and passed when retried.
