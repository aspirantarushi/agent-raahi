# Online rollout: where we paused

Paused on 4 November 2026, part-way through Stage 2 (database). The app has **not** been
switched to the database: it still uses local folders (`pending/`, `drafts/`, `cases/`,
`audit/`, `problems/`) and the single supervisor password in `.streamlit/secrets.toml`.

## The plan (agreed)
1. GitHub private repository — **done**
2. Online database (Supabase) with organisation isolation — **in progress**
3. Individual sign-in (email and password) and roles — not started
4. Organisation case tracker and impact page — not started
5. Deploy to Streamlit Community Cloud with one practice organisation — not started

Decisions already made:
- Sign-in by email and password (not email links).
- Roles: volunteer (every member), supervisor, organisation admin, platform admin (Arushi).
- A supervisor can never approve a draft they made themselves or were the last to resend.
- Hosting: Streamlit Community Cloud (the hackathon only needs "built in AgentFoundry,
  deployed on any cloud").
- Before real cases: agree with the supervising lawyer how the DPDP Act, 2023 is handled and
  whether the Gemini free tier (which lets Google use what is sent) is acceptable.

## Done in Stage 2
- Supabase project `legal-aid-agent`, region South Asia (Mumbai). "Automatically expose new
  tables" is switched off.
- `supabase/schema.sql` has been run in the project: 8 tables, row-level security, the case
  actions (submit, send back, resend, approve, mark submitted, set next step, accept
  invitations) and explicit grants to signed-in users only.
- Checked live: an anonymous visitor (public key only) is refused on every table and action.
- Arushi's own account exists and is the platform admin.
- Practice data (fake only): Practice Clinic Alpha (verified), Practice Clinic Beta
  (verified), Practice Clinic Gamma (not verified), and four practice accounts:
  `volunteer.alpha@example.com`, `supervisor1.alpha@example.com`,
  `supervisor2.alpha@example.com` (also organisation admin of Alpha),
  `member.beta@example.com` (supervisor and admin of Beta, member of Gamma).
- `db.py`: all database calls (sign-in, reading, the case actions), plain HTTPS, no extra
  library (the `supabase` Python library does not install on this Mac's Python 3.9).
  Passwords are wrapped so they never appear in error reports. **Not used by the app yet.**
- `tests/test_db_live.py`: 18 live checks of the database's rules, signed in as the practice
  accounts. They run only when asked (see below) and have **not passed yet**.

## Where exactly we stopped
The live checks could not sign in: the practice password in `.env` did not match the one set
in Supabase. While debugging, the old practice password appeared in an error report (fixed in
`db.py` since), so it must be replaced anyway.

## To resume (in this order)
1. Give the four practice accounts a **new** practice password. In Supabase > SQL Editor:
   ```sql
   update auth.users
   set encrypted_password = extensions.crypt('NEW-PRACTICE-PASSWORD', extensions.gen_salt('bf')),
       updated_at = now()
   where email in ('volunteer.alpha@example.com', 'supervisor1.alpha@example.com',
                   'supervisor2.alpha@example.com', 'member.beta@example.com')
   returning email;
   ```
   Expect 4 rows. Then delete that saved query in the SQL Editor, and put the same new password
   in `.env` as `PRACTICE_PASSWORD=...` (plain text).
2. Run the live checks and fix anything they find:
   `LIVE_DB_TESTS=1 .venv/bin/python -m pytest tests/test_db_live.py`
3. Move saving from local folders to the database behind one switch, keeping the local
   version for the offline tests: cases, drafts, case files, audit records, problem reports.
4. Stage 3: sign-in screen, accept invitations, organisation admin screen (invite members,
   choose supervisors), platform admin screen (create and verify organisations); remove the
   shared supervisor password.
5. Stage 4: case tracker (status, volunteer, supervisor, next step and due date, overdue
   highlighted, filters) and impact counts; "mark as submitted" step.
6. Stage 5: deploy to Streamlit Community Cloud; secrets in its settings; practice
   organisation only.

## Settings in `.env` (never in git)
`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `PRACTICE_PASSWORD`.
The Supabase secret / service-role key is never used.
