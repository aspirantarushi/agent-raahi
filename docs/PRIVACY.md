# Privacy: what this app stores, where, for how long, who can see it, how it is deleted

This describes the app as it runs now: on one computer (or one server), with local folders.
Before real cases, agree these rules with the supervising lawyer, including how India's Digital
Personal Data Protection Act, 2023 applies to your organisation.

## Never stored
- Names, phone numbers, Aadhaar numbers, addresses or prisoner IDs of the people seeking help.
  Phone, Aadhaar and email numbers (in any Indian script) are removed from text before it is sent
  anywhere or saved. Names cannot be removed automatically: volunteers are told not to type them and
  must tick "no names" before sending a summary.
- The pasted or spoken case notes. They stay in the open browser session only and are gone when the
  page is closed. Voice recordings are sent only to be turned into text and are never saved.

## What is stored, and where (folders next to the app)
| What | Folder | Contents |
| --- | --- | --- |
| Drafts waiting for review, or sent back | `pending/` | the draft, the checked facts (dates, sections, yes/no answers), the readiness checklist, the evidence ledger |
| Approved drafts | `drafts/` | the approved draft text |
| Case files | `cases/` | facts known, facts missing, next steps |
| Timelines | `timelines/` | next steps, the handoff (who submitted it, when, how; acknowledgement and reference) |
| Audit records | `audit/` | when, the AI model used, the facts the AI read, what the volunteer changed, who approved or sent it back |
| Problem reports | `problems/` | short reports with a case number and date |
| Evaluation sessions | `evaluation/sessions/` | practice evaluation only (fictional cases) |
| Impact log | `impact/` | only for real cases a partner has given permission for (see the README) |
| Keys | `.env`, `.streamlit/secrets.toml` | Gemini key, supervisor password; never uploaded |

`pending/`, `timelines/`, `audit/`, `problems/`, `evaluation/sessions/`, `impact/`, `.env` and the
secrets file are kept out of git. New files in `drafts/` and `cases/` are kept out of git too (only a
few practice files from early testing are in the repository).

## Sent outside the computer
- **Google Gemini** (the AI): the filtered notes, to read facts; recordings, to turn them into text.
  On Gemini's free tier, Google may use what is sent to improve its products. Decide with the
  supervising lawyer whether this is acceptable for real cases, or use a paid tier.
- **Bhashini** (MeitY): not used in the pilot (languages are frozen at English and Hindi).

## For how long
Until a supervisor deletes the case. The app does not delete cases on its own. Agree a retention
period with the supervising lawyer (for example, delete a set time after the case is acknowledged or
closed) and delete cases when it ends.

## Who can see it
- Anyone using the app on this computer can see "My cases" (drafts, case files, timelines).
- The Supervisor screen (approve, send back, audit records, problem reports, delete) needs the
  supervisor password.
- Anyone with access to the computer's files can read the folders above. Keep the computer locked.
- Individual sign-in and per-organisation separation are planned (see docs/ONLINE_ROLLOUT_STATUS.md);
  until then, use the app only within one organisation.

## How a case is deleted
Supervisor screen -> "Delete a case": choose the case and type DELETE. This removes the case's
pending record, approved draft, case file, timeline and problem reports. The audit record keeps only
"case deleted" and the date. Copies made outside the app (printouts, emails, files sent to the DLSA)
must be deleted separately.
