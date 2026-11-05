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
    """Step progress, "1. Tell the story" -> "2. Questions" -> ... on one line each (current is 1-based)."""
    items = []
    for i, label in enumerate(steps, 1):
        state = "done" if i < current else "now" if i == current else ""
        aria = ' aria-current="step"' if i == current else ""
        items.append(f'<li class="{state}"{aria}>{i}. {html.escape(label)}</li>')
    return f'<ol class="stepper" aria-label="Progress">{"".join(items)}</ol>'


def chip(kind: str, text: str) -> str:
    return f'<span class="chip {html.escape(kind)}">{html.escape(text)}</span>'


# ---------- top bar and home page sections (plain HTML, styled by assets/app.css) ----------
# Layout, spacing and type follow docs/design/home-reference.html.

def icon(name: str) -> str:
    """A Material Symbols icon (the outlined icons Streamlit already ships; nothing extra to download)."""
    return f'<span class="mi" aria-hidden="true">{html.escape(name)}</span>'


def brand(name: str, size: int = 48) -> str:
    return f'<div class="brand">{logo_mark(size)}<div class="word">{wordmark(name)}</div></div>'


def hero(badge: str, kicker: str, lead: str, sub: str, name: str = "") -> str:
    """The logo with the name (large), the badge, "Listen. Ask. Refer." (small), then the tagline as
    the main heading."""
    logo = (f'<div class="hero-brand">{logo_mark(72)}<div class="word">{wordmark(name)}</div></div>' if name else "")
    return (f'<section class="hero" id="top">{logo}<span class="badge">{html.escape(badge)}</span>'
            f'<div class="kicker">{html.escape(kicker)}</div><h1>{html.escape(lead)}</h1>'
            f'<p class="sub">{html.escape(sub)}</p></section>')


def helpline(free: str, danger: str, aid: str) -> str:
    """"Free and open source.", then the two tap-to-call helplines below it, each with its own icon."""
    return (f'<div class="helpline"><p>{html.escape(free)}</p><p class="lines">'
            f'<a class="danger" href="tel:112">{icon("call")}<span>{html.escape(danger)}</span></a>'
            f'<a href="tel:15100">{icon("support_agent")}<span>{html.escape(aid)}</span></a></p></div>')


def eyebrow(text: str) -> str:
    dev = " dev" if re.search("[\u0900-\u097F]", text) else ""
    return f'<p class="eyebrow{dev}">{html.escape(text)}</p>'


def section(anchor: str, label: str, title: str, body: str, center: bool = True, extra: str = "") -> str:
    return (f'<section id="{html.escape(anchor)}" class="sec{" center" if center else ""} {extra}">'
            f'{eyebrow(label)}<h2>{html.escape(title)}</h2>{body}</section>')


def how_cards(items) -> str:
    """items: [(title, text)], numbered 01, 02, ..."""
    return '<div class="grid how">' + "".join(
        f'<div class="card"><span class="num">{i:02d}</span><h3>{html.escape(t)}</h3><p>{html.escape(p)}</p></div>'
        for i, (t, p) in enumerate(items, 1)) + "</div>"


def safe_cards(items) -> str:
    """items: [(icon name, title, text)]: an icon above each card's title."""
    return '<div class="grid safe">' + "".join(
        f'<div class="card">{icon(name)}<h3>{html.escape(t)}</h3><p>{html.escape(p)}</p></div>'
        for name, t, p in items) + "</div>"


def compare(today: dict, raahi: dict) -> str:
    """Today (a case in many places) beside With Agent Raahi (one case file, shown as a practice example)."""
    e = html.escape
    chips = "".join(f"<span>{e(c)}</span>" for c in today["chips"])
    return (f'<section class="sec" id="what-changes"><div class="compare">'
            f'<div class="today">{eyebrow(today["eyebrow"])}<h3>{e(today["title"])}</h3>'
            f'<div class="chips">{chips}</div><p>{e(today["text"])}</p></div>'
            f'<div class="raahi">{eyebrow(raahi["eyebrow"])}<h3>{e(raahi["title"])}</h3>'
            f'<div class="mini"><span class="ex">{e(raahi["example"])}</span>'
            f'<div class="top"><span>{e(raahi["case"])}</span>{chip("sent-back", raahi["status"])}</div>'
            f'<div class="bar"><i></i></div><span class="line">{e(raahi["check"])}</span>'
            f'<span class="line">{e(raahi["next"])}</span></div></div></div></section>')


def source_link(source: str, link: str) -> str:
    """"Source: <name>", the name itself the link (opens in a new tab); no web address in brackets."""
    name = html.escape(source)
    if link and link.lower() != "none" and link.startswith(("http://", "https://")):
        name = f'<a href="{html.escape(link)}" target="_blank" rel="noopener noreferrer">{name}</a>'
    return f"Source: {name}"


def facts_band(title: str, facts) -> str:
    """facts: [(sentence from knowledge/, its Source, its Link)]. Full width navy band; each source
    in italics, its name the link."""
    rows = "".join(f'<div class="fact"><p>{html.escape(text)}</p><em>{source_link(source, link)}</em></div>'
                   for text, source, link in facts)
    return (f'<section class="facts-band" id="facts">'
            + eyebrow(title).replace('">', f'"><span class="facts-mark">{logo_on_dark(28)}</span>', 1)
            + f'<div class="grid">{rows}</div></section>')


def footer(name: str, tagline: str, text: str, tagline_hi: str = "") -> str:
    second = f' · <span lang="hi">{html.escape(tagline_hi)}</span>' if tagline_hi and tagline_hi != tagline else ""
    return (f'<footer class="footer"><span><b>{wordmark(name)}</b> · {html.escape(tagline)}{second}</span>'
            f'<span>{html.escape(text)}</span></footer>')


def guide_card(name: str, title: str, text: str) -> str:
    """A Learn card: topic icon above the title and a line about it (like the safety cards)."""
    return f'<div class="card guide">{icon(name)}<h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>'


def tag(text: str) -> str:
    """A small label with a light tinted background, like "added 2026-11-05 by Volunteer A"."""
    return f'<span class="tag">{html.escape(text)}</span>'


# ---------- the shared case tracker ----------

def tracker_table(rows, headers: dict, overdue_word: str) -> str:
    """rows: dicts with case, code, status (chip HTML, already safe), next, due, overdue, camp, who.
    Overdue due dates are red and also say "Overdue" (never colour alone)."""
    keys = ["case", "code", "status", "next", "due", "camp", "who"]
    head = "".join(f"<th>{html.escape(headers[k])}</th>" for k in keys)
    body = []
    for r in rows:
        cells = []
        for k in keys:
            if k == "status":
                cells.append(f'<td data-label="{html.escape(headers[k])}">{r[k]}</td>')
            elif k == "due" and r.get("overdue"):
                cells.append(f'<td data-label="{html.escape(headers[k])}" class="overdue">'
                             f'<b>{html.escape(overdue_word)}</b> · {html.escape(r[k])}</td>')
            else:
                cells.append(f'<td data-label="{html.escape(headers[k])}">{html.escape(str(r[k] or ""))}</td>')
        body.append(f'<tr class="{"overdue" if r.get("overdue") else ""}">{"".join(cells)}</tr>')
    return (f'<div class="tracker-wrap"><table class="tracker"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


SLIP_CSS = """
body { margin: 0; font-family: "Noto Sans", "Noto Sans Devanagari", system-ui, sans-serif; color: #13213B;
  background: transparent; }
.slip { width: 300px; margin: 8px auto; background: #fff; border: 2px solid #13213B; border-radius: 16px;
  padding: 16px 18px; text-align: center; }
.clinic { font-weight: 700; font-size: 17px; }
.case { font-size: 14px; margin-top: 4px; }
.code { font-size: 34px; font-weight: 800; letter-spacing: 6px; margin: 6px 0 2px 0; font-family: ui-monospace, Menlo, monospace; }
.qr { width: 190px; height: 190px; image-rendering: pixelated; }
.bring { font-weight: 700; font-size: 17px; margin-top: 4px; }
.help { font-size: 14px; margin-top: 10px; border-top: 1px solid #ECE7DC; padding-top: 8px; }
.buttons { text-align: center; margin: 10px 0; }
button { font: inherit; font-weight: 600; min-height: 44px; padding: 0 18px; margin: 4px; border-radius: 999px;
  border: 1px solid #13213B; background: #13213B; color: #fff; cursor: pointer; }
button.light { background: #fff; color: #13213B; }
@media print { .buttons { display: none; } .slip { border-width: 3px; } }
"""

SLIP_JS = """
const S = JSON.parse(document.getElementById('slip-data').textContent);
function drawSlip(done) {
  const c = document.createElement('canvas'); c.width = 720; c.height = 1040;
  const x = c.getContext('2d'); const font = '"Noto Sans", "Noto Sans Devanagari", system-ui, sans-serif';
  x.fillStyle = '#ffffff'; x.fillRect(0, 0, 720, 1040);
  x.strokeStyle = '#13213B'; x.lineWidth = 6; x.strokeRect(12, 12, 696, 1016);
  x.fillStyle = '#13213B'; x.textAlign = 'center';
  x.font = '700 38px ' + font; x.fillText(S.clinic, 360, 90);
  x.font = '500 30px ' + font; x.fillText(S.case_id, 360, 145);
  x.font = '800 84px ui-monospace, Menlo, monospace'; x.fillText(S.code.split('').join(' '), 360, 250);
  const img = new Image();
  img.onload = function () {
    x.imageSmoothingEnabled = false; x.drawImage(img, 170, 290, 380, 380);
    x.font = '700 40px ' + font; x.fillText(S.bring_en, 360, 745); x.fillText(S.bring_hi, 360, 805);
    x.font = '600 32px ' + font; x.fillText(S.help_line, 360, 900); x.fillText(S.help_line_hi, 360, 950);
    done(c);
  };
  img.src = S.qr;
}
function saveImage() {
  drawSlip(function (c) {
    c.toBlob(function (blob) {
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = 'case-slip-' + S.code + '.png'; document.body.appendChild(a); a.click(); a.remove();
    }, 'image/png');
  });
}
"""


def slip_page(lines: dict, qr_data_uri: str, print_label: str = "Print", save_label: str = "Save as image",
              print_only: bool = False) -> str:
    """The case slip as a small page: the clinic, the case number, the code, the QR code, "Bring this next
    time" in English and Hindi, and the helplines 112 and 15100. Nothing about the case or the problem.
    The image is drawn by the browser (which writes Hindi correctly) and saved as a PNG for WhatsApp."""
    import json
    e = html.escape
    help_en = "Emergency 112 · Free legal aid 15100"
    help_hi = "आपातकाल 112 · मुफ़्त क़ानूनी मदद 15100"
    slip = (f'<div class="slip"><div class="clinic">{e(lines["clinic"])}</div>'
            f'<div class="case">{e(lines["case_id"])}</div><div class="code">{e(lines["code"])}</div>'
            f'<img class="qr" alt="QR code" src="{e(qr_data_uri)}">'
            f'<div class="bring">{e(lines["bring_en"])}</div><div class="bring">{e(lines["bring_hi"])}</div>'
            f'<div class="help">{e(help_en)}<br>{e(help_hi)}</div></div>')
    if print_only:
        return (f'<!doctype html><html><head><meta charset="utf-8"><title>{e(lines["code"])}</title>'
                f'<style>{SLIP_CSS}</style></head><body onload="window.print()">{slip}</body></html>')
    data = json.dumps({**lines, "qr": qr_data_uri, "help_line": help_en, "help_line_hi": help_hi},
                      ensure_ascii=False).replace("</", "<\\/")
    buttons = (f'<div class="buttons"><button onclick="window.print()">{e(print_label)}</button>'
               f'<button class="light" onclick="saveImage()">{e(save_label)}</button></div>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{SLIP_CSS}</style></head><body>'
            f'{slip}{buttons}<script type="application/json" id="slip-data">{data}</script>'
            f'<script>{SLIP_JS}</script></body></html>')
