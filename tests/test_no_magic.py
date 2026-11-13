"""Streamlit "magic" writes the value of any bare expression to the page (it once printed the
DeltaGenerator documentation under "Due this week"). Magic is switched off in .streamlit/config.toml,
and every expression statement in the app's Python files must be a plain call (or a docstring)."""

import ast
import toml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "app.py", *sorted(p for p in ROOT.glob("*.py") if p.name != "app.py")]


def bare_expressions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        v = node.value
        if isinstance(v, ast.Call) or isinstance(v, (ast.Await, ast.Yield, ast.YieldFrom)):
            continue
        if isinstance(v, ast.Constant) and isinstance(v.value, str):   # docstrings
            continue
        if isinstance(v, ast.Constant) and v.value is Ellipsis:         # "..." placeholders
            continue
        bad.append(f"{path.name}:{node.lineno}: {ast.unparse(v)[:80]}")
    return bad


def test_every_expression_statement_is_a_plain_call():
    bad = [b for f in FILES for b in bare_expressions(f)]
    assert not bad, "bare expressions (Streamlit magic would print them):\n" + "\n".join(bad)


def test_the_check_catches_the_patterns(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""doc"""\nprint(1)\n(a() if c else b())\nc and b()\na(), b()\nx\n', encoding="utf-8")
    assert [b.split(":")[1] for b in bare_expressions(f)] == ["3", "4", "5", "6"]


def test_magic_is_switched_off():
    config = toml.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["runner"]["magicEnabled"] is False
