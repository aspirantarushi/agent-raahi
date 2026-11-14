# Online plan: one clinic, one shared case tracker

Practice data only until the steps in "Before real cases" below are done. The live app runs as the
*Agent Raahi Practice Clinic* with fictional stories (see "Try the Practice Clinic" in the README).

Changed on 5 November 2026 (Arushi's decision): the paused multi-organisation plan (organisations,
individual accounts, handovers) is replaced by a simpler setup for **one institution**.
`supabase/schema.sql` and `db.py` from that plan stay in the repository for later but are **not used**.

## How it works now
- **Access.** One clinic passcode for volunteers (`CLINIC_PASSCODE`) and a separate supervisor
  password (`SUPERVISOR_PASSWORD`) for approving, editing and sending back drafts. Both live only in
  `.streamlit/secrets.toml` on this computer and in the host's secret settings online, never in git.
  Volunteers type their name or initials when they sign in; it is saved with every action (facts
  added, visits logged, contradictions resolved, drafts sent). Home and Learn need no passcode.
  The Supervisor menu opens "Supervisor sign-in": the supervisor password, then their name or initials;
  a correct supervisor password also opens the volunteer screens for that session, and signing out as
  supervisor ends that access. If the supervisor password is typed into "Volunteer sign-in", the app
  says "This is the volunteer sign-in. Supervisors: use the Supervisor page."
  After the password the supervisor types their name or initials; it is saved with every approval,
  edit and send-back and on each research point, and a supervisor cannot approve a draft they sent or last
  resent themselves, or decide research points they asked for.
  After 5 wrong passwords (or passcodes) that sign-in is locked for 5 minutes. A supervisor is signed
  out after 30 minutes without activity (shared computers at camps).
- **Audit records.** The Supervisor page lists every case in one table (case code, type, status,
  who sent it and when, who decided and when, AI used, last step), with search, a status filter, a
  date range and "Download as CSV"; clicking a row shows that case's full history.
- **Storage** (`storage.py`). Local folders by default. When `SUPABASE_URL` and
  `SUPABASE_SECRET_KEY` are set, the app saves cases, drafts, timelines, visit logs, audit records,
  research briefs, research saved as knowledge, problem reports, evaluation sessions, the impact log and (in
  the Practice Clinic only) the practice snapshot in one Supabase table, `raahi_records`
  (`supabase/tracker.sql`). Only the app's server uses it, with the secret key. Row level security is
  on with no policies and no rights for the public roles, so nothing can be read from outside the app.
  The table also refuses text that looks like a phone, Aadhaar or email number. Tests always use
  local throw-away folders (`tests/conftest.py`), never Supabase.
- **Case slip.** A case is opened when intake starts and gets a case number and a 6-character code
  (no 0/O or 1/I). The slip shows only the clinic name, the case number, the code, a QR code,
  "Bring this next time / अगली बार यह साथ लाएँ" and the helplines 112 and 15100: never the case type
  or the problem, because someone else may see it. It can be printed or saved as an image for WhatsApp.
- **Continue a case** (Home and New case): type the code, or scan the QR code with a phone camera
  (it opens the app at `APP_URL/?code=...`; the passcode is still needed). The case file shows the
  summary, facts known (with who added them and when), what is still missing, documents, the next
  step, the visit log and the last volunteer.
- **Ask only what's missing.** New notes are merged into the case. Known facts are never asked again.
  A fact that contradicts an earlier one is not saved over it: "Cannot conclude yet" shows both values
  until a volunteer chooses which is right (the choice is saved and audited).
- **Visit log.** Each contact (camp visit, phone call, clinic meeting, jail visit) adds a dated entry:
  who, how, what was learned, what was done, next step and due date.
- **Case tracker** (replaces "My cases"): every case with status, next step and due date, overdue in
  red with the word "Overdue", filters by status, camp and volunteer, and "hide intake not finished".
  Cases opened but never sent show "Intake not finished". A case can be tagged with a camp
  (village, district, date), or every case opened during "Today's camp" is tagged automatically.

## Your steps to go online (one at a time)
1. **Create the table.** Supabase > your project (here: "Code for a Billion") > SQL Editor > New query. Paste
   all of `supabase/tracker.sql`, press Run. Expect "Success. No rows returned".
2. **Copy the secret key.** Supabase > Project Settings > API Keys > Secret keys: copy the key that
   starts with `sb_secret_`. Open `.streamlit/secrets.toml` on your Mac and add these lines
   (do not paste the key in chat):
   ```toml
   SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
   SUPABASE_SECRET_KEY = "sb_secret_..."
   ```
3. **Choose the clinic passcode and name.** Add to the same file:
   ```toml
   CLINIC_PASSCODE = "a passphrase you will tell your volunteers"
   CLINIC_NAME = "Your clinic's name as it should appear on slips"
   ```
4. **Try it locally** with the practice stories (see "Try the Practice Clinic" in the README).
5. **Deploy:** Streamlit Community Cloud, with the same lines in its Secrets settings (every name is listed
   below). The step-by-step clicks are in docs/GO_ONLINE.md.

## Before real cases
Agree with the supervising lawyer how the DPDP Act, 2023 is handled, a retention period, and whether
the Gemini free tier (which lets Google use what is sent) is acceptable.

## Settings (never in git)
Every setting the app reads, names only (values go in `.streamlit/secrets.toml` or the host's secret settings,
never in git; keys can also stay in `.env` on your own computer):

- **Needed:** `CLINIC_PASSCODE`, `SUPERVISOR_PASSWORD`, `CLINIC_NAME`, `APP_URL`, `SUPABASE_URL`,
  `SUPABASE_SECRET_KEY`, `GEMINI_API_KEY`.
- **Backups and speech:** `GROQ_API_KEY` (backup for reading stories), `TAVILY_API_KEY` (backup search for
  research), `SARVAM_API_KEY` (speech to text).
- **Optional:** `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `GROQ_MODEL` (other models), `BHASHINI_USER_ID`,
  `BHASHINI_API_KEY` (more languages, not used in the pilot).
- **Only for tests and local practice copies:** `RAAHI_TEST`, `RAAHI_STORAGE`, `RAAHI_DATA_DIR`,
  `RAAHI_START_SCREEN`, `RAAHI_FORCE_CLOUD`. (`SUPABASE_PUBLISHABLE_KEY` is read only by `db.py`, which is not
  used.)
