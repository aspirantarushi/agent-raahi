"""List every link in knowledge/, knowledge_hi/, learner/, the Home facts band and the drafts (templates/,
templates_hi/ and the code that fills them), and show the ones that fail.

    .venv/bin/python scripts/check_links.py            # all links, failures first
    .venv/bin/python scripts/check_links.py --failed   # only the failures

Government sites often block scripts (403, timeouts, odd certificates). A link this script flags is
NOT proof that it is broken: open it in a browser first. Only a link that also fails in a browser is
broken. No personal data is sent: only a generic browser name, and the link itself.
"""

import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

URL = re.compile(r"https?://[^\s\"'<>\]`,]+(?:\([^\s)]*\))?[^\s\"'<>\]`,()]*")
PLACES = ["knowledge", "knowledge_hi", "learner", "templates", "templates_hi"]
DRAFT_CODE = ["drafts.py", "general.py", "casework.py", "home.py"]
AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def links() -> dict:
    """{link: [where it is used]}"""
    found = {}

    def add(url, where):
        if not url.startswith(("http://", "https://")):  # "none": a source shown by name only
            return
        url = url.rstrip(".,;:")
        if url.count(")") > url.count("("):  # "(https://...)" in a sentence: the bracket is not the link's
            url = url.rstrip(")")
        found.setdefault(url, [])
        if where not in found[url]:
            found[url].append(where)

    for place in PLACES:
        for path in sorted((ROOT / place).glob("*")):
            if path.suffix == ".csv":  # one link per cell
                import csv
                with open(path, newline="", encoding="utf-8") as f:
                    for row in csv.reader(f):
                        for cell in row:
                            for url in URL.findall(cell):
                                add(url, f"{place}/{path.name}")
            elif path.suffix == ".md":
                for url in URL.findall(path.read_text(encoding="utf-8")):
                    add(url, f"{place}/{path.name}")
    for name in DRAFT_CODE:
        for url in URL.findall((ROOT / name).read_text(encoding="utf-8")):
            add(url, name)
    import home  # the facts band: each card's own source link
    for _, _, link in home.facts("en"):
        add(link, "Home facts band")
    return found


def check(url: str) -> str:
    """"ok 200", or what went wrong."""
    context = ssl.create_default_context()
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=25, context=context) as reply:
                return f"ok {reply.status}"
        except urllib.error.HTTPError as err:
            if method == "HEAD" and err.code in (403, 404, 405, 501):
                continue  # some servers refuse HEAD: try GET
            return f"HTTP {err.code}"
        except ssl.SSLError as err:
            return f"certificate problem ({err.reason})"
        except urllib.error.URLError as err:
            return f"cannot reach ({getattr(err, 'reason', err)})"
        except Exception as err:  # timeouts and others
            return f"failed ({type(err).__name__})"
    return "failed"


def main():
    only_failed = "--failed" in sys.argv
    found = links()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(zip(found, pool.map(check, found)))
    failed = [u for u in found if not results[u].startswith("ok")]
    print(f"{len(found)} links, {len(failed)} flagged (open each flagged link in a browser before calling it broken)\n")
    for url in failed + ([] if only_failed else [u for u in found if u not in failed]):
        print(f"{results[url]:<40} {url}\n{'':<40} used in: {', '.join(found[url])}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
