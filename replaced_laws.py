"""Laws that have been replaced, so research never relies on them without a warning. Plain code.

Each entry: the old law (and the short names it goes by), the law that replaced it, the date, and the
official page where the date and the list were confirmed (6 November 2026).
- The three criminal laws: in force from 1 July 2024 (Ministry of Home Affairs notifications).
- The four labour codes: in force from 21 November 2025; together they replaced 29 central labour Acts
  (PIB document of 21 November 2025, which lists the Acts in each code; the Code on Wages list is in
  PIB release PRID 2193095).
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import List

CRIMINAL = date(2024, 7, 1)
LABOUR = date(2025, 11, 21)
SRC_CRIMINAL = "Ministry of Home Affairs notifications bringing the new criminal laws into force on 1 July 2024"
SRC_LABOUR = ("PIB, \"India's Labour Reforms\" (21 November 2025): https://static.pib.gov.in/WriteReadData/"
              "specificdocs/documents/2025/nov/doc20251121701501.pdf")
SRC_WAGES = "PIB release on the Code on Wages, 2019: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2193095"
BNS, BNSS, BSA = "Bharatiya Nyaya Sanhita, 2023", "Bharatiya Nagarik Suraksha Sanhita, 2023", "Bharatiya Sakshya Adhiniyam, 2023"
WAGES, IR, SS, OSH = ("Code on Wages, 2019", "Industrial Relations Code, 2020", "Code on Social Security, 2020",
                      "Occupational Safety, Health and Working Conditions Code, 2020")

# (old law, other names it is written as, new law, date, source)
REPLACED = [
    ("Indian Penal Code, 1860", ["Indian Penal Code", "IPC", "I.P.C."], BNS, CRIMINAL, SRC_CRIMINAL),
    ("Code of Criminal Procedure, 1973", ["Code of Criminal Procedure", "CrPC", "Cr.P.C.", "Criminal Procedure Code"],
     BNSS, CRIMINAL, SRC_CRIMINAL),
    ("Indian Evidence Act, 1872", ["Indian Evidence Act", "Evidence Act"], BSA, CRIMINAL, SRC_CRIMINAL),
    # Code on Wages, 2019
    ("Payment of Wages Act, 1936", ["Payment of Wages Act", "Payment of Wages (Procedures) Rules",
                                    "Payment of Wages (Procedure) Rules"], WAGES, LABOUR, SRC_WAGES),
    ("Minimum Wages Act, 1948", ["Minimum Wages Act", "Minimum Wages (Central) Rules"], WAGES, LABOUR, SRC_WAGES),
    ("Payment of Bonus Act, 1965", ["Payment of Bonus Act"], WAGES, LABOUR, SRC_WAGES),
    ("Equal Remuneration Act, 1976", ["Equal Remuneration Act"], WAGES, LABOUR, SRC_WAGES),
    # Industrial Relations Code, 2020
    ("Trade Unions Act, 1926", ["Trade Unions Act"], IR, LABOUR, SRC_LABOUR),
    ("Industrial Employment (Standing Orders) Act, 1946", ["Industrial Employment (Standing Orders) Act",
                                                          "Standing Orders Act"], IR, LABOUR, SRC_LABOUR),
    ("Industrial Disputes Act, 1947", ["Industrial Disputes Act"], IR, LABOUR, SRC_LABOUR),
    # Code on Social Security, 2020
    ("Employee's Compensation Act, 1923", ["Employee's Compensation Act", "Employees' Compensation Act",
                                          "Employees Compensation Act", "Workmen's Compensation Act"], SS, LABOUR, SRC_LABOUR),
    ("Employees' State Insurance Act, 1948", ["Employees' State Insurance Act", "ESI Act"], SS, LABOUR, SRC_LABOUR),
    ("Employees' Provident Funds and Miscellaneous Provisions Act, 1952", ["Employees' Provident Funds",
                                                                           "EPF Act"], SS, LABOUR, SRC_LABOUR),
    ("Employment Exchanges (Compulsory Notification of Vacancies) Act, 1959", ["Employment Exchanges"], SS, LABOUR,
     SRC_LABOUR),
    ("Maternity Benefit Act, 1961", ["Maternity Benefit Act"], SS, LABOUR, SRC_LABOUR),
    ("Payment of Gratuity Act, 1972", ["Payment of Gratuity Act", "Gratuity Act"], SS, LABOUR, SRC_LABOUR),
    ("Cine-Workers Welfare Fund Act, 1981", ["Cine-Workers Welfare Fund Act"], SS, LABOUR, SRC_LABOUR),
    ("Building and Other Construction Workers' Welfare Cess Act, 1996", ["Welfare Cess Act"], SS, LABOUR, SRC_LABOUR),
    ("Unorganised Workers' Social Security Act, 2008", ["Unorganised Workers' Social Security Act",
                                                        "Unorganised Workers Social Security Act"], SS, LABOUR, SRC_LABOUR),
    # Occupational Safety, Health and Working Conditions Code, 2020
    ("Factories Act, 1948", ["Factories Act"], OSH, LABOUR, SRC_LABOUR),
    ("Plantations Labour Act, 1951", ["Plantations Labour Act"], OSH, LABOUR, SRC_LABOUR),
    ("Mines Act, 1952", ["Mines Act"], OSH, LABOUR, SRC_LABOUR),
    ("Working Journalists and other Newspaper Employees (Conditions of Service and Miscellaneous Provisions) Act, 1955",
     ["Working Journalists and other Newspaper Employees"], OSH, LABOUR, SRC_LABOUR),
    ("Working Journalists (Fixation of Rates of Wages) Act, 1958", ["Working Journalists (Fixation of Rates of Wages)"],
     OSH, LABOUR, SRC_LABOUR),
    ("Motor Transport Workers Act, 1961", ["Motor Transport Workers Act"], OSH, LABOUR, SRC_LABOUR),
    ("Beedi and Cigar Workers (Conditions of Employment) Act, 1966", ["Beedi and Cigar Workers"], OSH, LABOUR, SRC_LABOUR),
    ("Contract Labour (Regulation and Abolition) Act, 1970", ["Contract Labour (Regulation and Abolition) Act",
                                                             "Contract Labour Act"], OSH, LABOUR, SRC_LABOUR),
    ("Sales Promotion Employees (Conditions of Service) Act, 1976", ["Sales Promotion Employees"], OSH, LABOUR, SRC_LABOUR),
    ("Inter-State Migrant Workmen (Regulation of Employment and Conditions of Service) Act, 1979",
     ["Inter-State Migrant Workmen"], OSH, LABOUR, SRC_LABOUR),
    ("Cine-Workers and Cinema Theatre Workers (Regulation of Employment) Act, 1981",
     ["Cine-Workers and Cinema Theatre Workers"], OSH, LABOUR, SRC_LABOUR),
    ("Dock Workers (Safety, Health and Welfare) Act, 1986", ["Dock Workers (Safety, Health and Welfare) Act"], OSH,
     LABOUR, SRC_LABOUR),
    ("Building and Other Construction Workers (Regulation of Employment and Conditions of Service) Act, 1996",
     ["Building and Other Construction Workers (Regulation of Employment"], OSH, LABOUR, SRC_LABOUR),
]


@dataclass
class Replaced:
    old: str
    new: str
    since: date
    source: str

    def warning(self) -> str:
        return f"Replaced by the {self.new} on {self.since.day} {self.since:%B %Y}: check before approving."


def _pattern(name: str) -> re.Pattern:
    words = re.escape(name).replace(r"\ ", r"\s+").replace("'", "['’]?")
    return re.compile(rf"(?<![A-Za-z]){words}(?![A-Za-z])", re.I if not name.isupper() else 0)


def _with_rules(names: List[str]) -> List[str]:
    """Rules made under an old Act go with it ("Payment of Wages Act" -> also "Payment of Wages Rules")."""
    return names + [re.sub(r"\s+Act$", " Rules", n) for n in names if n.endswith(" Act")]


PATTERNS = [(old, [_pattern(n) for n in _with_rules([old] + names)], new, since, src)
            for old, names, new, since, src in REPLACED]


def found_in(text: str) -> List[Replaced]:
    """Replaced laws a text names (each once)."""
    out = []
    for old, patterns, new, since, src in PATTERNS:
        if any(p.search(text or "") for p in patterns):
            out.append(Replaced(old, new, since, src))
    return out


def still_relies_on_old(text: str) -> List[Replaced]:
    """Replaced laws named without the law that replaced them (an edited point that names both is fine)."""
    return [r for r in found_in(text) if r.new.split(",")[0].casefold() not in (text or "").casefold()]
