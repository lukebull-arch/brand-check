#!/usr/bin/env python3
"""GEEIQ brand check PDF renderer.

Takes a payload dict (or JSON file) and renders the one-page A4 report:
bespoke top half, standing Virtual Worlds content on the amethyst band.
Layout matches the approved KFC sample.

Payload shape:
{
  "brand": "KFC",
  "snapshot": "July 2026",
  "headline": "one sentence",
  "stats": [{"num": "687", "label": "...", "coral": true}, ...],   # 4-6
  "reading": "two to four sentences of analyst reading"
}
"""
import json
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

PURPLE = HexColor("#7C68FB")
AMETHYST = HexColor("#2E204D")
OFFWHITE = HexColor("#FAF7F2")
CORAL = HexColor("#FC4F3F")
WHITE = HexColor("#FFFFFF")
TINT = HexColor("#EEEDFE")
MUTED = HexColor("#5B5170")
LABEL_LIGHT = HexColor("#C9C0E6")

STANDING_BODY = (
    "Virtual worlds are creator-led economies. Players build experiences, items "
    "and communities around the brands they love, with or without permission. "
    "Attention that brands used to buy on other channels now lives inside Roblox, "
    "Fortnite and their peers, and players pay it willingly. Brands are committing: "
    "activity is maturing from one-off experiments into always-on presence.")
STANDING_BAND = [
    ("1,011", "new brand activations tracked in 2025"),
    ("1.8", "average activations per active brand in 2025, the highest on record"),
    ("88%", "of 2025 activity on Roblox and Fortnite"),
    ("8 years", "of GEEIQ tracking"),
]
STANDING_CLOSING = (
    "This check is a snapshot. The full picture, how brands enter virtual "
    "worlds and where most get it wrong, is in Brands in Gaming 101: Virtual Worlds.")
STANDING_LINKS = "geeiq.com/resources/reports/virtual-worlds-101   ·   geeiq.com/demo"


def _register_fonts():
    pdfmetrics.registerFont(TTFont("Jakarta", f"{ASSETS}/fonts/Plus_Jakarta_Sans_wght_600.ttf"))
    pdfmetrics.registerFont(TTFont("JakartaBold", f"{ASSETS}/fonts/Plus_Jakarta_Sans_wght_700.ttf"))
    pdfmetrics.registerFont(TTFont("Figtree", f"{ASSETS}/fonts/Figtree_wght_400.ttf"))
    pdfmetrics.registerFont(TTFont("FigtreeSemi", f"{ASSETS}/fonts/Figtree_wght_600.ttf"))


def render(payload, out_path):
    _register_fonts()
    W, H = A4
    M = 42
    c = canvas.Canvas(out_path, pagesize=A4)

    def wrap(text, font, size, max_w):
        words, lines, cur = text.split(), [], ""
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if pdfmetrics.stringWidth(trial, font, size) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w_
        if cur:
            lines.append(cur)
        return lines

    def draw_wrapped(text, x, y, font, size, color, max_w, leading=None):
        leading = leading or size * 1.45
        c.setFont(font, size)
        c.setFillColor(color)
        lines = wrap(text, font, size, max_w)
        for i, line in enumerate(lines):
            c.drawString(x, y - i * leading, line)
        return y - (len(lines) - 1) * leading

    # background
    c.setFillColor(OFFWHITE)
    c.rect(0, 0, W, H, stroke=0, fill=1)

    # header
    logo_h = 16
    logo_w = logo_h * (867 / 173)
    c.drawImage(f"{ASSETS}/logo-color.png", M, H - M - logo_h, width=logo_w,
                height=logo_h, mask="auto", preserveAspectRatio=True)
    c.setFont("Figtree", 9)
    c.setFillColor(MUTED)
    c.drawRightString(W - M, H - M - logo_h + 3, f"Snapshot: {payload['snapshot']}")

    # title + headline
    y = H - M - 74
    c.setFont("JakartaBold", 27)
    c.setFillColor(AMETHYST)
    c.drawString(M, y, f"Brand check: {payload['brand']}")
    y -= 36
    y = draw_wrapped(payload["headline"], M, y, "Jakarta", 13, AMETHYST, W - 2 * M)

    # stat grid (3 per row, up to 6)
    stats = payload["stats"][:6]
    grid_top = y - 32
    card_gap = 10
    card_w = (W - 2 * M - 2 * card_gap) / 3
    card_h = 86
    n_rows = (len(stats) + 2) // 3
    for i, s in enumerate(stats):
        col, row = i % 3, i // 3
        cx = M + col * (card_w + card_gap)
        cy = grid_top - card_h - row * (card_h + card_gap)
        c.setFillColor(WHITE)
        c.roundRect(cx, cy, card_w, card_h, 9, stroke=0, fill=1)
        c.setFont("JakartaBold", 21)
        c.setFillColor(CORAL if s.get("coral") else AMETHYST)
        c.drawString(cx + 14, cy + card_h - 34, str(s["num"]))
        c.setFont("Figtree", 8.3)
        c.setFillColor(MUTED)
        for j, line in enumerate(wrap(s["label"], "Figtree", 8.3, card_w - 24)):
            c.drawString(cx + 14, cy + card_h - 50 - j * 11, line)

    # analyst reading
    y = grid_top - n_rows * card_h - (n_rows - 1) * card_gap - 34
    y = draw_wrapped(payload["reading"], M, y, "Figtree", 10, MUTED, W - 2 * M, leading=16)

    # standing content panel, sized to its content
    panel_top = y - 32
    pw = W - 2 * M - 28
    body_lines = len(wrap(STANDING_BODY, "Figtree", 9.5, pw))
    closing_lines = len(wrap(STANDING_CLOSING, "FigtreeSemi", 9.5, pw))
    content_h = (42 + 24 + (body_lines - 1) * 14 + 32 + 13 + 3 * 10
                 + 36 + (closing_lines - 1) * 14 + 20 + 32)
    panel_bot = panel_top - content_h
    c.setFillColor(AMETHYST)
    c.roundRect(M - 10, panel_bot, W - 2 * M + 20, panel_top - panel_bot, 14,
                stroke=0, fill=1)

    px = M + 14
    py = panel_top - 42
    c.setFont("JakartaBold", 16)
    c.setFillColor(WHITE)
    c.drawString(px, py, "Virtual worlds, in one page")
    py -= 24
    py = draw_wrapped(STANDING_BODY, px, py, "Figtree", 9.5, LABEL_LIGHT, pw, leading=14)

    band_top = py - 32
    bw = pw / 4
    for i, (num, label) in enumerate(STANDING_BAND):
        bx = px + i * bw
        c.setFont("JakartaBold", 17)
        c.setFillColor(WHITE)
        c.drawString(bx, band_top, num)
        c.setFont("Figtree", 7.6)
        c.setFillColor(LABEL_LIGHT)
        for j, line in enumerate(wrap(label, "Figtree", 7.6, bw - 14)):
            c.drawString(bx, band_top - 13 - j * 10, line)

    cy2 = band_top - 68
    cy2 = draw_wrapped(STANDING_CLOSING, px, cy2, "FigtreeSemi", 9.5, WHITE, pw, leading=14)
    cy2 -= 20
    c.setFont("FigtreeSemi", 9)
    c.setFillColor(TINT)
    c.drawString(px, cy2, STANDING_LINKS)

    wl_h = 12
    wl_w = wl_h * (867 / 173)
    c.drawImage(f"{ASSETS}/logo-white.png", W - M - 24 - wl_w, cy2 - 3,
                width=wl_w, height=wl_h, mask="auto", preserveAspectRatio=True)

    c.setFont("Figtree", 7.8)
    c.setFillColor(MUTED)
    c.drawString(M, panel_bot - 18,
                 f"Built by a GEEIQ analyst. Data: GEEIQ platform and public sources, {payload['snapshot']}.")

    c.save()
    return out_path


if __name__ == "__main__":
    payload = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else "report.pdf"
    print(render(payload, out))
