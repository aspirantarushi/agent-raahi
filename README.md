# Legal aid agent: content files

Version 1 content for the legal aid agent (Code for a Billion, Timely Justice track). Researched on 2 November 2026. Nothing here has been checked by a lawyer yet: every entry says "Lawyer checked: no" until it is.

## What's here

| File | What it holds |
| --- | --- |
| knowledge/legal_aid_eligibility.md | Who qualifies for free legal aid, where and how to apply, timelines, appeals |
| knowledge/income_limits.csv | Income limit for free legal aid in each state and UT |
| knowledge/undertrial_bail.md | Rights on arrest, bail, default bail, Section 479 BNSS, who to approach |
| knowledge/sentence_table.csv | 48 offence rows: BNS and IPC sections, maximum prison term in months, whether death or life is possible, whether Section 479 can apply, and the follow-up question that decides the right row |
| knowledge/cyber_fraud.md | 1930, bank reporting, RBI liability rules, evidence, digital-arrest scams |
| knowledge/helplines.md | Verified helpline numbers and when to use which |
| knowledge/intake_cyber_fraud.md | Questions the agent asks, in order, for a fraud case |
| knowledge/intake_undertrial.md | Questions the agent asks, in order, for an undertrial case |
| templates/dlsa_application.md | Legal aid application (based on NALSA Form I) |
| templates/section479_note.md | Request to the DLSA or jail legal aid clinic to move a Section 479 application |
| templates/cyber_complaint.md | Complaint summary for cybercrime.gov.in or the police |
| templates/bank_letter.md | Letter to the bank under the RBI customer liability rules (current rules, plus wording for transactions from 1 January 2027) |
| learner/legal_aid.md, learner/undertrial_bail.md, learner/cyber_fraud.md | Explainer, 10-question quiz and 2 practice cases per module |
| learner/case_law.md | 12 landmark judgments with one-line summaries |

## What this tool will never do
- It never predicts the outcome of a case, the chances of bail, flight risk, the risk of
  re-offending, or anyone's guilt or credibility, and it never scores or ranks people.
- The Section 479 dates are statutory deadlines worked out by plain, tested code from the
  statute and knowledge/sentence_table.csv. They are not an assessment of whether bail should
  be granted: the jail superintendent must apply and the court decides.
- AI is used only to extract facts stated in case notes. A volunteer checks every fact, and
  the AI is told never to judge bail chances, risk, guilt or credibility.
- Every draft ends with a note on how it was prepared (AI model used, if any; rule-based
  dates; supervisor approval date), and every case has an audit record. This follows the
  Supreme Court's draft "Regulations for Use of AI in Courts, 2026" (Regulations 16, 20(d),
  20(f) and 43), because drafts may later be filed in court.

## Language support
- **English and Hindi** are the checked languages. Their screen text is in `i18n/en.json` and
  `i18n/hi.json` (everyday Hindi). Hindi legal text is in `knowledge_hi/` and `templates_hi/`, marked
  "Hindi translation checked: no" until a Hindi speaker who knows the law has checked it.
- **The other 21 scheduled languages** use Bhashini (MeitY). `scripts/translate_ui.py` translates
  the screen text once into `i18n/<code>.json`, marked "machine translated by Bhashini, not checked".
  {placeholders}, numbers, 112, 1930, 15100 and web addresses are never sent for translation, so they
  stay exact (a test checks every file). The language switch lists each language in its own script.
- **Notes** in Hindi, Hinglish or English are read by the AI directly. Notes in another scheduled
  language are translated to English by Bhashini first; the volunteer checks every fact against the
  original. **Voice**: Bhashini speech-to-text where it supports the language, otherwise Gemini.
- **Privacy first**: phone, Aadhaar and email numbers are removed BEFORE any text reaches Bhashini or
  Gemini, in every script (Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada,
  Malayalam, Ol Chiki, Meetei Mayek, Arabic-Indic and others). Recordings are never saved.
- **Legal text** in languages other than English and Hindi is only a *reading copy*, labelled
  "Machine translated, not checked. Rely on the English or Hindi version." Section numbers, dates
  and amounts must come back exactly as in English, or that part stays in English. **Drafts for the
  DLSA or a court are made only in English or Hindi.**
- **If Bhashini is not set up or not reachable**, the app works in English and Hindi and says so.
- Bhashini access: register at https://dashboard.bhashini.co.in/user/register; after approval, the
  user ID and API key are under "My Profile". Put them in `.env` as `BHASHINI_USER_ID` and
  `BHASHINI_API_KEY` (never in git). Bhashini's docs say the free APIs are for proof-of-concept use;
  production use needs their paid plan.

## Before launch: checks for the reviewing lawyer
1. sentence_table.csv: every maximum term, especially rows with an "ask_to_decide" question, and the status of BNS 106(2).
2. undertrial_bail.md: the Section 479 rules and the worked example, and especially how Section 479(2) ("more than one offence") should be applied when one case charges several sections.
3. cyber_fraud.md: the RBI liability entries, including the switch to the new rules for transactions from 1 January 2027, and the 2026 Ombudsman scheme.
4. case_law.md: each summary, plus official citations.
5. income_limits.csv: the NALSA table is undated; confirm limits for the states you pilot in. Flagged rows: Mizoram, Dadra and Nagar Haveli, Daman and Diu, Lakshadweep, Delhi.

## Known gaps
- Special laws (NDPS Act, Arms Act, state prohibition and excise laws) are not in the sentence table.
- Some states have amended the BNSS for their own territory (for example Maharashtra in 2026, on remand and preliminary enquiries). None found so far touch the bail or Section 479 provisions, but check for the states you pilot in.
- The RBI cyber-fraud rules change on 1 January 2027. The agent must ask the transaction date and apply the right set of rules; remove the old rules from the knowledge files once no open cases depend on them.
- Hindi versions still to be written and checked by a Hindi speaker.
- Several entries cite reliable secondary summaries (iPleaders, LawSikho, Legacy IAS, Vidhi Judicial) of the statute; before launch, replace these with India Code links to the bare acts where possible.

## Main sources
- Legal Services Authorities Act, 1987 (Supreme Court Legal Services Committee): https://sclsc.gov.in/legal-services/Entitlement
- NALSA (Free and Competent Legal Services) Regulations, 2010, current text as amended in 2012, 2018 and 2019: https://www.casemine.com/act/in/5f5f117e9fca195c05cce4a9
- NALSA state income limits: https://nalsa.gov.in/services/legal-aid/eligibility
- Bihar SLSA eligibility: https://patnahighcourt.gov.in/BSLSA/Eligibility.aspx
- Section 479 BNSS explained: https://blog.ipleaders.in/maximum-detention-of-an-undertrial-and-release-section-479-bnss/
- Bail under BNSS: https://www.legacyias.com/bail-under-bnss-2023/
- Rights of arrested persons under BNSS: https://lawsikho.com/blog/?p=6885
- BNS section texts: https://www.vidhijudicial.com (one page per section, linked in sentence_table.csv)
- BNS–IPC comparison: https://www.keralaprisons.gov.in/userfiles/act-and-rules/comparison_summary_BNS_to_IPC.pdf
- RBI (Commercial Banks – Responsible Business Conduct) Directions, 2025, which carry forward the 6 July 2017 customer liability circular (rules for transactions up to 31 December 2026): https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=13140
- RBI Responsible Business Conduct Third Amendment Directions, 2026 (rules from 1 January 2027): https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543
- RBI Integrated Ombudsman Scheme, 2026 FAQs: https://www.rbi.org.in/commonman/Upload/English/FAQs/PDFs/RBIOS01072026.pdf
- Legal aid beneficiaries: Lok Sabha Unstarred Question 4327, 20 December 2024: https://eparlib.sansad.in/bitstream/123456789/2987363/1/AU4327_ycIKN1.pdf
- I4C digital-arrest advisory: https://www.deccanherald.com/india/amid-rise-in-digital-arrest-cases-indian-cyber-crime-coordination-centre-issues-advisory-for-citizens-3221509
- Government helpline directory: https://india.gov.in/directory/helpline
