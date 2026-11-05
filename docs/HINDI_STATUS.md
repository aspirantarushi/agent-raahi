# Hindi and voice: status and files to check

All seven parts of the Hindi and voice request are built and tested (5 November 2026).

## How it works
- Language switch "Language / भाषा" at the top of every screen. All screen text, the safety
  messages (112, 1930, 15100), the Section 479 reasons, draft phrases and the AI disclosure come
  from `i18n/en.json` and `i18n/hi.json`. To add a language, copy `en.json` (for example to
  `bn.json`), translate the values and add it to `LANGUAGES` in `lang.py`. Missing keys fall back
  to English.
- Hindi legal content: `knowledge_hi/` and `templates_hi/`, each marked
  "Hindi translation checked: no". The label is shown next to Hindi legal text (summaries) and at
  the top of Hindi drafts until the file says "yes". Source and Link lines stay in English. A test
  checks that every section number, date and amount matches the English file.
- Notes in Hindi, Hinglish or mixed are read by the AI and checked by plain code (Hindi and
  Hinglish month names, आईपीसी / बीएनएस, Hindi state names, amounts like "10 हज़ार").
- Privacy: Devanagari digits and numbers split by spaces are removed before anything reaches the AI.
- Voice: "Speak the story" records in the browser; the recording goes to Gemini only to become
  text (Devanagari on the Hindi screen, as spoken on the English screen) and is never saved; the
  text goes through the privacy filter into the notes box for the volunteer to correct.
- Drafts: the volunteer chooses the draft language. A Hindi draft keeps "DRAFT — to be checked by
  a lawyer" as its first line, then the Hindi line and the translation label.

## Review sheet (start here)
**`docs/hindi_review.csv`** lists every Hindi line not yet marked checked, one per row, with the English
next to it: Where (file and key), English, Hindi now, Type (legal content / draft / screen text /
practice story), Checked (blank), Suggested fix (blank). Legal content and drafts come first. It opens
in Excel or Google Sheets. It includes the Home facts, the Learn cards, buttons, research, the
complaint letter, the checklist and the step 3 cards. After fixes are made in the files, rebuild it:

    .venv/bin/python scripts/hindi_review.py

Fixes already applied from a review are noted in the "Suggested fix" column (for example the 1930
lines, 5 November 2026: "ताकि पैसे धोखेबाज़ों के हाथ लगने से पहले ही रोके जा सकें").

## Hindi files a Hindi speaker who knows the law should check
When an entry or template is checked, change "Hindi translation checked: no" to "yes" in it.
1. `knowledge_hi/undertrial_bail.md` — 3 entries: rights on arrest; free legal aid from the first
   court appearance; who to approach for an undertrial
2. `knowledge_hi/cyber_fraud.md` — 3 entries: call 1930 at once; stop further loss; evidence to keep
3. `knowledge_hi/legal_aid_eligibility.md` — 1 entry: what to carry
4. `templates_hi/section479_note.md` — the Section 479 note (marker on line 1)
5. `templates_hi/dlsa_application.md` — the DLSA application (marker on line 1)
5a. `templates_hi/complaint_letter.md` — the complaint letter made in step 3 (marker on line 1)
5b. `home.py` — the Hindi Home facts (the facts carousel)
6. `i18n/hi.json` — all screen text, and the legal wording used in drafts and summaries: the keys
   starting `s479.` (Section 479 reasons), `draft.` and `sec.` (draft phrases), `disclosure.`
   (AI disclosure), `elig.` and `group.` (free legal aid), `next:` (next steps), `doc:` (documents)
   and `intake.q.` (intake questions)
7. The name and tagline in `i18n/hi.json`: "एजेंट राही" and "क़ानूनी मदद तक, रोशन राह"
   (key `meta.hi_checked.app.tagline` is "no" until checked; change it to "yes")
8. `case_notes_hi.txt` and `practice_stories/upi_fraud_hinglish.txt` — fake practice stories (only
   check that they read naturally)

## Known limits
- The follow-up question from the sentence table ("ask_to_decide") and the offence names come from
  `knowledge/sentence_table.csv` and stay in English in Hindi drafts.
- Name spotting relies on capital letters, which Devanagari doesn't have; for Hindi notes the
  "no names" tick box is the safeguard.
- Case files, audit records and the supervisor's audit view stay in English.
- Steps in a general summary's timeline are saved in English and shown in Hindi where hi.json has them.
