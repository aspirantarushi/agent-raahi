"""Small building blocks for the look and feel: header, helplines, step progress, status chips.

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


def helpline_links(danger: str, aid: str) -> str:
    """The two tap-to-call helplines, each with its own icon (the Home page style, used on every screen)."""
    return (f'<p class="lines">'
            f'<a class="danger" href="tel:112">{icon("call")}<span>{html.escape(danger)}</span></a>'
            f'<a href="tel:15100">{icon("support_agent")}<span>{html.escape(aid)}</span></a></p>')


def new_case_side(camp_label: str, camp_text: str, camp_on: bool, tip: str) -> str:
    """Beside the New case card on a laptop: today's camp (or "No camp started") and one short tip."""
    return (f'<div class="nc-side"><p class="nc-camp{" on" if camp_on else ""}">{icon("holiday_village")}'
            f'<span><b>{html.escape(camp_label)}</b> {html.escape(camp_text)}</span></p>'
            f'<p class="nc-tip">{icon("lightbulb")}<span>{html.escape(tip)}</span></p></div>')


def signin_side(title: str, points, help_title: str, danger: str, aid: str) -> str:
    """Beside a sign-in form (below it on a phone): what the page is for, then the two helplines."""
    items = "".join(f"<li>{html.escape(p)}</li>" for p in points)
    return (f'<div class="signin-side"><h3>{html.escape(title)}</h3><ul>{items}</ul>'
            f'<h4>{html.escape(help_title)}</h4>'
            f'<nav class="helpline helpline-page" aria-label="Emergency and helplines">'
            f'{helpline_links(danger, aid)}</nav></div>')


def page_helplines(danger: str, aid: str) -> str:
    """The helplines under a page heading (New case, Case tracker, Supervisor, sign-in pages...)."""
    return (f'<nav class="helpline helpline-page" aria-label="Emergency and helplines">'
            f'{helpline_links(danger, aid)}</nav>')


def stepper(steps: List[str], current: int, step_word: str = "") -> str:
    """Step progress, "1. Tell the story" -> "2. Questions" -> ... on one line each (current is 1-based)."""
    items = []
    for i, label in enumerate(steps, 1):
        state = "done" if i < current else "now" if i == current else ""
        aria = ' aria-current="step"' if i == current else ""
        items.append(f'<li class="{state}"{aria}>{i}. {html.escape(label)}</li>')
    now = steps[current - 1] if 1 <= current <= len(steps) else ""
    phone = (f'<p class="stepper-phone" aria-hidden="true"><b>{html.escape(step_word.format(n=current, total=len(steps)))}</b>'
             f' \u00b7 {html.escape(now)}</p>') if step_word else ""
    return f'<ol class="stepper" aria-label="Progress">{"".join(items)}</ol>{phone}'


def step_band(n: int, text: str, state: str, state_text: str) -> str:
    """A step's header band: a numbered circle (a tick once done), the step's name and its state (Now / Done /
    Not yet). state: "now", "done" or "next"."""
    num = icon("check") if state == "done" else str(n)
    tick = (" " + icon("check")) if state == "done" else ""
    return (f'<div class="step-band {html.escape(state)}"><span class="step-num">{num}</span>'
            f'<span class="step-name">{html.escape(text)}</span>'
            f'<span class="step-state">{html.escape(state_text)}{tick}</span></div>')


def step_heading(icon_name: str, text: str) -> str:
    """A centred section heading with its outlined icon above it ("Tell the story", "What kind of case is it?")."""
    return (f'<div class="step-title center"><span class="mi step-icon" aria-hidden="true">{html.escape(icon_name)}</span>'
            f'<div>{html.escape(text)}</div></div>')


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
    return f'<div class="helpline">' + (f'<p>{html.escape(free)}</p>' if free else "") + f'{helpline_links(danger, aid)}</div>'


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
    """Today (a case in many places) beside With Agent Raahi: five short rows, each an outlined icon,
    a bold first phrase and the rest of the line. raahi["rows"]: [(icon name, bold phrase, rest)]."""
    e = html.escape
    chips = "".join(f"<span>{e(c)}</span>" for c in today["chips"])
    rows = "".join(f'<li>{icon(name)}<span><b>{e(bold)}</b> {e(rest)}</span></li>' for name, bold, rest in raahi["rows"])
    return (f'<section class="sec" id="what-changes"><div class="compare">'
            f'<div class="today">{eyebrow(today["eyebrow"])}<h3>{e(today["title"])}</h3>'
            f'<div class="chips">{chips}</div><p>{e(today["text"])}</p></div>'
            f'<div class="raahi">{eyebrow(raahi["eyebrow"])}<h3>{e(raahi["title"])}</h3>'
            f'<ul class="features">{rows}</ul></div></div></section>')


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


FACTS_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; background: #13213B; color: #F8F6F1; overflow: hidden;
  font-family: "Noto Sans", "Noto Sans Devanagari", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.band { max-width: 1168px; margin: 0 auto; padding: 44px 24px 28px; height: 100vh; display: flex; flex-direction: column; }
.eyebrow { display: flex; align-items: center; gap: 10px; margin: 0 0 18px; font-size: 13px; font-weight: 600;
  letter-spacing: .16em; text-transform: uppercase; color: #C9CFDA; }
.eyebrow.dev { letter-spacing: 0; font-size: 15px; }
.eyebrow svg { flex: 0 0 auto; }
.track { flex: 1 1 auto; display: flex; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none;
  outline: none; }
.track::-webkit-scrollbar { display: none; }
.slide { flex: 0 0 100%; scroll-snap-align: start; display: flex; flex-direction: column; justify-content: center;
  gap: 14px; padding: 0 8px 0 2px; overflow: hidden; }
.slide p { margin: 0; }
.fact { font-size: 28px; line-height: 1.35; font-weight: 500; color: #FFFFFF; max-width: 900px; letter-spacing: -.01em; }
.src { font-size: 15px; line-height: 1.5; color: #C9CFDA; }
.src a { color: #FFFFFF; text-decoration: underline; text-underline-offset: 3px; }
.controls { display: flex; align-items: center; gap: 10px; margin-top: 18px; }
.controls button { appearance: none; border: 1px solid rgba(255,255,255,.35); background: transparent; color: #FFFFFF;
  width: 44px; height: 44px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; padding: 0; }
.controls button:hover { background: rgba(255,255,255,.12); }
.controls button:focus-visible, .track:focus-visible, a:focus-visible { outline: 3px solid #5FD3BF; outline-offset: 2px; }
.dots { display: flex; gap: 2px; flex-wrap: wrap; }
.dots button { width: 28px; height: 44px; border: 0; background: transparent; }
.dots button::after { content: ""; width: 10px; height: 10px; border-radius: 999px; background: rgba(255,255,255,.35); }
.dots button[aria-current="true"]::after { background: #FFFFFF; width: 22px; }
.count { margin-left: auto; font-size: 14px; color: #C9CFDA; }
.pause[hidden] { display: none; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 640px) {
  .band { padding: 32px 16px 16px; }
  .fact { font-size: 19px; line-height: 1.45; }
  .src { font-size: 13.5px; }
  .dots { flex-wrap: nowrap; gap: 0; }
  .dots button { width: 18px; }
  .dots button[aria-current="true"]::after { width: 16px; }
  .controls { gap: 6px; }
  .count { display: none; }
  .pause { margin-left: auto; }
}
@media (prefers-reduced-motion: reduce) { .track { scroll-behavior: auto; } }
"""

FACTS_JS = """
(function () {
  const track = document.getElementById('track');
  const slides = Array.from(track.children);
  const dots = Array.from(document.querySelectorAll('.dots button'));
  const count = document.getElementById('count');
  const pauseBtn = document.getElementById('pause');
  const L = JSON.parse(document.getElementById('labels').textContent);
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const N = slides.length;
  let i = 0, userPaused = false, hover = false, focused = false, touchedAt = 0;

  function show(n, smooth) {
    i = (n + N) % N;
    track.scrollTo({ left: i * track.clientWidth, behavior: smooth && !reduce ? 'smooth' : 'auto' });
    update();
  }
  function update() {
    dots.forEach(function (d, k) { d.setAttribute('aria-current', k === i ? 'true' : 'false'); });
    slides.forEach(function (s, k) { s.setAttribute('aria-hidden', k === i ? 'false' : 'true');
      s.querySelectorAll('a').forEach(function (a) { a.tabIndex = k === i ? 0 : -1; }); });
    count.textContent = L.of.replace('{n}', i + 1).replace('{total}', N);
  }
  function userMove(n) { track.setAttribute('aria-live', 'polite'); show(n, true); }
  document.getElementById('prev').addEventListener('click', function () { userMove(i - 1); });
  document.getElementById('next').addEventListener('click', function () { userMove(i + 1); });
  dots.forEach(function (d, k) { d.addEventListener('click', function () { userMove(k); }); });
  let t;
  track.addEventListener('scroll', function () {  // swipes on phones
    clearTimeout(t);
    t = setTimeout(function () { const n = Math.round(track.scrollLeft / track.clientWidth); if (n !== i) { i = n; update(); } }, 80);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') userMove(i + 1);
    if (e.key === 'ArrowLeft') userMove(i - 1);
  });
  document.body.addEventListener('mouseenter', function () { hover = true; });
  document.body.addEventListener('mouseleave', function () { hover = false; });
  document.addEventListener('focusin', function (e) {  // keyboard focus pauses; a mouse click on an arrow does not
    focused = !!(e.target.matches && e.target.matches(':focus-visible'));
  });
  document.addEventListener('focusout', function () { focused = false; });
  window.addEventListener('blur', function () { focused = false; hover = false; });
  document.addEventListener('touchstart', function () { touchedAt = Date.now(); }, { passive: true });
  function setPaused(p) {
    userPaused = p;
    pauseBtn.setAttribute('aria-label', p ? L.play : L.pause);
    pauseBtn.innerHTML = p ? PLAY : PAUSE;
  }
  pauseBtn.addEventListener('click', function () { setPaused(!userPaused); });
  if (reduce) { pauseBtn.hidden = true; }  // no automatic movement at all
  else {
    setInterval(function () {
      if (userPaused || hover || focused || Date.now() - touchedAt < 15000 || document.hidden) return;
      track.setAttribute('aria-live', 'off');
      show(i + 1, true);
    }, 7000);
  }
  window.addEventListener('resize', function () { show(i, false); });
  update();
})();
"""

_SVG = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' \
       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICON_PREV = _SVG.format('<path d="M15 6l-6 6 6 6"/>')
ICON_NEXT = _SVG.format('<path d="M9 6l6 6-6 6"/>')
ICON_PAUSE = _SVG.format('<path d="M9 6v12M15 6v12"/>')
ICON_PLAY = _SVG.format('<path d="M8 5.5v13l11-6.5z"/>')


def facts_carousel(title: str, facts, labels: dict) -> str:
    """The facts band as a small page (for components.html): one fact at a time, arrows, dots, swipe,
    auto-advance every 7 seconds, paused on hover, tap or focus, and never moving by itself when the
    device asks for reduced motion. facts: [(text, Source, Link)]. labels: prev, next, pause, play,
    of ("{n} of {total}"), source ("Source:"), region."""
    import json
    e = html.escape
    slides = "".join(
        f'<div class="slide" role="group" aria-roledescription="slide" '
        f'aria-label="{e(labels["of"].replace("{n}", str(n)).replace("{total}", str(len(facts))))}">'
        f'<p class="fact">{e(text)}</p><p class="src"><em>{source_link(source, link).replace("Source:", e(labels["source"]), 1)}'
        f'</em></p></div>' for n, (text, source, link) in enumerate(facts, 1))
    dots = "".join(f'<button type="button" aria-label="{e(labels["of"].replace("{n}", str(n)).replace("{total}", str(len(facts))))}">'
                   f'</button>' for n in range(1, len(facts) + 1))
    head = eyebrow(title).replace('">', f'">{logo_on_dark(28)}', 1)
    data = json.dumps({k: labels[k] for k in ("of", "pause", "play")}, ensure_ascii=False).replace("</", "<\\/")
    script = FACTS_JS.replace("PLAY : PAUSE", f"{json.dumps(ICON_PLAY)} : {json.dumps(ICON_PAUSE)}")
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, '
            f'initial-scale=1"><style>{FACTS_CSS}</style></head><body>'
            f'<section class="band" id="facts" aria-roledescription="carousel" aria-label="{e(labels["region"])}">{head}'
            f'<div class="track" id="track" tabindex="0" aria-live="off">{slides}</div>'
            f'<div class="controls"><button type="button" id="prev" aria-label="{e(labels["prev"])}">{ICON_PREV}</button>'
            f'<div class="dots">{dots}</div>'
            f'<button type="button" id="next" aria-label="{e(labels["next"])}">{ICON_NEXT}</button>'
            f'<span class="count" id="count" aria-hidden="true"></span>'
            f'<button type="button" class="pause" id="pause" aria-label="{e(labels["pause"])}">{ICON_PAUSE}</button></div>'
            f'</section><script type="application/json" id="labels">{data}</script><script>{script}</script></body></html>')


PRIVACY_URL = "https://github.com/aspirantarushi/agent-raahi/blob/main/docs/PRIVACY.md"


def footer(name: str, parts, privacy: str) -> str:
    """One short centred line: the name, open source, built on AgentFoundry, and Privacy (the privacy
    page on GitHub, opening in a new tab)."""
    items = [f"<b>{wordmark(name)}</b>", *[html.escape(p) for p in parts],
             f'<a href="{PRIVACY_URL}" target="_blank" rel="noopener noreferrer">{html.escape(privacy)}</a>']
    return '<footer class="footer">' + " \u00b7 ".join(f'<span class="fi">{i}</span>' for i in items) + "</footer>"


def guide_card(name: str, title: str, text: str, tag: str = "") -> str:
    """A Learn card: topic icon above the title and a line about it (like the safety cards); tag: for
    example "Coming soon", for a guide not shown yet."""
    badge = f'<span class="soon">{html.escape(tag)}</span>' if tag else ""
    return (f'<div class="card guide{" soon-card" if tag else ""}">{icon(name)}{badge}<h3>{html.escape(title)}</h3>'
            f'<p>{html.escape(text)}</p></div>')


KEY_SPAN = re.compile(r'^<span class="k">(.*?)</span>(.*)$', re.S)


def _row(r: str) -> str:
    """A "label: value" row as two columns (a grey label, then the value), so they never run together;
    the colon is kept for copied text and screen readers."""
    m = KEY_SPAN.match(r)
    if not m:
        return f'<div class="row">{r}</div>'
    return (f'<div class="row kv"><span class="k">{m[1]}<span class="sep">:</span></span>'
            f'<span class="v">{m[2]}</span></div>')


def info_card(title: str, rows: List[str], kind: str = "", icon_name: str = "") -> str:
    """A step-3 card: a heading and rows (each row already safe HTML)."""
    head = (icon(icon_name) if icon_name else "") + f"<h4>{html.escape(title)}</h4>"
    body = "".join(_row(r) for r in rows)
    return f'<div class="infocard {html.escape(kind)}"><div class="head">{head}</div>{body}</div>'


def letter_html(text: str) -> str:
    """A draft letter shown as a readable page (not typewriter text); line breaks kept."""
    lines = "<br>".join(html.escape(line) if line.strip() else "&nbsp;" for line in text.strip().split("\n"))
    return f'<div class="letter">{lines}</div>'


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
