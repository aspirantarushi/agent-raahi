"""Build docs/grey_text_review.csv: every light-grey explanation or instruction on every screen, in screen
order, with its key, the screen, the English and Hindi text, and a blank "My edit" column.

    .venv/bin/python scripts/grey_text_review.py

Light grey in this app: Streamlit captions; the one-line reasons under greyed-out buttons (why_disabled);
"Why this is asked" under questions; the reason under each checklist tick (tick-why); the grey side
notes (sign-in cards, the New case tip) and the grey paragraphs on Home. The order follows each screen's
code from top to bottom (its own drawing order, including the helpers it calls). Nothing is changed.
"""

import ast
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "grey_text_review.csv"
EN = json.loads((ROOT / "i18n" / "en.json").read_text(encoding="utf-8"))
HI = json.loads((ROOT / "i18n" / "hi.json").read_text(encoding="utf-8"))

# (screen name in the sheet, the function that draws it), in the order of the top navigation
SCREENS = [
    ("Home", "home_screen"),
    ("Volunteer sign-in", "clinic_gate"),
    ("Current case", "new_case_screen"),
    ("Case tracker", "my_cases_screen"),
    ("Learn", "learn_screen"),
    ("Practice", "practice_screen"),
    ("Supervisor (sign-in and review)", "supervisor_screen"),
]
GREY_CALLS = {"caption", "why_disabled", "why_asked_line"}           # everything they show is grey
GREY_CLASSES = ("tick-why", "why-asked", "why-off", "nc-tip", "case-sub")  # grey <p> styles in assets/app.css
# Home's grey paragraphs (.hero .sub, .card p, .compare p) and the grey side notes, drawn through ui.py
UI_GREY = {"new_case_side": "all", "signin_side": [1], "guide_card": [2]}
NOT_EXPLANATIONS = re.compile(r"^(fact\.|close\.reason\.|yes$|no$|q\.year_start$|signin\.title$|signin\.help$|"
                              r"nc\.camp_label$|ready\.why\.case_legal_aid$|ready\.why\.answered$|"
                              r"ui\.result\.(checked|table_source)$)")
# keys a shared helper draws on a different screen than the one that reached it first
SCREEN_OF = {re.compile(r"^signin\.s\d$"): "Supervisor (sign-in and review)"}
HOME_GREY = (["home.sub", "home.free"] + [f"home.how{i}_p" for i in range(1, 6)] + ["home.today_p"]
             + [f"home.safe{i}_p" for i in range(1, 7)] + [f"home.learn{i}_p" for i in range(1, 5)])


def keys_in(node) -> list:
    """The i18n keys of every t("key") / t(f"key.{x}") / lang.t(...) call under node, in source order."""
    found = []
    for n in _ordered(node):
        if isinstance(n, ast.Call) and _name(n.func) == "t" and n.args:
            arg = n.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append(arg.value)
            elif isinstance(arg, ast.JoinedStr):  # t(f"why.send.{x}"): every key that fits the pattern
                pattern = "".join(re.escape(v.value) if isinstance(v, ast.Constant) else ".+" for v in arg.values)
                found += [k for k in EN if re.fullmatch(pattern, k)]
        elif isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.Constant) \
                and re.match(r"^[a-z_]+\.[a-z_.]+$", str(n.values[0].value)):  # key = f"ready.why.{x}"; t(key)
            pattern = "".join(re.escape(v.value) if isinstance(v, ast.Constant) else ".+" for v in n.values)
            found += [k for k in EN if re.fullmatch(pattern, k)]
    return found


def _name(func) -> str:
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def _ordered(node):
    """Every node under node, in source order (fields in order, depth first)."""
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _ordered(child)


def grey_keys(func_name: str, funcs: dict, seen: set) -> list:
    """The grey keys a screen function shows, following the local helpers it calls, in drawing order."""
    if func_name in seen or func_name not in funcs:
        return []
    seen.add(func_name)
    out = []
    for n in _ordered(funcs[func_name]):
        if not isinstance(n, ast.Call):
            continue
        name = _name(n.func)
        grey_kw = [k.value for k in n.keywords if k.arg == "captions"]  # the grey line under each radio option
        for value in grey_kw:
            out += keys_in(value)
        if name in GREY_CALLS:
            for arg in n.args:
                out += keys_in(arg)
                for c in _ordered(arg):  # a helper that returns the grey text, e.g. why_asked(...)
                    if isinstance(c, ast.Call) and _name(c.func) in funcs and _name(c.func) != "t":
                        out += keys_in(funcs[_name(c.func)])
        elif name in ("markdown", "html") and n.args and any(
                cls in ast.unparse(n.args[0]) for cls in GREY_CLASSES):
            out += keys_in(n.args[0])
            for c in _ordered(n.args[0]):
                if isinstance(c, ast.Call) and _name(c.func) in funcs and _name(c.func) not in ("t", "show_date"):
                    out += keys_in(funcs[_name(c.func)])
        elif isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and \
                n.func.value.id == "ui" and name in UI_GREY:
            args = n.args if UI_GREY[name] == "all" else [n.args[i] for i in UI_GREY[name] if i < len(n.args)]
            for arg in args:
                out += keys_in(arg)
                for c in _ordered(arg):
                    if isinstance(c, ast.Call) and _name(c.func) in funcs:
                        out += keys_in(funcs[_name(c.func)])
        elif name in funcs and isinstance(n.func, ast.Name):
            out += grey_keys(name, funcs, seen)  # a helper this screen calls: its grey text, in place
    return out


def main():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    funcs = {f.name: f for f in tree.body if isinstance(f, ast.FunctionDef)}
    rows, done = [], set()
    for screen, func in SCREENS:
        keys = HOME_GREY + grey_keys(func, funcs, set()) if screen == "Home" else grey_keys(func, funcs, set())
        for key in keys:
            if key in done or key not in EN or NOT_EXPLANATIONS.match(key):
                continue
            done.add(key)
            where = next((name for pattern, name in SCREEN_OF.items() if pattern.match(key)), screen)
            rows.append([key, where, EN[key], HI.get(key, ""), ""])
    order = [name for name, _ in SCREENS]  # in screen order, then drawing order within each screen
    rows.sort(key=lambda r: order.index(r[1]))
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows the Hindi properly
        writer = csv.writer(f)
        writer.writerow(["Key", "Screen", "English", "Hindi", "My edit"])
        writer.writerows(rows)
    by_screen = {}
    for r in rows:
        by_screen[r[1]] = by_screen.get(r[1], 0) + 1
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} lines", by_screen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
