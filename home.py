"""Home page facts: plain-English (and Hindi) cards, each based on exact sentences in knowledge/.

Each fact names a knowledge entry and the sentences in it that the card is based on, word for word.
If an entry changes and one of those sentences no longer appears, an error is raised (and a test
fails) instead of showing a legal point that is not in our verified files. knowledge/ is never
edited from here. No pilot figures until they are measured.
"""

from typing import List, Tuple

import knowledge

# (file, heading, [sentences in the entry the card is based on], plain English, plain Hindi)
FACTS = [
    ("legal_aid_eligibility.md", "Who qualifies for free legal aid",
     ["A person who has to file or defend a case gets free legal services if they belong to any one of these groups:",
      "a member of a Scheduled Caste or Scheduled Tribe", "a victim of human trafficking or begar (forced labour)",
      "a woman or a child (anyone under 18)", "a person with a disability", "an industrial workman",
      "a victim of a mass disaster", "a person in custody",
      "Women, children and people in custody qualify whatever their income."],
     "Free legal aid does not depend on income for women, children, people in custody, SC/ST members, people "
     "with disabilities, industrial workers, and victims of trafficking or disasters, if they have a case to "
     "file or defend.",
     "महिलाओं, बच्चों, हिरासत में बंद लोगों, SC/ST समुदाय के लोगों, दिव्यांगों, औद्योगिक मज़दूरों और तस्करी या आपदा "
     "के पीड़ितों को मुफ़्त क़ानूनी मदद मिलती है, चाहे उनकी आमदनी कितनी भी हो, अगर उन्हें कोई केस करना या लड़ना है।"),
    ("legal_aid_eligibility.md", "How long a decision takes",
     ["A decision must be taken immediately, and within seven days of receiving the application at most."],
     "Once a legal aid application is received, the legal services authority must decide it straight away, and "
     "within seven days at most.",
     "मुफ़्त क़ानूनी मदद की अर्ज़ी मिलने के बाद विधिक सेवा प्राधिकरण को उस पर तुरंत फ़ैसला करना होता है, और ज़्यादा से "
     "ज़्यादा सात दिन के अंदर।"),
    ("undertrial_bail.md", "Section 479: release after a share of the maximum sentence",
     ["No undertrial can be held beyond the full maximum term."],
     "Under Section 479 BNSS, no undertrial prisoner can be held in jail beyond the maximum prison term for the "
     "offence. This does not cover offences that can be punished with death or life imprisonment.",
     "धारा 479 BNSS के तहत किसी भी विचाराधीन क़ैदी को अपराध की अधिकतम सज़ा से ज़्यादा समय जेल में नहीं रखा जा सकता। "
     "यह उन अपराधों पर लागू नहीं होता जिनमें मौत या उम्रक़ैद की सज़ा हो सकती है।"),
    ("undertrial_bail.md", "When Section 479 does not apply",
     ["The offence can be punished with death or life imprisonment."], None, None),  # the exception above
    ("cyber_fraud.md", "Call 1930 at once: the first hours matter most",
     ["call the national cyber-fraud helpline 1930 immediately",
      "Report as early as possible, ideally within a few hours: the faster the report, the better the chance the "
      "money can be stopped before the fraudster withdraws it."],
     "Lost money online? Call 1930 straight away, ideally within the first few hours. The sooner it is reported, "
     "the better the chance of stopping the money before the fraudster withdraws it.",
     "ऑनलाइन पैसे गए? तुरंत 1930 पर कॉल करें, हो सके तो पहले कुछ घंटों में। जितनी जल्दी शिकायत होगी, धोखेबाज़ के पैसे "
     "निकालने से पहले उन्हें रोकने का मौक़ा उतना ज़्यादा होगा।"),
    ("legal_aid_eligibility.md", "The legal aid lawyer cannot charge any fee",
     ["A panel lawyer assigned through legal aid must not take any fee or anything of value from the person."],
     "A legal aid lawyer must not take any fee, or anything of value, from the person they are helping.",
     "लीगल एड वकील जिसकी मदद कर रहे हैं, उससे कोई फ़ीस या कोई भी क़ीमती चीज़ नहीं ले सकते।"),
    ("undertrial_bail.md", "Free legal aid starts at the first court appearance",
     ["An accused person who cannot afford a lawyer is entitled to free legal aid from the moment they are first "
      "produced before a magistrate, and the magistrate must tell them about this right.",
      "They do not need to have asked for it."],
     "Someone who is arrested and cannot afford a lawyer has the right to free legal aid from their first "
     "appearance before a magistrate, even if they have not asked for it.",
     "गिरफ़्तार व्यक्ति अगर वकील का ख़र्च नहीं उठा सकता, तो उसे मजिस्ट्रेट के सामने पहली पेशी से ही मुफ़्त क़ानूनी मदद का "
     "हक़ है, चाहे उसने माँगी न हो।"),
    ("legal_aid_eligibility.md", "A self-declaration is usually enough proof",
     ["the person's own affidavit (sworn statement) can be accepted unless the authority has a reason to disbelieve it.",
      "No income certificate is required by law."],
     "No income certificate is needed for free legal aid: the person's own sworn statement (affidavit) of income "
     "is usually accepted.",
     "मुफ़्त क़ानूनी मदद के लिए आय प्रमाण-पत्र ज़रूरी नहीं है: आमदनी के बारे में व्यक्ति का अपना शपथ-पत्र (हलफ़नामा) "
     "आम तौर पर मान लिया जाता है।"),
    ("cyber_fraud.md", "\"Digital arrest\" calls are always fraud",
     ["No police, CBI, ED, customs officer or judge arrests anyone over a video call or asks for money to avoid "
      "arrest.", "Hang up, don't pay, and report to 1930 or cybercrime.gov.in."],
     "No police officer, CBI, ED or judge arrests anyone over a video call or asks for money to avoid arrest. "
     "If someone does, hang up, don't pay, and call 1930.",
     "पुलिस, CBI, ED या कोई जज वीडियो कॉल पर किसी को गिरफ़्तार नहीं करते, न गिरफ़्तारी से बचाने के लिए पैसे माँगते हैं। "
     "ऐसा कॉल आए तो फ़ोन काटें, पैसे न दें, और 1930 पर कॉल करें।"),
]

HINDI_CHECKED = False  # the Hindi cards have not been checked by a fluent reviewer yet


def check_sources() -> None:
    """Every sentence a card is based on must still be in knowledge/, word for word."""
    for file, heading, basis, _, _ in FACTS:
        body = " ".join(knowledge.get(file, heading).body.split())
        for sentence in basis:
            if " ".join(sentence.split()) not in body:
                raise ValueError(f"Home fact not found word for word in knowledge/{file}: {heading}: {sentence!r}")


def facts(code: str = "en") -> List[Tuple[str, str, str]]:
    """[(the card's text, Source, Link)] in English or Hindi. Raises if a basis sentence is gone."""
    check_sources()
    out = []
    for file, heading, _, english, hindi in FACTS:
        if english is None:  # a basis-only entry (the exception added to the card before it)
            continue
        entry = knowledge.get(file, heading)
        out.append((hindi if code == "hi" and hindi else english, entry.source, entry.link))
    return out
