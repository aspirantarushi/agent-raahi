"""Small building blocks for the look and feel: header, safety bar, step progress, status chips.

Plain HTML and CSS (assets/app.css); the logo files in assets/brand/ are drawn inline; no animations,
no extra libraries.
"""

import html
import re
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
CSS_FILE = HERE / "assets" / "app.css"


def style() -> str:
    """The stylesheet, read each time so edits show without restarting the app (it is small)."""
    return f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>"


BRAND = HERE / "assets" / "brand"
LOGO_FILE = BRAND / "raahi-mark.svg"            # on light backgrounds
LOGO_ON_DARK_FILE = BRAND / "raahi-mark-on-dark.svg"  # on navy
FAVICON_FILE = BRAND / "favicon.svg"            # browser tab icon
APP_ICON_FILE = BRAND / "raahi-app-icon.svg"    # home-screen icon (Streamlit has no setting for it yet)


def inline_svg(path: Path, size: int) -> str:
    """The logo file drawn inline (no extra download). The files are used exactly as given; only the
    hidden <metadata> block (a content signature, about 8 KB, not part of the drawing) is left out
    of the page to keep it light on 3G."""
    svg = re.sub(r"<metadata>.*?</metadata>", "", path.read_text(encoding="utf-8").strip(), flags=re.S)
    return svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)


def logo_mark(size: int = 40) -> str:
    """The R whose leg becomes a road, with an amber light (assets/brand/raahi-mark.svg)."""
    return inline_svg(LOGO_FILE, size)


def logo_on_dark(size: int = 40) -> str:
    return inline_svg(LOGO_ON_DARK_FILE, size)


def wordmark(name: str) -> str:
    """'AGENT Raahi': the first word small in capitals, the last in the accent colour (also 'एजेंट राही')."""
    first, _, last = name.rpartition(" ")
    return (f'<small class="agent">{html.escape(first)}</small> <span>{html.escape(last)}</span>' if first
            else f"<span>{html.escape(name)}</span>")


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


# ---------- top bar and home page sections (plain HTML, styled by assets/app.css) ----------

def brand(name: str, size: int = 32) -> str:
    return f'<div class="brand">{logo_mark(size)}<div class="word">{wordmark(name)}</div></div>'


def topnav(links) -> str:
    """links: [(anchor id, label)] for in-page links on the home page."""
    return '<nav class="topnav" aria-label="Sections">' + "".join(
        f'<a href="#{html.escape(a)}">{html.escape(label)}</a>' for a, label in links) + "</nav>"


def hero(kicker: str, lead: str, sub: str) -> str:
    return (f'<section class="hero"><div class="kicker">{html.escape(kicker)}</div>'
            f'<div class="lead">{html.escape(lead)}</div><p class="sub">{html.escape(sub)}</p></section>')


def helpline(danger: str, aid: str) -> str:
    return (f'<p class="helpline"><a class="danger" href="tel:112">{html.escape(danger)}</a> &nbsp;·&nbsp; '
            f'<a href="tel:15100">{html.escape(aid)}</a></p>')


def section(anchor: str, title: str, sub: str = "") -> str:
    return (f'<div id="{html.escape(anchor)}" class="section-title">{html.escape(title)}</div>'
            + (f'<div class="section-sub">{html.escape(sub)}</div>' if sub else ""))


def cards(items, columns: str = "four", numbered: bool = False) -> str:
    """items: [(title, text)]."""
    out = []
    for i, (title, text) in enumerate(items, 1):
        num = f'<span class="num">{i}</span>' if numbered else ""
        out.append(f'<div class="card">{num}<h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>')
    return f'<div class="grid {columns}">{"".join(out)}</div>'


def compare(today_title: str, today, raahi_title: str, raahi) -> str:
    li = lambda xs: "".join(f"<li>{html.escape(x)}</li>" for x in xs)
    return (f'<div class="grid two"><div class="card today"><h3>{html.escape(today_title)}</h3><ul>{li(today)}</ul></div>'
            f'<div class="card raahi"><h3>{html.escape(raahi_title)}</h3><ul>{li(raahi)}</ul></div></div>')


def facts_band(title: str, facts) -> str:
    """facts: [(sentence from knowledge/, its Source line)]."""
    rows = "".join(f'<div class="fact"><p>{html.escape(text)}</p><small>{html.escape(source)}</small></div>'
                   for text, source in facts)
    return (f'<section class="facts" id="facts"><h2><span class="facts-mark">{logo_on_dark(36)}</span>'
            f'{html.escape(title)}</h2>{rows}</section>')


def footer(name: str, tagline: str, text: str) -> str:
    return (f'<footer class="footer"><b>{wordmark(name)}</b> · {html.escape(tagline)}<br>{html.escape(text)}</footer>')
