# Intake checklist: undertrial and bail

Ask one question at a time, in this order. Never record the person's name, father's name, address, phone number or prisoner ID in the app. Case numbers (CNR) are fine.

## The case
1. Is the person currently in jail or police custody? [Jail / Police custody / Out on bail / Not yet arrested]
   - Not yet arrested and fears arrest: explain notice of appearance (BNSS 35(3)) and anticipatory bail (BNSS 482); suggest a lawyer.
2. On what date did custody begin (the date of arrest)? [date]
3. On what date was the offence said to have happened? [date]
   - Before 1 July 2024: IPC sections apply. On or after: BNS sections.
4. Which sections are written on the FIR or chargesheet? [list, e.g. "BNS 305" or "IPC 380"]
   - If unknown: ask them to get the FIR copy or check eCourts with the CNR number.
5. Has a chargesheet been filed yet? [Yes, date: ___ / No / Don't know]
   - If no and 60 or 90 days have passed: flag default bail (BNSS 187(3)) for the lawyer.
6. Which court is the case in, and is there a CNR number? [court, CNR]
7. Has bail been applied for? [Not applied / Applied and refused / Granted but still in jail / Don't know]
   - Granted but still in jail: go to the "bail granted but still in jail" entry in undertrial_bail.md.

## Section 479 questions
8. Has the person ever been convicted of any offence before? [Never / Yes / Not sure]
9. Are any other cases pending against them? [No / Yes / Not sure]
   - Also check question 4: if more than one section is charged in this case, Section 479(2) may bar release. Flag for a lawyer; don't present the dates as settled.
10. For each section, the follow-up question in sentence_table.csv's "ask_to_decide" column (for example: was anyone hurt? was it at night?).
11. Has the case been delayed because of the accused (for example, their own adjournment requests)? [No / Yes / Not sure]
    - Delay caused by the accused doesn't count toward the Section 479 period.

## Lawyer and legal aid
12. Does the person have a lawyer? [Private lawyer / Legal aid lawyer / None / Don't know]
13. Has anyone contacted the jail's legal aid clinic or the District Legal Services Authority? [Yes / No]
14. Do any of these apply: woman, child, SC/ST, person with disability? [list]
    - A person in custody qualifies for free legal aid anyway (Legal Services Authorities Act, Section 12(g)).

## Facts needed before drafts
- For the Section 479 note to the legal aid clinic: items 2, 4, 8, 9, 10, 11 and the calculator result
- For a legal aid application: items 6, 12, 14 and a short statement of the case
