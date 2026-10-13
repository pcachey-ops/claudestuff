"""Turn a ProductSpec into a printable PDF and a square listing cover image."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from .models import Page, ProductSpec

PAGE_W, PAGE_H = letter
MARGIN = 0.75 * inch
INK = HexColor("#222222")
RULE = HexColor("#BBBBBB")


def _wrap(c: canvas.Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if c.stringWidth(trial, font, size) <= width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
    return lines


def _header(c: canvas.Canvas, page: Page, accent: Color) -> float:
    c.setFillColor(accent)
    c.rect(0, PAGE_H - 0.35 * inch, PAGE_W, 0.35 * inch, stroke=0, fill=1)
    y = PAGE_H - MARGIN - 0.2 * inch
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 22)
    for line in _wrap(c, page.heading, "Helvetica-Bold", 22, PAGE_W - 2 * MARGIN):
        c.drawString(MARGIN, y, line)
        y -= 26
    c.setFillColor(INK)
    c.setFont("Helvetica-Oblique", 10.5)
    for line in _wrap(c, page.intro, "Helvetica-Oblique", 10.5, PAGE_W - 2 * MARGIN):
        c.drawString(MARGIN, y, line)
        y -= 14
    return y - 14


def _checklist(c: canvas.Canvas, page: Page, y: float, accent: Color) -> None:
    box = 11
    gap = max(18.0, min(34.0, (y - MARGIN) / max(len(page.items), 1)))
    c.setFont("Helvetica", 11.5)
    for item in page.items:
        if y < MARGIN + box:
            break
        c.setStrokeColor(accent)
        c.setLineWidth(1.2)
        c.rect(MARGIN, y - box + 2, box, box, stroke=1, fill=0)
        c.setFillColor(INK)
        c.drawString(MARGIN + box + 10, y - box + 4, item[:95])
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.line(MARGIN + box + 10, y - box - 4, PAGE_W - MARGIN, y - box - 4)
        y -= gap


def _lined(c: canvas.Canvas, page: Page, y: float, accent: Color) -> None:
    prompts = page.items or [""]
    block = (y - MARGIN) / len(prompts)
    for prompt in prompts:
        top = y
        c.setFillColor(accent)
        c.setFont("Helvetica-Bold", 12)
        for line in _wrap(c, prompt, "Helvetica-Bold", 12, PAGE_W - 2 * MARGIN)[:2]:
            c.drawString(MARGIN, y, line)
            y -= 15
        y -= 8
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        while y > top - block + 12:
            c.line(MARGIN, y, PAGE_W - MARGIN, y)
            y -= 22
        y = top - block


def _table(c: canvas.Canvas, page: Page, y: float, accent: Color) -> None:
    cols = page.items[:6] or ["Notes"]
    width = PAGE_W - 2 * MARGIN
    col_w = width / len(cols)
    head_h, row_h = 24, 26
    c.setFillColor(accent)
    c.rect(MARGIN, y - head_h, width, head_h, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 10)
    for i, col in enumerate(cols):
        label = _wrap(c, col, "Helvetica-Bold", 10, col_w - 8)[0]
        c.drawString(MARGIN + i * col_w + 5, y - head_h + 8, label)
    top = y - head_h
    rows = int((top - MARGIN) // row_h)
    bottom = top - rows * row_h
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    for r in range(rows + 1):
        c.line(MARGIN, top - r * row_h, MARGIN + width, top - r * row_h)
    for i in range(len(cols) + 1):
        c.line(MARGIN + i * col_w, top, MARGIN + i * col_w, bottom)


LAYOUTS = {"checklist": _checklist, "lined": _lined, "table": _table}


def _footer(c: canvas.Canvas, spec: ProductSpec, number: int) -> None:
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#888888"))
    c.drawString(MARGIN, 0.45 * inch, f"{spec.cover_title}  ·  for personal use")
    c.drawRightString(PAGE_W - MARGIN, 0.45 * inch, str(number))


def render_pdf(spec: ProductSpec, path: Path) -> Path:
    accent = HexColor(spec.accent_color)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(spec.cover_title)
    c.setAuthor("Digital Product Pipeline")

    # Title page
    c.setFillColor(accent)
    c.rect(0, PAGE_H * 0.45, PAGE_W, PAGE_H * 0.55, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF"))
    y = PAGE_H * 0.78
    for line in _wrap(c, spec.cover_title, "Helvetica-Bold", 36, PAGE_W - 2 * MARGIN):
        c.setFont("Helvetica-Bold", 36)
        c.drawString(MARGIN, y, line)
        y -= 42
    c.setFont("Helvetica", 15)
    for line in _wrap(c, spec.cover_subtitle, "Helvetica", 15, PAGE_W - 2 * MARGIN):
        c.drawString(MARGIN, y - 6, line)
        y -= 20
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, PAGE_H * 0.38, "What's inside")
    c.setFont("Helvetica", 11)
    y = PAGE_H * 0.38 - 20
    for i, page in enumerate(spec.pages, start=2):
        c.drawString(MARGIN + 10, y, f"{i}.  {page.heading[:80]}")
        y -= 16
        if y < MARGIN:
            break
    c.showPage()

    for number, page in enumerate(spec.pages, start=2):
        y = _header(c, page, accent)
        LAYOUTS[page.layout](c, page, y, accent)
        _footer(c, spec, number)
        c.showPage()
    c.save()
    return path


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for base in ("/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "C:/Windows/Fonts"):
        try:
            return ImageFont.truetype(f"{base}/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_cover(spec: ProductSpec, path: Path, size: int = 2000) -> Path:
    """Square cover image (Etsy recommends 2000px) mocking up the printable on a coloured background."""
    accent = spec.accent_color
    img = Image.new("RGB", (size, size), accent)
    d = ImageDraw.Draw(img)

    # Paper sheet with a soft shadow
    sheet = (int(size * 0.18), int(size * 0.30), int(size * 0.82), int(size * 1.08))
    shadow = tuple(int(accent[i : i + 2], 16) * 7 // 10 for i in (1, 3, 5))
    d.rectangle([sheet[0] + 18, sheet[1] + 18, sheet[2] + 18, sheet[3]], fill=shadow)
    d.rectangle(sheet, fill="#FFFFFF")
    d.rectangle([sheet[0], sheet[1], sheet[2], sheet[1] + 40], fill=accent)
    line_y = sheet[1] + 110
    while line_y < size - 40:
        d.rectangle([sheet[0] + 60, line_y, sheet[0] + 90, line_y + 30], outline=accent, width=5)
        d.line([sheet[0] + 120, line_y + 30, sheet[2] - 60, line_y + 30], fill="#CCCCCC", width=4)
        line_y += 90

    title_font = _font(118, bold=True)
    y = int(size * 0.05)
    for line in textwrap.wrap(spec.cover_title.upper(), width=18)[:2]:
        w = d.textlength(line, font=title_font)
        d.text(((size - w) / 2, y), line, font=title_font, fill="#FFFFFF")
        y += 135
    sub_font = _font(56)
    sub = textwrap.shorten(spec.cover_subtitle, width=48, placeholder="…")
    w = d.textlength(sub, font=sub_font)
    d.text(((size - w) / 2, y + 10), sub, font=sub_font, fill="#FFFFFF")

    badge_font = _font(48, bold=True)
    badge = f"PRINTABLE PDF · {len(spec.pages) + 1} PAGES"
    bw = d.textlength(badge, font=badge_font)
    bx, by = (size - bw) / 2 - 40, size * 0.86
    d.rounded_rectangle([bx, by, bx + bw + 80, by + 100], radius=50, fill="#222222")
    d.text((bx + 40, by + 22), badge, font=badge_font, fill="#FFFFFF")

    img.save(path, "PNG", optimize=True)
    return path
