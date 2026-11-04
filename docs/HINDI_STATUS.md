# Hindi and voice: where we paused (4 November 2026)

Done:
- Privacy: Devanagari digits (०-९) and spaced-out numbers are caught (privacy.py), with tests.
- knowledge_hi/: Hindi versions of the 7 knowledge entries the app shows (each "Hindi translation
  checked: no"); knowledge.get(..., lang="hi") falls back to English when missing.
- templates_hi/: Hindi Section 479 note and DLSA application (marker on line 1).
- tests/test_hindi_files.py: numbers, Source/Link/Checked lines and markers match the English.
- lang.py: reads i18n/<language>.json (the i18n files are not written yet; lang.py is not used yet).

Still to do (in order):
1. i18n/en.json (today's English wording exactly) and i18n/hi.json; language switch on every screen.
2. Section 479 reasons, draft phrases and the AI disclosure through lang.py; Hindi drafts from
   templates_hi/ with the "translation checked: no" label; draft-language choice.
3. General summary labels and next steps in Hindi.
4. AI reading of Hindi / Hinglish notes (prompt, Hindi month and state names, आईपीसी/बीएनएस).
5. Voice input with st.audio_input (Gemini transcription, recording never saved).
6. Tests incl. a Hindi practice case; then the list of Hindi files to check.
The app itself is unchanged and English-only until step 1.
