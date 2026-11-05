# Going online on Streamlit Community Cloud

This page is for Arushi (or whoever deploys the app). You do the clicks; nothing here deploys by itself.
It never contains a password or key: only the **names** of the settings. The values stay on your Mac
(`.env` and `.streamlit/secrets.toml`) and in the Secrets box online.

## Before you start (check once)

1. **The Supabase table exists.** Supabase > project `legal-aid-agent` > Table Editor: you should see
   `raahi_records`. If not: SQL Editor > New query > paste all of `supabase/tracker.sql` > Run.
2. **The latest code is on GitHub** (`aspirantarushi/agent-raahi`, branch `main`).
3. **Your values are at hand.** Open `.env` and `.streamlit/secrets.toml` on your Mac. You will copy
   the values from there into the Secrets box. Do not paste them into a chat, an email or GitHub.

## The clicks

1. Go to **share.streamlit.io** and sign in with **GitHub** (the account that owns the repository).
2. Top right: **Create app**.
3. Choose **"Deploy a public app from GitHub"** (the first option).
4. Fill in:
   - **Repository:** `aspirantarushi/agent-raahi`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** choose a short address, for example `agent-raahi` (it becomes
     `https://agent-raahi.streamlit.app`). Write it down: it is your `APP_URL` below.
5. Click **Advanced settings**.
   - **Python version:** choose **3.12**. (Your Mac runs 3.9, which is too old for Community Cloud.
     Every package the app needs has a ready-made 3.12 version; this was checked. The Python
     version cannot be changed later without deleting the app and deploying it again.)
   - **Secrets:** paste the block below, with your values in place of `...`.
6. Click **Save**, then **Deploy**. The first start takes a few minutes (it installs the packages).
   You'll see the Home page when it's ready.

## The Secrets box: names and format

One setting per line: the NAME, a space, `=`, a space, then the value **in double quotes**. No spaces
before the name. Lines starting with `#` are notes and are ignored.

```toml
# Needed
SUPERVISOR_PASSWORD = "..."
CLINIC_PASSCODE = "..."
CLINIC_NAME = "..."
SUPABASE_URL = "..."
SUPABASE_SECRET_KEY = "..."
GEMINI_API_KEY = "..."
APP_URL = "..."

# Backups (recommended)
GROQ_API_KEY = "..."
TAVILY_API_KEY = "..."
```

What each one is:

| Name | What to put | Where you have it |
|---|---|---|
| `SUPERVISOR_PASSWORD` | the supervisor's password (approving drafts) | `.streamlit/secrets.toml` |
| `CLINIC_PASSCODE` | the passcode volunteers type to sign in | `.streamlit/secrets.toml` |
| `CLINIC_NAME` | the clinic name printed on case slips | `.streamlit/secrets.toml` |
| `SUPABASE_URL` | the Supabase project address (`https://....supabase.co`) | `.streamlit/secrets.toml` |
| `SUPABASE_SECRET_KEY` | the Supabase **secret** key (starts with `sb_secret_`) | `.streamlit/secrets.toml` |
| `GEMINI_API_KEY` | the Google AI Studio key | `.env` |
| `APP_URL` | the app's address from step 4, e.g. `https://agent-raahi.streamlit.app` | you chose it |
| `GROQ_API_KEY` | the Groq key (backup for reading stories) | `.env` |
| `TAVILY_API_KEY` | the Tavily key (backup search for research) | `.env` |

Optional, only if you want them (leave them out otherwise): `GEMINI_MODEL`,
`GEMINI_FALLBACK_MODEL`, `GROQ_MODEL` (to change the AI models), `BHASHINI_USER_ID` and
`BHASHINI_API_KEY` (other Indian languages, when MeitY gives you the keys).

**Never put these in the Secrets box:** `RAAHI_STORAGE`, `RAAHI_DATA_DIR`, `RAAHI_TEST`,
`RAAHI_START_SCREEN`, `RAAHI_FORCE_CLOUD` (they are for tests and practice copies; `RAAHI_STORAGE`
or `RAAHI_TEST` would stop the app from saving to Supabase). `SUPABASE_PUBLISHABLE_KEY` and
`PRACTICE_PASSWORD` in your `.env` are not needed online.

**To change a secret later:** share.streamlit.io > your app's **⋮** menu > **Settings** > **Secrets**,
edit, **Save**. The app restarts within a minute.

## Check it worked (5 minutes)

1. Open the app address on your phone and on a laptop. Home loads.
2. **No red "Not ready for real cases" notice at the top.** That notice means the Supabase settings
   are missing or mistyped: anything saved would be lost when the app restarts.
3. New case > sign in with the clinic passcode > paste a practice story (from `practice_stories/`) >
   Read the story. If it reads, the Gemini key works.
4. Send it to the supervisor. In Supabase > Table Editor > `raahi_records` you should see new rows.
5. Supervisor > sign in > the practice case is waiting. Reject it with the reason "practice" (or
   delete it in "Delete a case").
6. Print or open a case slip and scan its QR code with a phone camera: it should open the app's
   address (if `APP_URL` is right).

## What behaves differently online

- **Every push to `main` goes live.** The online app updates itself a minute after any change is
  pushed to GitHub. Test on your Mac first.
- **Sleeping.** A free app that nobody opens for a while goes to sleep. The next person sees
  "This app has gone to sleep" and clicks **"Yes, get this app back up!"**; it takes about a minute.
  Open it yourself before a camp or a demo.
- **Speed.** Reading a story or researching takes about as long as on your Mac (the AI does the
  work), but each save goes over the internet to Supabase, so buttons that save can take a second
  longer. The free server is small; a handful of volunteers at once is fine, a big camp with many
  phones at the same moment may feel slow.
- **AI limits are shared.** Everyone uses the same Gemini key, so a busy day reaches the free daily
  limit sooner. The app then tries the backup model and Groq, and says when the AI is busy.
- **Voice ("Speak the story").** Works online: the browser asks once for microphone permission (the
  app is on `https://`, which browsers require). On iPhone use Safari; inside WhatsApp's own browser
  the microphone may be blocked: open the link in Chrome or Safari instead.
- **QR camera ("Continue a case" > Scan).** Works online after the browser asks for camera permission.
  The QR code on slips opens `APP_URL`, so slips printed before `APP_URL` was set won't open the
  app (the 6-character code still works when typed).
- **Who can see it.** "Public app" means anyone with the link sees Home and Learn. New case, Case
  tracker and Supervisor still need the clinic passcode and the supervisor password. (In the app's
  Settings > Sharing you can instead allow only invited email addresses.)
- **Saved data lives in Supabase only.** The online server's own disk is wiped at every restart, so
  nothing is kept there. The practice cases in this repository's folders don't show online.
- **India time.** The server runs on UTC; the app sets its clock to India time, so dates (Section
  479, next steps, the audit record) are the same as on your Mac.
- **Other languages.** Only English, Hindi and Hinglish, as now (Bhashini is not set up).

## Before real cases (not technical)

Agree with the supervising lawyer how the DPDP Act, 2023 is handled, how long records are kept, and
whether the Gemini free tier (Google may use what is sent to improve its products) is acceptable, or
whether to switch to a paid key first.
