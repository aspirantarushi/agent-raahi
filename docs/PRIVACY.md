# Privacy: what Agent Raahi stores, where it goes, who can see it, how it is deleted

> **Prototype: practice data only. No real person's data has been entered.**
> Every story, case and draft in this app and in this repository is made up for practice.
> The live app runs as the *Agent Raahi Practice Clinic*. Its two passcodes are published in the README on
> purpose so anyone can try it: they are practice-only, used nowhere else, and protect fictional data only.
> A real clinic sets its own passcode and supervisor password in the host's secret settings.

## In short

1. **Never stored:** names, phone numbers, Aadhaar numbers, addresses or prisoner IDs of the people
   seeking help, the story as typed or spoken, and voice recordings.
2. **Stored:** the checked case facts and summary lines (people described by their role), drafts, the
   case's next steps, an audit record of who did what and when, and short problem reports.
3. **Who can see it:** volunteers who know the clinic passcode (all the clinic's cases), and the
   supervisor (with a separate password), who also approves, closes and deletes cases.
4. **Where it goes:** the app runs on Streamlit Community Cloud (United States); records are kept in
   the clinic's Supabase project (Mumbai); the story is read by Google Gemini (with Groq as a backup)
   and recordings are turned into text by Sarvam AI (India), with Gemini as the backup.
5. **How it is deleted:** the supervisor deletes a case on the Supervisor page; a retention period
   (proposed: 1 year after the case is closed) is to be agreed with the supervising lawyer.

Before any real case: agree these rules with the supervising lawyer, use the consent notice below,
and check how India's Digital Personal Data Protection Act, 2023 (DPDP Act) and its rules apply to
the clinic, which would be the "data fiduciary" (the one responsible for the data).

## Never stored
- **Names, phone numbers, Aadhaar numbers, addresses or prisoner IDs** of the people seeking help.
  Phone, Aadhaar and email numbers (in any Indian script) are removed by code from text before it is
  sent anywhere or saved, and the online table itself refuses text that still looks like one.
  Names cannot be removed automatically: volunteers are told not to type them; the app warns when
  the story or a draft seems to contain a common Indian first name or surname; and the volunteer must
  tick "no names" before sending a summary. A name typed despite this could still reach the AI and
  the case record, so this depends on the volunteer.
- **Consumer, account or application numbers** (for example an electricity consumer number): the app
  asks only whether the person has one (yes or no), the AI is told never to write one, and in the
  letter the number stays a [blank]. A number typed into an answer box is not caught by code (only
  phone, Aadhaar and email numbers are), so volunteers must not type them.
- **The story as typed or spoken.** It stays in the open browser session (in the app server's
  memory) only, and is gone when the page is closed or the session ends. Only the checked summary
  lines and facts are kept.
- **Voice recordings.** They are sent only to be turned into text and are never saved by the app.

## What is stored, and where
Volunteers are recorded by the name or initials they type when they sign in; supervisors by the
name or initials they type after the supervisor password.

| What | Local folder (or `kind` in the online table) | Contents |
| --- | --- | --- |
| Case tracker records | `tracker/` | case number and slip code, facts known (with date and volunteer), contradictions and how they were resolved, summary lines, problems in plain words, documents (has / still to get / can't get, with the reason), answers to questions, visit log, camp (village, district, date), who did what, and (if closed) why, when and by whom |
| Drafts waiting for review, or sent back | `pending/` | the draft, the checked facts, the readiness checklist, the evidence ledger, who sent it, who sent it back and why |
| Approved drafts | `drafts/` | the approved draft text |
| Case files | `cases/` | facts known, facts missing, next steps |
| Timelines | `timelines/` | next steps, the handoff (who submitted it, when, how; acknowledgement and reference) |
| Research briefs | `research/` | for problems our files don't cover: the state and the problem in plain words, the official sources found, each point, what the volunteer left out and why, and the supervisor's decision on each point |
| Research saved as knowledge | `knowledge_added/` | a point the supervisor approved and saved for future cases: the state, the point, its official source, and which case it came from (a case number only) |
| Audit records | `audit/` | when, the AI model used, the facts the AI read, what changed and who did it, who sent, approved, sent back, closed, reopened or deleted it |
| Problem reports | `problems/` | short reports with a case number and date; AI failures (time, error type, provider and model, outcome; never case text, recordings or keys) |
| Evaluation sessions | `evaluation/sessions/` | practice evaluation only (fictional cases) |
| Impact log | `impact/` | only for real cases a partner organisation has given permission to log (see docs/CONTENT.md) |
| Practice snapshot | `practice_snapshot/` | Practice Clinic only: a copy of the fictional practice cases, so the supervisor can reset the Practice Clinic; never in a real clinic |
| Keys and passwords | `.env`, `.streamlit/secrets.toml` / host secret settings | Gemini, Groq, Tavily and Sarvam keys, clinic passcode, supervisor password, Supabase secret key; never uploaded to git |

All these folders, `.env` and the secrets file are kept out of git.

**Practice files in this repository.** Everything in the repository is fictional practice material:
the stories in `practice_stories/` and `case_notes*.txt` (each starts "Practice case (not a real
person)"), the evaluation cases in `evaluation/cases/`, the practice cases in `learner/`, and one
early test case kept in `cases/U-20261103-0aea.md` and `drafts/U-20261103-0aea.md` (made-up facts, no
names or personal numbers). Two empty files left from early testing were removed.

## The case slip
The slip given to the person shows only the clinic name, the case number, the code, a QR code,
"Bring this next time" (English and Hindi) and the helplines 112 and 15100. It never shows the case
type, the problem or any legal issue, because someone else may see it (for example in a domestic
violence case). The QR code holds only the app's address and the code; opening it still needs the
clinic passcode.

## Sent outside the clinic's computer

| Service | What it receives | Where it processes data | Kept by the service |
| --- | --- | --- | --- |
| **Streamlit Community Cloud** (hosts the app) | everything the app shows and handles, in memory while a page is open (the story passes through here) | United States (all Community Cloud apps; not configurable) | the app saves nothing there; records go to Supabase |
| **Supabase** (the case records, when set up) | the stored records in the table above | the clinic's project, region Mumbai (India) | until the supervisor deletes them |
| **Google Gemini** (reads the story; research) | the filtered story; facts already known when a case is continued; recordings only if Sarvam fails; for research, the state and the problem in plain words (with Google Search) | Google's facilities, in any country (not only India) | free tier: Google may use what is sent to improve its products, and people may review it; paid tier: not used for that |
| **Groq** (backup, only when both Gemini models fail) | the filtered story and facts already known; for research, the state, the problem in plain words and the official search results (to write and split the brief) | outside India (the company is in the United States) | 30 days by default; "zero data retention" can be switched on in Groq's Data Controls |
| **Tavily** (research backup search) | the state and the problem in plain words (numbers removed), searched on official sites only | outside India (a United States company) | its documentation says "zero data retention" (its full privacy policy was not checked) |
| **Sarvam AI** (speech to text) | voice recordings in English, Hindi or Hinglish, in parts under 30 seconds | India | on the clinic's account: model training turned off, data retention 1 day (the shortest the dashboard allows) |

So the story typed by a volunteer passes through the United States (the app's host) and is read by
Gemini (or Groq), which may process it outside India; saved records are kept in Mumbai. Decide with
the supervising lawyer whether this is acceptable for real cases, and whether to use paid tiers.

What each AI service receives:

| What is sent | Sarvam | Gemini | Groq |
| --- | --- | --- | --- |
| Story / case notes, after the number filter | never | yes | only if both Gemini models fail |
| Facts already known (continuing a case) | never | yes | only if both Gemini models fail |
| Voice recordings | yes (first) | only if Sarvam fails | never |
| "Research from official sources": state and problem in plain words | never | yes (with Google Search) | only to write and split the brief from the official search results, if Gemini is busy |
| Drafts, names, phone or Aadhaar numbers | never | never | never |

- **"Research from official sources"** runs only when the volunteer presses "Run research". Only the
  state and the problem in plain words are sent, never the story; the app refuses to send them if
  they seem to contain a name from the story. Points are kept only with an official source from the
  search results, labelled "AI research, not yet checked by a lawyer" until the supervisor decides.
- Which provider saw a case is recorded: the audit record and each draft's "how this draft was
  prepared" note name the AI model (Groq models start with "groq:"), and the problems log says when a
  backup was used.
- **Bhashini** (MeitY): not used in this prototype or the planned pilot (languages are English, Hindi
  and Hinglish).

## Who can see it
- **Volunteers:** everyone who knows the clinic passcode can see the case tracker (all the clinic's
  cases, facts, visit logs and slips) and add to cases. Change the passcode when a volunteer leaves.
- **Supervisor:** the Supervisor page has its own sign-in with the supervisor password only, then the
  supervisor's name or initials, which is recorded on every approval, edit-and-approve, send-back,
  close, reopen and deletion, and on each research point they approve or reject. A supervisor cannot approve
  a draft they sent or last resent, or decide research points they asked for. The
  supervisor sign-in also opens the volunteer screens for that session.
- **Wrong passwords:** after 5 wrong supervisor passwords (or 5 wrong clinic passcodes) that sign-in is
  locked for 5 minutes (counted per browser and, with a higher limit of 20, per network address).
- **Idle supervisor:** signed out automatically after 30 minutes without activity (shared computers
  at camps).
- **Public:** Home and Learn need no sign-in and show no case data.
- **Files:** with local folders, anyone with access to the computer's files can read them: keep it
  locked. Online, only the app's server (with the secret key) can read the table; row level security
  is on with no public access.

## Closing a case
The supervisor can close an approved case with a reason (resolved, referred elsewhere, person
withdrew, could not contact, other) and a short note without names. A closed case is read-only
(nothing can be added or changed) and shows "Closed"; the supervisor can reopen it with a reason.
Every close and reopen is in the audit record with the supervisor's name and the date.

## For how long
The app does not delete cases on its own; they stay until the supervisor deletes them.
**Proposed default, to be agreed with the supervising lawyer:** delete a case 1 year after it is
closed (the tracker shows the closing date), unless the person or the law requires otherwise.

## How a case is deleted
Supervisor page → "Delete a case": choose the case and type DELETE. This removes the case's tracker
record (facts, visit log, slip code), the draft waiting or sent back, the approved draft, the case
file, the timeline, its research briefs and its problem reports. The audit record keeps only "case
deleted", the date and who deleted it. A point already saved as knowledge stays (it is a general
legal point with its source, and names the case only by number). Copies made outside the app
(printed slips, printouts, emails, files sent to the DLSA) must be deleted separately.

## Consent before any real case
Not built into the app yet: until it is, the volunteer records consent on paper (or in the clinic's
own register), never in the story box. Before a real person's story is entered, the volunteer reads
this out in the person's language and asks if they agree:

> "I will write down your problem to help you get free legal aid. I will not write your name, phone
> number, Aadhaar number or address. What I write is kept by [clinic name] and checked by our lawyer.
> To read it, the app uses computer services, some outside India. You can ask us to show you, correct
> or delete what we keep, at any time. Do you agree?"

> «मैं आपकी समस्या लिखूँगा/लिखूँगी ताकि आपको मुफ़्त क़ानूनी मदद मिल सके। मैं आपका नाम, फ़ोन नंबर, आधार नंबर या
> पता नहीं लिखूँगा/लिखूँगी। जो लिखा जाएगा वह [क्लिनिक का नाम] के पास रहेगा और हमारे वकील उसे जाँचेंगे। इसे पढ़ने के
> लिए ऐप कंप्यूटर सेवाओं का इस्तेमाल करता है, जिनमें से कुछ भारत के बाहर हैं। आप कभी भी कह सकते हैं कि हम जो रखते हैं
> वह आपको दिखाएँ, ठीक करें या मिटा दें। क्या आप सहमत हैं?»
> (Hindi translation checked: no.)

If the person does not agree, do not enter the story: give the helplines (NALSA 15100, and 112 in an
emergency) and help them on paper.

## The person's rights (DPDP Act, 2023)
Under the DPDP Act the person can ask the clinic to:
- **see** what is kept about them and who it was shared with (Section 11);
- **correct, complete or delete** it (Section 12);
- **complain** to the clinic, and then to the Data Protection Board of India (Section 13);
- **nominate** someone to act for them if they die or cannot act (Section 14).

How the clinic does this in the app: find the case from the slip code; show the case file; correct it
with "Edit case" (a closed case is reopened first); delete it with "Delete a case". Check with the
supervising lawyer how the Act and its rules (and their start dates) apply to the clinic.

**Contact for privacy questions and requests:** the clinic's supervising lawyer,
[name of the supervising lawyer], [clinic name and address], [phone or email of the clinic, not of a volunteer].

## What could not be confirmed from the code
- **Sarvam account settings** (training off, retention 1 day): set by the clinic in Sarvam's
  dashboard; the code cannot check them.
- **Supabase region (Mumbai):** chosen when the clinic's project was created; check it in the Supabase
  dashboard.
- **Where Gemini, Groq and Tavily process data, and what they keep:** from each company's published
  terms and documentation (read in November 2026), not from the code. Groq's exact processing
  location and Tavily's full privacy policy were not confirmed; read them before real cases.
- **Whether the Gemini key is on the free or the paid tier:** decided by the Google account's billing,
  not by the code.
- **Streamlit Community Cloud** hosting in the United States: from Streamlit's documentation; what
  Streamlit itself logs about visits is not controlled by the app (the app writes no story or case
  text to its logs).
- **DPDP Act sections and rules:** the section numbers above are from the Act; how the Act and its
  rules apply to the clinic, and from when, is for the supervising lawyer to confirm.
- **Consent:** there is no consent step in the app yet (see above).
