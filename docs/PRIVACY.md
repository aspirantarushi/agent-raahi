# Privacy: what this app stores, where, for how long, who can see it, how it is deleted

This describes the app for one clinic: on one computer with local folders, or online with the
clinic's Supabase table (see docs/ONLINE_ROLLOUT_STATUS.md). Before real cases, agree these rules
with the supervising lawyer, including how India's Digital Personal Data Protection Act, 2023
applies to your organisation.

## Never stored
- Names, phone numbers, Aadhaar numbers, addresses or prisoner IDs of the people seeking help.
  Phone, Aadhaar and email numbers (in any Indian script) are removed from text before it is sent
  anywhere or saved, and the online table refuses text that still looks like one. Names cannot be
  removed automatically: volunteers are told not to type them and must tick "no names" before
  sending a summary.
- The pasted or spoken case notes. They stay in the open browser session only and are gone when the
  page is closed. Voice recordings are sent only to be turned into text and are never saved. From the
  notes, only the checked summary lines and facts are kept.

## What is stored, and where
Volunteers are recorded by the name or initials they type when they sign in.

| What | Local folder (or `kind` in the online table) | Contents |
| --- | --- | --- |
| Case tracker records | `tracker/` | case number and slip code, facts known (with date and volunteer), contradictions and how they were resolved, summary lines, problems in plain words, documents held, answers to questions, visit log, camp (village, district, date), who did what |
| Drafts waiting for review, or sent back | `pending/` | the draft, the checked facts, the readiness checklist, the evidence ledger, who sent it |
| Approved drafts | `drafts/` | the approved draft text |
| Case files | `cases/` | facts known, facts missing, next steps |
| Timelines | `timelines/` | next steps, the handoff (who submitted it, when, how; acknowledgement and reference) |
| Audit records | `audit/` | when, the AI model used, the facts the AI read, what changed and who did it, who approved or sent it back |
| Problem reports | `problems/` | short reports with a case number and date |
| Evaluation sessions | `evaluation/sessions/` | practice evaluation only (fictional cases) |
| Impact log | `impact/` | only for real cases a partner has given permission for (see the README) |
| Keys and passwords | `.env`, `.streamlit/secrets.toml` / host secret settings | Gemini key, clinic passcode, supervisor password, Supabase secret key; never uploaded to git |

All these folders, `.env` and the secrets file are kept out of git (a few practice files from early
testing are in the repository).

## The case slip
The slip given to the person shows only the clinic name, the case number, the code, a QR code,
"Bring this next time" (English and Hindi) and the helplines 112 and 15100. It never shows the case
type, the problem or any legal issue, because someone else may see it (for example in a domestic
violence case). The QR code holds only the app's address and the code; opening it still needs the
clinic passcode.

## Sent outside the computer
- **Supabase** (when set up): the records above, in the clinic's own project (region Mumbai), used
  only by the app's server with the secret key. Row level security is on with no public access.
- **Google Gemini** (the AI): the filtered notes, to read facts (and, when continuing a case, the facts
  already known, so it does not ask for them again); recordings, to turn them into text. On Gemini's
  free tier, Google may use what is sent to improve its products. Decide with the supervising lawyer
  whether this is acceptable for real cases, or use a paid tier.
- **Bhashini** (MeitY): not used in the pilot (languages are frozen at English and Hindi).

## For how long
Until a supervisor deletes the case. The app does not delete cases on its own. Agree a retention
period with the supervising lawyer (for example, delete a set time after the case is acknowledged or
closed) and delete cases when it ends.

## Who can see it
- Everyone with the clinic passcode can see the case tracker (all the clinic's cases, facts, visit
  logs and slips) and add to cases. Change the passcode when a volunteer leaves.
- The Supervisor screen (approve, edit, send back, audit records, problem reports, delete) also needs
  the supervisor password.
- Home and Learn are public: they show no case data.
- With local folders, anyone with access to the computer's files can read them: keep it locked.
  Online, only the app's server can read the table.

## How a case is deleted
Supervisor screen -> "Delete a case": choose the case and type DELETE. This removes the case's
tracker record (facts, visit log, slip code), pending record, approved draft, case file, timeline and
problem reports. The audit record keeps only "case deleted" and the date. Copies made outside the app
(printed slips, printouts, emails, files sent to the DLSA) must be deleted separately.
