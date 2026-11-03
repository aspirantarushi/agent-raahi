# Legal aid agent — project brief for Claude Code

## Who you are working with
Arushi is building this for the Code for a Billion hackathon (Code for India; submissions close
15 November 2026). She has no coding background. So:
- Work one step at a time. After each change, explain in one or two plain sentences what you did
  and how she can see it working. No jargon without a one-line explanation.
- Before installing anything big, deleting anything, or changing files in knowledge/, templates/
  or learner/, ask first.
- After each step that works, run the tests and tell her the result.

## What we are building
A legal aid agent for India (not a chatbot) used by law students, student volunteers and NGO
caseworkers. A supervisor (for example a clinic lawyer) approves every draft before it is saved
or used. Three modules, built in this order:
1. Undertrial bail: Section 479 BNSS release dates, plus a note to the DLSA or the jail legal aid
   clinic (templates/section479_note.md).
2. Cyber fraud first response: 1930, RBI rules for the bank, complaint and bank letter
   (templates/cyber_complaint.md, templates/bank_letter.md).
3. Free legal aid eligibility check and DLSA application (templates/dlsa_application.md).
Plus a learner mode (learner/) that teaches volunteers with explainers, quizzes and practice cases.

Hackathon rules that shape the build: built inside AgentFoundry; deployed on a cloud; public
GitHub repo with a clear README; open source under the MIT licence; a 2–3 minute demo. Judging:
size of the problem, severity, quality of the solution, proven impact (real use counts most).

## Hard rules (never break these)
- Never predict outcomes, recommend a specific lawyer, or say release is automatic. Under Section
  479 the jail superintendent must apply and the court decides.
- Never store or ask for names, phone numbers, Aadhaar numbers, addresses or prisoner IDs. Case
  numbers (CNR, FIR number) are fine. Only fake practice data in this repo.
- Every draft starts with "DRAFT — to be checked by a lawyer". Name, phone, Aadhaar and address
  blanks stay empty for the person to fill by hand.
- Legal points come only from the files in knowledge/, each with its Source line. If the files
  don't cover something, say so and point to NALSA's free helpline 15100.
- Safety first: if anyone is in danger, show "Call 112 now." For cyber fraud with money lost in
  the last few days and 1930 not yet called, show "Call 1930 now."
- Drafts and case files are saved only after the supervisor clicks Approve.

## How the code should work
- Dates, eligibility and rule checks are plain code, never AI guesses, with tests:
  - Section 479: look up the offence in knowledge/sentence_table.csv (columns offence,
    bns_section, ipc_section, max_prison_months, death_or_life_possible, section_479_applies,
    ask_to_decide, ...). If death or life is possible, Section 479 does not apply. One-half of
    the maximum from the date custody began = bail date; one-third = personal bond date if never
    convicted. More than one case pending: not available. More than one section charged, or an
    ask_to_decide question unanswered: show dates as "to be checked by a lawyer". Delay caused
    by the accused does not count.
  - Cyber fraud: RBI rules differ for transactions up to 31 December 2026 and from 1 January 2027
    (see knowledge/cyber_fraud.md).
  - Eligibility: knowledge/legal_aid_eligibility.md and knowledge/income_limits.csv. Anyone in
    custody, every woman and every child qualifies whatever their income.
- Templates are filled by code: copy the template exactly and replace only [square-bracket]
  blanks. Unknown blanks stay visible.
- AI is used for understanding free-text case notes, asking for missing facts one at a time
  (knowledge/intake_*.md), plain-language explanations, and learner mode. Keep all AI calls in one
  file (llm.py) so the model can be swapped; the AI provider for the cloud version is not decided
  yet. Never put API keys in code: read them from environment variables, and keep .env out of git.
- A source check: every legal statement shown to users must match an entry in knowledge/, and
  its Source line is shown.
- Keep it simple: Python, with a Streamlit web app, unless Arushi agrees to something else.
  Mobile-friendly, large text.

## Folder map
- knowledge/  verified legal content (Markdown entries with Source / Link / Checked lines) and
  sentence_table.csv, income_limits.csv. Do not edit without asking.
- templates/  draft templates with [square-bracket] blanks.
- learner/    learner-mode explainers, quizzes and practice cases.
- lite/       small files for the AgentFoundry Build-tab demo. Leave as they are.
- case_notes.txt  a fake practice case. cases/ and drafts/ hold saved output (never real data).

## Practice case: expected result (use it as a test)
IPC 380 (theft in a dwelling house) = BNS 305, maximum 84 months. Custody began 15 March 2024,
never convicted, one case, today's date 2 November 2026. One-third (28 months) = 15 July 2026,
reached. One-half (42 months) = 15 September 2027, not yet reached. Eligible for free legal aid
(in custody). Draft: the Section 479 note (he already has a legal aid lawyer, so no DLSA
application). Release is not automatic.
