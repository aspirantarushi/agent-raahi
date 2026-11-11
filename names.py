"""Words in a story that look like people's names: common Indian first names and surnames, in English
letters and in Devanagari. Plain code; a rough check, never a guarantee (the volunteer still ticks
"no names"). Names are never needed: people are described by their role.

Not flagged: places (state names, and words used as places, such as "in Patna" or "Ganga district"),
and names that are also everyday words ("asha" = hope, "prem" = love, "raja" = king, "das" = ten,
"lal" = red) unless written with a capital letter in English letters (never in Devanagari, which has no
capitals).
"""

import re
from typing import List

FIRST_NAMES = """
aarav aarti abdul abhay abhishek aditi aditya afsana ahmed ajay ajit akash akhil akhtar alka alok aman amar amina amit
amita amrita anand anil anita anjali ankit ankita anu anupam anuradha anwar archana arjun arun aruna arvind asif ashok
ayesha babita babu baldev balram bharat bhavna bhupendra bimla brijesh chanda chandan chetan deepa deepak deepika dev
devendra dharmendra dilip dinesh divya durga farida farhan fatima ganesh gaurav geeta girish gopal govind gurpreet
harish hemant ibrahim imran indira irfan jagdish jaspreet jaya jitendra kamal kamla kanchan karan kavita kavya khushboo
krishna kuldeep lakshmi lalita latha laxmi madhu mahendra mahesh mamta manish manju manoj meena meera mohammad mohammed
mohan mohini monika mukesh munni nafisa naresh naveen neelam neeraj neha nikhil nirmala nisha nitin pankaj parveen pawan
pinki poonam prakash pramod prashant pratibha praveen preeti priya priyanka radha rahul rajendra rajesh rajiv rajni rakesh
ramesh rameshwar ravi rekha reshma ritu rohit roshan rubina sachin sadhana sahil sameer sandeep sangeeta sanjay sanjeev
santosh sapna sarita satish savita seema shabana shahid shakuntala shalini shanti sharda shilpa shiv shivani shobha
shyam sita sonia subhash sudha suman sumit sunil sunita suraj suresh sushil sushma swati tanvi tarun uma umesh usha vandana
varun vijay vikas vikram vimla vinay vinod vipin vishal yash yogesh zahid zainab
"""
SURNAMES = """
agarwal ahmad ali ansari bano begum bhatt chauhan chaudhary chaudhari choudhary devi dubey dutta ghosh gupta iyer jadhav
jha joshi kaur khan kumar kumari mandal mehta mishra nair pandey parmar patel patil pillai prasad qureshi rajput rathore
reddy saxena sen sharma shaikh shukla singh sinha siddiqui solanki srivastava thakur tiwari tripathi verma yadav
"""
# Names that are also everyday words: only flagged when capitalised in English letters
EVERYDAY_WORDS = set("""
asha kiran pooja puja prem raja rani sona chand deep jyoti roshni sunny lucky ram lal das shah rao jain ganga
anand shanti durga lakshmi krishna sita radha deepa kamal aman babu chanda sapna suraj roshan madhu shiv dev ganesh
devi sen vijay seema rekha kavita geeta poonam prakash santosh mamta usha neelam sarita savita
""".split())

DEVANAGARI = """
रमेश सुरेश महेश राजेश मुकेश दिनेश राकेश अनिल सुनील मनोज संजय अजय अमित सुमित रोहित राहुल
विनोद अशोक सुनीता अनीता मंजू मीना शबाना फ़ातिमा फातिमा
आयशा रुबीना इमरान आसिफ़ आसिफ अब्दुल मोहम्मद शर्मा वर्मा यादव गुप्ता मिश्रा पांडेय पाण्डेय तिवारी शुक्ला
सिंह कुमार कुमारी खान अंसारी कुरैशी पटेल ठाकुर चौहान झा जोशी प्रसाद श्रीवास्तव सिन्हा
""".split()
# Names that are also everyday Hindi words are left out here, because Devanagari has no capitals to tell
# them apart: प्रकाश (light), संतोष (satisfaction), सीमा (border), रेखा (line), कविता (poem), विजय (victory),
# गीता, ममता, पूनम, उषा, लता, नीलम, सरिता, सविता, देवी.

_LATIN = set(FIRST_NAMES.split()) | set(SURNAMES.split())
_DEVANAGARI = set(DEVANAGARI)
PLACE_BEFORE = re.compile(r"(?:\b(?:in|at|near|from|lives in|works in|district|city of|town of|village of)|"
                          r"(?:में|से|ज़िला|जिला))\s*$", re.I)
PLACE_AFTER = re.compile(r"^\s*(?:district|distt|city|zila|jila|town|village|gaon|nagar|tehsil|block|river|"
                         r"police station|thana|mein|me\b|ज़िले|जिले|ज़िला|जिला|शहर|गाँव|गांव|नगर|नदी)", re.I)


def _is_place(text: str, start: int, end: int) -> bool:
    return bool(PLACE_BEFORE.search(text[max(0, start - 20):start]) or PLACE_AFTER.search(text[end:end + 20]))


def found_in(text: str, states: set = frozenset()) -> List[str]:
    """The words in text that look like people's names, as written, each once, in order."""
    found = []
    for m in re.finditer(r"[A-Za-z]+|[ऀ-ॿ]+", text or ""):
        word = m.group(0)
        key = word.casefold()
        if word in found or key in states:
            continue
        if word[0].isascii():
            if key not in _LATIN or (key in EVERYDAY_WORDS and not word[0].isupper()):
                continue
        elif word not in _DEVANAGARI:
            continue
        if _is_place(text, m.start(), m.end()):
            continue
        found.append(word)
    return found
