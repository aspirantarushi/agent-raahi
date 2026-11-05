"""Official sites: the only sources research may cite, and how knowledge links are marked. Plain code.

A link counts when its host is one of these or ends with "." + one of these. Where each non-gov.in
address was confirmed is noted beside it.
"""

import urllib.parse

# Official sites only. A link counts when its host is one of these or ends with "." + one of these.
ALLOWED_SUFFIXES = ("gov.in", "nic.in")  # central and state government, India Code, NALSA, SLSAs, most courts
ALLOWED_HOSTS = (
    "indiacode.nic.in", "nalsa.gov.in", "sci.gov.in", "ecourts.gov.in",
    "rbi.org.in",             # Reserve Bank of India (the banking regulator)
    "allahabadhighcourt.in",  # Allahabad High Court
    "patnahighcourt.gov.in",
    # Electricity regulators and state power companies whose sites are not under gov.in / nic.in.
    # Each address was confirmed on 5 November 2026 on a government page, or on the state-owned
    # holding company's page that a government page links to (where shown):
    # Bihar
    "berc.co.in",     # Bihar Electricity Regulatory Commission (also its Ombudsman and CGRF pages):
                      #   state.bihar.gov.in and cercind.gov.in/serc_hin.html
    "bsphcl.co.in",   # Bihar State Power (Holding) Company Ltd: state.bihar.gov.in
    "nbpdcl.co.in",   # North Bihar Power Distribution Company Ltd: bsphcl.co.in/main.htm
    "sbpdcl.co.in",   # South Bihar Power Distribution Company Ltd: bsphcl.co.in/main.htm
    "bsptcl.in",      # Bihar State Power Transmission Company Ltd: bsphcl.co.in/main.htm
    "bspgcl.co.in",   # Bihar State Power Generation Company Ltd: bsphcl.co.in/main.htm
    # Uttar Pradesh
    "uperc.org",      # UP Electricity Regulatory Commission (also the Electricity Ombudsman page):
                      #   cercind.gov.in/serc_hin.html
    "uppcl.org",      # UP Power Corporation Ltd: cercind.gov.in/sebs.html
    "pvvnl.org",      # Paschimanchal Vidyut Vitran Nigam Ltd: cercind.gov.in/sebs.html and uppcl.org
    "mvvnl.in",       # Madhyanchal Vidyut Vitran Nigam Ltd: cercind.gov.in/sebs.html and uppcl.org
    "dvvnl.org",      # Dakshinanchal Vidyut Vitran Nigam Ltd: cercind.gov.in/sebs.html and uppcl.org
    "kesco.org.in",   # Kanpur Electricity Supply Company (current address): uppcl.org
    "kesco.co.in",    # Kanpur Electricity Supply Company (older address, still live): cercind.gov.in/sebs.html
    "upptcl.org",     # UP Power Transmission Corporation Ltd: uppcl.org
    # Purvanchal Vidyut Vitran Nigam is puvvnl.up.nic.in (cercind.gov.in/sebs.html): already allowed (nic.in).
)


def host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def allowed_link(url: str) -> bool:
    if not url or urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return False
    h = host(url)
    return any(h == d or h.endswith("." + d) for d in ALLOWED_SUFFIXES + ALLOWED_HOSTS)


SECONDARY = "(secondary source: to be replaced)"
