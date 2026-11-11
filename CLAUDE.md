# Agent Raahi (legal aid agent) — project brief for Claude Code

Name: Agent Raahi (Hindi: एजेंट राही). Tagline: "Lighting the way to legal aid" (Hindi: "क़ानूनी मदद तक,
रोशन राह", Hindi translation checked: no). Description: "An AI casework agent for legal aid clinics and NGOs".
The name, tagline and logo (assets/brand/: raahi-mark.svg, raahi-mark-on-dark.svg, favicon.svg, raahi-app-icon.svg) come from i18n/en.json, i18n/hi.json and ui.py.

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
- Legal points come only from the files in knowledge/, each with its Source line, or from AI
  research from official sources (research.py): shown to the volunteer and used in a draft only
  with the label "AI research, not yet checked by a lawyer", and final only once the supervisor
  approves it. If neither covers something, say so and point to NALSA's free helpline 15100.
- Research: only the state and the issue in plain words are sent (never names or personal numbers).
  Every point needs an official source (gov.in, nic.in, India Code, state regulators, courts, NALSA,
  legal services authorities) that came from the actual search results; plain code checks this and
  drops points without one, and points that predict outcomes. Replaced laws, a source that names a
  different law, and a source from another state's website are flagged.
- Nothing that produces a result happens by itself: the volunteer presses a button (Read the story,
  Turn speech into text, Calculate the dates, Run research, Draft the letter, Make the drafts); the
  notes' language is only suggested and the volunteer confirms it; the supervisor rebuilds the letter
  from the approved points with a button.
- The flow for problems not in knowledge/: story read → questions → the volunteer presses "Run
  research" (state chosen first) → the points are shown to the volunteer, each with its source link,
  the warnings and the label "AI research, not yet checked by a lawyer" → the volunteer may untick
  points they think are wrong (with a short reason); they can never add or edit a legal point →
  "Draft the letter" drafts it from the ticked points and the facts of the case (no
  legal claim beyond the ticked points) → "Send to supervisor" sends the summary, the letter, the
  DLSA application, every research point, and which points the volunteer left out and why → the
  supervisor approves, edits or rejects each point; the letter is then rebuilt from the approved
  points only (or taken out if all are rejected), and the supervisor approves, edits or rejects
  the drafts. Only approved points reach the case record and the knowledge base. Every step is in
  the audit record.
- When a problem falls under a law that was replaced (for example unpaid wages → Code on Wages, 2019;
  arrest or bail → BNSS/BNS), the search names the current law (replaced_laws.search_text), so
  official pages under it come first. If no research point is ticked (or research fails, or the
  supervisor rejects every point), a facts-only request letter is drafted to the right type of
  office, using only the facts of the case and what the person wants (no sections, Acts or
  deadlines), labelled "Facts-only letter: no legal points yet; the supervisor may add them."
- Safety first: if anyone is in danger, show "Call 112 now." For cyber fraud with money lost in
  the last few days and 1930 not yet called, show "Call 1930 now."
- Drafts and case files are saved only after the supervisor clicks Approve.

## What this tool will never do
- It never predicts the outcome of a case, the chances of bail, flight risk, the risk of
  re-offending, or anyone's guilt or credibility, and it never scores or ranks people.
- The Section 479 calculator is an aid for the reviewing lawyer, not a release decision. Its
  dates are worked out by plain, tested code from the statute and knowledge/sentence_table.csv;
  they are not an assessment of whether bail should be granted: the jail superintendent must
  apply and the court decides. It is a secondary option; "Any case" is where volunteers start.
- AI is used only to extract facts stated in case notes. A volunteer checks every fact, and
  the AI is told never to judge bail chances, risk, guilt or credibility.
- Every draft ends with a note on how it was prepared (AI model used, if any; rule-based
  dates; supervisor approval date), and every case has an audit record. This follows the
  Supreme Court's draft "Regulations for Use of AI in Courts, 2026" (Regulations 16, 20(d),
  20(f) and 43), because drafts may later be filed in court.

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
  (knowledge/intake_*.md), plain-language explanations, learner mode, and "Research this issue"
  (Gemini with Google Search grounding, for issues knowledge/ doesn't cover). Keep all AI calls in one
  file (llm.py) so the model can be swapped; the AI provider for the cloud version is not decided
  yet. Never put API keys in code: read them from environment variables, and keep .env out of git.
- A source check: every legal statement shown to users must match an entry in knowledge/ or a
  research point from official sources, and its Source line is shown; a research point the
  supervisor has not approved yet is always labelled "AI research, not yet checked by a lawyer".
- Keep it simple: Python, with a Streamlit web app, unless Arushi agrees to something else.
  Mobile-friendly, large text.

## Folder map
- knowledge/  verified legal content (Markdown entries with Source / Link / Checked lines) and
  sentence_table.csv, income_limits.csv. Do not edit without asking. Approved research saved as
  knowledge lives in the shared database (record kind "knowledge_added"), not in these files; the
  supervisor can export it as Markdown to add to knowledge/ by hand after a check.
- templates/  draft templates with [square-bracket] blanks (complaint_letter.md: step 3 letters, filled
  only with facts of the case and research points: the volunteer's ticked points, labelled as not yet
  checked, until the supervisor decides, then only the approved ones; Hindi in templates_hi/).
- learner/    learner-mode explainers, quizzes and practice cases.
- lite/       small files for the AgentFoundry Build-tab demo. Leave as they are.
- case_notes.txt  a fake practice case. cases/ and drafts/ hold saved output (never real data).

## Practice case: expected result (use it as a test)
IPC 380 (theft in a dwelling house) = BNS 305, maximum 84 months. Custody began 15 March 2024,
never convicted, one case, today's date 2 November 2026. One-third (28 months) = 15 July 2026,
reached. One-half (42 months) = 15 September 2027, not yet reached. Eligible for free legal aid
(in custody). Draft: the Section 479 note (he already has a legal aid lawyer, so no DLSA
application). Release is not automatic.
