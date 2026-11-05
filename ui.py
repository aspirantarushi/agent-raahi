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
