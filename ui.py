"""Small building blocks for the look and feel: header, safety bar, step progress, status chips.

Plain HTML and CSS (assets/app.css); no images, no animations, no extra libraries.
"""

import html
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
CSS_FILE = HERE / "assets" / "app.css"


def style() -> str:
    """The stylesheet, read each time so edits show without restarting the app (it is small)."""
    return f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>"


LOGO_FILE = HERE / "assets" / "logo-mark.svg"


def logo_mark(size: int = 40) -> str:
    """The lamp-and-path mark: a tiny inline SVG (about 0.5 KB), no image download."""
    svg = LOGO_FILE.read_text(encoding="utf-8").strip()
    return svg.replace('width="40" height="40"', f'width="{size}" height="{size}"', 1)


def wordmark(name: str) -> str:
    """'Agent Raahi' with the last word in the accent colour (also 'एजेंट राही')."""
    first, _, last = name.rpartition(" ")
    return f"{html.escape(first)} <span>{html.escape(last)}</span>" if first else f"<span>{html.escape(name)}</span>"


def header(name: str, tagline: str, description: str = "") -> str:
    return (f'<header class="app-header" role="banner"><div class="app-logo">{logo_mark()}</div>'
            f'<div><div class="app-name">{wordmark(name)}</div>'
            f'<div class="app-tagline">{html.escape(tagline)}</div>'
            + (f'<div class="app-description">{html.escape(description)}</div>' if description else "")
            + '</div></header>')


def safety_bar(danger: str, legal_aid: str) -> str:
    """Always visible; tappable phone links on phones."""
    return (f'<nav class="safety-bar" aria-label="Emergency and helplines">'
            f'<a class="danger" href="tel:112">{html.escape(danger)}</a>'
            f'<a href="tel:15100">{html.escape(legal_aid)}</a></nav>')


def stepper(steps: List[str], current: int) -> str:
    """Step progress, for example 1 Tell the story -> 2 Questions -> ... (current is 1-based)."""
    items = []
    for i, label in enumerate(steps, 1):
        state = "done" if i < current else "now" if i == current else ""
        aria = ' aria-current="step"' if i == current else ""
        items.append(f'<li class="{state}"{aria}><b>{i}</b><span>{html.escape(label)}</span></li>')
    return f'<ol class="stepper" aria-label="Progress">{"".join(items)}</ol>'


def chip(kind: str, text: str) -> str:
    return f'<span class="chip {html.escape(kind)}">{html.escape(text)}</span>'
