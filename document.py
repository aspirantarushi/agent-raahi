"""Drafts as proper documents: an on-screen page preview, a Word file (.docx) and a PDF, all from the
draft's own text (so a supervisor's edits show in every format). Plain code, no AI.

The text is read line by line into blocks:
- the "DRAFT — to be checked by a lawyer" line (and its Hindi line): bold, at the top
- a "not ready for review" list added by the checklist: an amber box
- the title (the first line, if it isn't "To,") and a "(based on ...)" line under it
- headings: short lines with no full stop, followed by a list or an indented line
- labels: "To,", "Date:", "Subject:", "Problem:" ... in bold
- numbered lines ("1. ") and bullets ("- "); indented lines belong to the line above
- the signature or thumb impression line: with space above it to sign
- after "---": notes for the volunteer (a grey box), and last the note on how the draft was prepared
  (small grey text)
[Blanks] are highlighted in light yellow; dates, amounts and urgent words are bold.
"""

import html
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import drafts
import lang

HERE = Path(__file__).resolve().parent
FONTS = HERE / "assets" / "fonts"

DRAFT_LINES = {drafts.DRAFT_HEADER, "ड्राफ़्ट — वकील से जाँच करवाना ज़रूरी है"}
DISCLOSURE_FIRST = {lang.t("disclosure.prepared_with", "en"), lang.t("disclosure.prepared_with", "hi"),
                    *drafts.DISCLOSURE_STARTS}
NOT_READY = (lang.t("ready.block_not_ready", "en", n=0).split(":")[0], lang.t("ready.block_not_ready", "hi", n=0).split(":")[0],
             lang.t("ready.block_cannot", "en").rstrip(":"), lang.t("ready.block_cannot", "hi").rstrip(":"))
TRANSLATION_LABEL = ("हिंदी अनुवाद की जाँच", "Hindi translation checked")
OPENERS = ("to,", "सेवा में,", "to:", "from:")
SIGN_WORDS = ("thumb impression", "अँगूठे", "अंगूठे", "signature of", "हस्ताक्षर")

MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
          "जनवरी|फ़रवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|सितम्बर|अक्टूबर|नवंबर|नवम्बर|दिसंबर|दिसम्बर")
IMPORTANT = re.compile(
    rf"(\b\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}\b|\b(?:{MONTHS})\s+\d{{4}}\b|₹\s?[\d,]+(?:\.\d+)?|\bRs\.?\s?[\d,]+|"
    r"\bCall (?:112|1930|15100)(?: now)?\.?|\b1930\b|\b112\b|\b15100\b|\bUrgent:|ज़रूरी:|"
    r"not a legal deadline|क़ानूनी समय-सीमा नहीं|\bdeadline\b|\babout \d+ (?:days?|weeks?|months?|years?)\b|"
    r"लगभग \d+ (?:दिन|हफ़्ते|महीने|साल))", re.I)
BLANK = re.compile(r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]")


@dataclass
class Block:
    kind: str                 # draft, notready, title, subtitle, heading, para, bullet, number, rule, sign
    text: str
    part: str = "body"        # body, notes, disclosure
    indent: int = 0
    number: str = ""
    label: str = ""           # a bold "Label:" at the start
    more: List[str] = field(default_factory=list)  # indented lines that belong to this one


def _label(text: str) -> Tuple[str, str]:
    """("Subject:", " Restoration of ...") for "Subject: Restoration of ..."; ("", text) otherwise."""
    low = text.strip().casefold()
    if low in OPENERS:
        return text.strip(), ""
    m = re.match(r"^([^:\[\]()]{2,45}?:)(\s+.*|$)", text)
    if m and "http" not in m[1] and len(m[1].split()) <= 7 and not re.search(r"['’]", m[1]):
        return m[1], m[2]
    return "", text


def parse(text: str) -> List[Block]:
    lines = (text or "").replace("\r\n", "\n").split("\n")
    # parts: the body; after "---", notes; the last part starting "Prepared with ..." is the disclosure
    parts, current = [("body", [])], None
    for line in lines:
        if line.strip() == "---":
            parts.append(("notes", []))
            continue
        parts[-1][1].append(line)
    if len(parts) > 1:
        first = next((l.strip() for l in parts[-1][1] if l.strip()), "")
        if first in DISCLOSURE_FIRST or any(first.startswith(s) for s in DISCLOSURE_FIRST):
            parts[-1] = ("disclosure", parts[-1][1])
    blocks: List[Block] = []
    for part, plines in parts:
        if blocks and part != "body":
            blocks.append(Block("rule", "", part))
        _parse_part(plines, part, blocks)
    return blocks


def _parse_part(lines: List[str], part: str, blocks: List[Block]) -> None:
    titled = part != "body"
    in_notready = False
    prev_blank = True
    nonblank = [i for i, l in enumerate(lines) if l.strip()]
    for n, raw in enumerate(lines):
        line = raw.rstrip()
        s = line.strip()
        if not s:
            prev_blank, in_notready = True, False
            continue
        nxt = next((lines[i] for i in nonblank if i > n), "")
        indent = len(line) - len(line.lstrip(" "))
        if s in DRAFT_LINES or s.startswith(TRANSLATION_LABEL):
            blocks.append(Block("draft", s, part))
        elif s.startswith(NOT_READY):
            in_notready = True
            blocks.append(Block("notready", s, part))
        elif in_notready and s.startswith("- "):
            blocks.append(Block("notready", s[2:], part, indent=1))
        elif indent >= 2 and s.startswith("- ") and blocks and blocks[-1].kind in ("bullet", "number"):
            label, rest = _label(s[2:])
            blocks.append(Block("bullet", rest, part, indent=1, label=label))
        elif indent >= 2 and blocks and blocks[-1].kind in ("bullet", "number", "para") and not prev_blank:
            blocks[-1].more.append(s)
        elif s.startswith("- ") or s.startswith("• "):
            label, rest = _label(s[2:])
            blocks.append(Block("bullet", rest, part, indent=1 if indent >= 2 else 0, label=label))
        elif re.match(r"^\d{1,2}\.\s", s):
            num, rest = s.split(" ", 1)
            label, rest = _label(rest)
            blocks.append(Block("number", rest, part, number=num, label=label))
        elif not titled and s.casefold() not in OPENERS and ":" not in s and len(s) <= 110 and not s.startswith("["):
            titled = True
            blocks.append(Block("title", s, part))
        elif blocks and blocks[-1].kind == "title" and s.startswith("(") and s.endswith(")"):
            blocks.append(Block("subtitle", s, part))
        elif any(w in s.casefold() for w in SIGN_WORDS) and len(s) <= 90:
            blocks.append(Block("sign", s, part))
        elif _is_heading(s, nxt, prev_blank):
            blocks.append(Block("heading", s.rstrip(":"), part))
        else:
            label, rest = _label(s)
            blocks.append(Block("para", rest, part, label=label))
        if blocks[-1].kind not in ("draft", "notready"):
            titled = True
        prev_blank = False


def _is_heading(s: str, nxt: str, prev_blank: bool) -> bool:
    n = nxt.strip()
    follows = n.startswith(("- ", "• ")) or bool(re.match(r"^\d{1,2}\.\s", n)) or nxt.startswith("   ") \
        or (s.endswith(":") and bool(n))
    plain = not re.search(r"[.;,!?।]$", s) and len(s) <= 80 and not s.startswith("[")
    colon_inside = ":" in s.rstrip(":")
    return prev_blank and follows and plain and not colon_inside


# ---------- inline: bold important words, highlighted blanks ----------

def runs(text: str) -> List[Tuple[str, str]]:
    """[(text, style)] with style "", "bold" or "blank"."""
    out: List[Tuple[str, str]] = []
    pos = 0
    for m in BLANK.finditer(text):
        out += _bold_runs(text[pos:m.start()])
        out.append((m.group(0), "blank"))
        pos = m.end()
    out += _bold_runs(text[pos:])
    return [r for r in out if r[0]]


def _bold_runs(text: str) -> List[Tuple[str, str]]:
    out, pos = [], 0
    for m in IMPORTANT.finditer(text):
        out += [(text[pos:m.start()], ""), (m.group(0), "bold")]
        pos = m.end()
    return out + [(text[pos:], "")]


# ---------- the page preview (HTML) ----------

def _inline_html(text: str) -> str:
    return "".join(f'<mark class="blank">{html.escape(t)}</mark>' if s == "blank" else
                   f"<b>{html.escape(t)}</b>" if s == "bold" else html.escape(t) for t, s in runs(text))


def to_html(text: str) -> str:
    """The draft as a page: an A4-like sheet with a proper title, headings and lists."""
    out, part = [], "body"
    for b in parse(text):
        if b.kind == "rule" and b.part == "notes":
            continue  # the notes box itself sets them apart
        if b.part != part:
            out.append("</div>" if part != "body" else "")
            part = b.part
            out.append(f'<div class="doc-{part}">')
        lab = f"<b>{html.escape(b.label)}</b>" if b.label else ""
        body = lab + _inline_html(b.text)
        more = "".join(f'<div class="more">{_inline_html(m)}</div>' for m in b.more)
        if b.kind == "draft":
            out.append(f'<p class="doc-draft">{html.escape(b.text)}</p>')
        elif b.kind == "notready":
            out.append(f'<p class="doc-notready{" sub" if b.indent else ""}">{_inline_html(b.text)}</p>')
        elif b.kind == "title":
            out.append(f"<h3 class=\"doc-title\">{_inline_html(b.text)}</h3>")
        elif b.kind == "subtitle":
            out.append(f'<p class="doc-subtitle">{_inline_html(b.text)}</p>')
        elif b.kind == "heading":
            out.append(f'<h4 class="doc-h">{_inline_html(b.text)}</h4>')
        elif b.kind == "rule":
            out.append('<hr class="doc-rule">')
        elif b.kind == "sign":
            out.append(f'<div class="doc-sign"><div class="space"></div><p>{body}</p></div>')
        elif b.kind == "bullet":
            out.append(f'<div class="doc-li{" sub" if b.indent else ""}"><span class="dot">•</span><div>{body}{more}</div></div>')
        elif b.kind == "number":
            out.append(f'<div class="doc-li num"><span class="dot">{html.escape(b.number)}</span><div>{body}{more}</div></div>')
        else:
            out.append(f'<p class="doc-p">{body}{more}</p>')
    if part != "body":
        out.append("</div>")
    return f'<div class="docpage">{"".join(out)}</div>'


DEVA_SAFE = set(" .,;:!?()[]-—–“”‘’'\"/₹%\n")  # punctuation the Devanagari font also has


def _scripts(text: str) -> List[Tuple[str, bool]]:
    """Split text into Devanagari and other pieces; spaces and punctuation stay with the piece before."""
    out: List[Tuple[str, bool]] = []
    for ch in text:
        deva = "\u0900" <= ch <= "\u097f" or ch in "\u200c\u200d"
        neutral = not ch.isalnum() and not deva and (ch in DEVA_SAFE or not (out and out[-1][1]))
        if out and (neutral or out[-1][1] == deva):
            out[-1] = (out[-1][0] + ch, out[-1][1])
        else:
            out.append((ch, deva))
    return out


# ---------- Word (.docx) ----------

def to_docx(text: str, title: str = "") -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_COLOR_INDEX

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)  # A4
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Noto Sans", Pt(11)
    rpr = normal.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(fonts)
    for attr, name in (("w:ascii", "Noto Sans"), ("w:hAnsi", "Noto Sans"), ("w:cs", "Nirmala UI")):
        fonts.set(qn(attr), name)
    if title:
        doc.core_properties.title = title
    grey = RGBColor(0x5B, 0x63, 0x70)

    def para(b_text, style="", size=None, color=None, bold_all=False, label="", indent=0.0, space_before=0,
             align=None, number=""):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after, pf.space_before = Pt(4), Pt(space_before)
        if indent:
            pf.left_indent, pf.first_line_indent = Cm(indent), Cm(-0.6)
        if align:
            p.alignment = align
        pieces = ([(number + "\t", "")] if number else []) + ([(label, "bold")] if label else []) + runs(b_text)
        for t, s in pieces:
            r = p.add_run(t)
            r.bold = bold_all or s == "bold"
            if s == "blank":
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
            if size:
                r.font.size = Pt(size)
                r.font.cs_size = Pt(size) if hasattr(r.font, "cs_size") else None
            if color:
                r.font.color.rgb = color
            r_fonts = r._element.get_or_add_rPr().get_or_add_rFonts()
            r_fonts.set(qn("w:cs"), "Nirmala UI")  # Hindi in Word: a Devanagari font found on Windows
            if s == "bold" or bold_all:
                r._element.rPr.append(r._element.rPr.makeelement(qn("w:bCs"), {}))
        if number:
            pf.tab_stops.add_tab_stop(Cm(indent or 0.6))
        return p

    for b in parse(text):
        small = b.part == "disclosure"
        notes = b.part == "notes"
        color = grey if (small or notes) else None
        size = 8.5 if small else 9.5 if notes else None
        if b.kind == "draft":
            para(b.text, bold_all=True, size=10, color=RGBColor(0x9A, 0x34, 0x12))
        elif b.kind == "notready":
            para(("• " if b.indent else "") + b.text, size=9.5, color=RGBColor(0x8A, 0x5A, 0x00), indent=0.6 if b.indent else 0)
        elif b.kind == "title":
            para(b.text, bold_all=True, size=15, space_before=6, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif b.kind == "subtitle":
            para(b.text, size=9.5, color=grey, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif b.kind == "heading":
            para(b.text, bold_all=True, size=12.5 if not (small or notes) else 10, space_before=8, color=color)
        elif b.kind == "rule":
            para("—" * 30, size=7, color=grey)
        elif b.kind == "sign":
            for _ in range(3):
                para("", size=8)
            para("_" * 34, color=grey)
            para(b.text, label=b.label, size=size, color=color)
        elif b.kind == "bullet":
            para(b.text, label=b.label, indent=0.6 + 0.6 * b.indent, number="•", size=size, color=color)
        elif b.kind == "number":
            para(b.text, label=b.label, indent=0.8, number=b.number, size=size, color=color)
        else:
            para(b.text, label=b.label, size=size, color=color)
        for m in b.more:
            para(m, indent=1.2 if b.kind in ("bullet", "number") else 0.6, size=size or 10, color=color)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------- PDF ----------

def to_pdf(text: str, title: str = "") -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(22, 20, 22)
    pdf.set_auto_page_break(True, margin=20)
    for style, latin, deva in (("", "NotoSans-Regular.ttf", "NotoSansDevanagari-Regular.ttf"),
                               ("B", "NotoSans-Bold.ttf", "NotoSansDevanagari-Bold.ttf")):
        pdf.add_font("Noto", style, str(FONTS / latin))
        pdf.add_font("NotoDeva", style, str(FONTS / deva))
    pdf.set_text_shaping(True)
    if title:
        pdf.set_title(title)
    pdf.set_creator("Agent Raahi")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    def write(t: str, size=11.0, bold_all=False, color=(19, 33, 59), label="", indent=0.0, bullet="",
              align="L", gap=1.6):
        """One paragraph: bold label, bold important words, underlined [blanks]; wrapped lines keep the indent."""
        h = size * 0.52
        pdf.set_text_color(*color)
        x0 = pdf.l_margin + indent
        if bullet:
            pdf.set_font("Noto", "B" if bullet[0].isdigit() else "", size)
            pdf.set_x(x0 - 5.5)
            pdf.cell(5.5, h, bullet)
        pieces = ([(label, "bold")] if label else []) + runs(t)
        segs = [(chunk, deva, "BU" if st == "blank" and bold_all else "U" if st == "blank" else
                 "B" if (st == "bold" or bold_all) else "") for x, st in (pieces or [(" ", "")]) for chunk, deva in _scripts(x)]
        if align == "C":  # centred if it fits on one line
            total = 0.0
            for chunk, deva, style in segs:
                pdf.set_font("NotoDeva" if deva else "Noto", style, size)
                total += pdf.get_string_width(chunk)
            if total < width:
                pdf.set_x(pdf.l_margin + (width - total) / 2)
                for chunk, deva, style in segs:
                    pdf.set_font("NotoDeva" if deva else "Noto", style, size)
                    pdf.write(h, chunk)
                pdf.ln(h + gap)
                return
        old = pdf.l_margin
        pdf.set_left_margin(x0)
        pdf.set_x(x0)
        right = pdf.w - pdf.r_margin
        for chunk, deva, style in segs:  # Hindi in the Devanagari font, everything else in Noto Sans
            pdf.set_font("NotoDeva" if deva else "Noto", style, size)
            first = chunk.split(" ")[0]
            if first and pdf.get_x() > x0 + 1 and pdf.get_string_width(first) > right - pdf.get_x():
                pdf.ln(h)  # a word or number is never split across two lines
                pdf.set_x(x0)
            pdf.write(h, chunk)
        pdf.set_left_margin(old)
        pdf.ln(h + gap)

    for b in parse(text):
        small = b.part == "disclosure"
        notes = b.part == "notes"
        color = (91, 99, 112) if (small or notes) else (19, 33, 59)
        size = 8.5 if small else 9.5 if notes else 11.0
        if b.kind == "draft":
            write(b.text, 10, True, (154, 52, 18))
        elif b.kind == "notready":
            write(b.text, 9.5, False, (138, 90, 0), indent=6 if b.indent else 0, bullet="•" if b.indent else "")
        elif b.kind == "title":
            pdf.ln(2)
            write(b.text, 15, True, align="C")
        elif b.kind == "subtitle":
            write(b.text, 9.5, False, (91, 99, 112), align="C")
        elif b.kind == "heading":
            pdf.ln(2.5)
            write(b.text, 12.5 if not (small or notes) else 10, True, color)
        elif b.kind == "rule":
            pdf.ln(2)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
        elif b.kind == "sign":
            pdf.ln(14)  # room to sign or put a thumb impression
            if "___" not in b.text:  # the line itself already has a place to sign
                pdf.set_draw_color(120, 120, 120)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 70, pdf.get_y())
                pdf.ln(1.5)
            write(b.text, size, False, color, label=b.label)
        elif b.kind == "bullet":
            write(b.text, size, False, color, label=b.label, indent=6 + 5 * b.indent, bullet="•")
        elif b.kind == "number":
            write(b.text, size, False, color, label=b.label, indent=7, bullet=b.number)
        else:
            write(b.text, size, False, color, label=b.label)
        for m in b.more:
            write(m, size if (small or notes) else 10, False, color, indent=12 if b.kind != "para" else 6)
    return bytes(pdf.output())
