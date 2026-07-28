#!/usr/bin/env python3
"""GEEIQ brand check PDF renderer.

Two A4 pages:
  1. The brand's footprint — hero figure, supporting stats, cross-platform
     chart, named findings, analyst reading. Everything here is specific to
     this brand and traceable to collected data.
  2. Virtual worlds, in one page — the standing explainer, verified GEEIQ
     figures, and the call to action.

Payload:
{
  "brand": "KFC",
  "snapshot": "July 2026",
  "headline": "one sentence",
  "stats": [{"num", "label", "coral": bool}, ...],   # first coral = hero
  "reading": "analyst paragraphs",
  "top_games_named":  [{"name", "visits", "like_pct", "creator"}],
  "top_items_named":  [{"name", "favorites", "creator", "price"}],
  "platform_views":   [{"platform", "views", "videos", "top_video"}],
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
RULE = HexColor("#E6E1D8")

W, H = A4
M = 44                      # page margin
LOGO_RATIO = 867 / 173      # brand logo aspect

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
HOW_IT_WORKS = [
    ("Creator-made first",
     "Most brands appear in virtual worlds before they arrive. Players build the "
     "items, shops and roleplay worlds themselves, and that activity sets the "
     "reference point for how the brand is understood in-platform."),
    ("Presence, then permanence",
     "The brands seeing compounding returns treat virtual worlds as an always-on "
     "channel rather than a campaign. One-off activations spike and fade; "
     "sustained presence accrues an audience."),
    ("Measure what players do",
     "Visits, repeat play and item ownership say more than impressions. The "
     "platforms expose real behavioural data, so performance can be judged on "
     "engagement rather than reach alone."),
]
CLOSING = ("This check is a snapshot of what we could see from public platform data. "
           "The full picture, how brands enter virtual worlds and where most get it "
           "wrong, is in Brands in Gaming 101: Virtual Worlds.")
LINKS = "geeiq.com/resources/reports/virtual-worlds-101   ·   geeiq.com/demo"


def safe_text(text):
    """Drop characters the brand fonts have no glyph for (emoji, CJK).
    Item names on Roblox are full of them and they render as tofu boxes."""
    keep = []
    for ch in str(text or ""):
        if ord(ch) < 0x250 or ch in "\u2018\u2019\u201c\u201d\u2013\u2014\u2026&":
            keep.append(ch)
    out = "".join(keep).strip()
    while "  " in out:
        out = out.replace("  ", " ")
    return out or "Untitled"


def _register_fonts():
    pdfmetrics.registerFont(TTFont("Jakarta", f"{ASSETS}/fonts/Plus_Jakarta_Sans_wght_600.ttf"))
    pdfmetrics.registerFont(TTFont("JakartaBold", f"{ASSETS}/fonts/Plus_Jakarta_Sans_wght_700.ttf"))
    pdfmetrics.registerFont(TTFont("Figtree", f"{ASSETS}/fonts/Figtree_wght_400.ttf"))
    pdfmetrics.registerFont(TTFont("FigtreeSemi", f"{ASSETS}/fonts/Figtree_wght_600.ttf"))


def render(payload, out_path):
    _register_fonts()
    c = canvas.Canvas(out_path, pagesize=A4)

    # ---------- small helpers ----------
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
        leading = leading or size * 1.5
        c.setFont(font, size)
        c.setFillColor(color)
        lines = wrap(text, font, size, max_w)
        for i, line in enumerate(lines):
            c.drawString(x, y - i * leading, line)
        return y - (len(lines) - 1) * leading

    def ellipsize(text, font, size, max_w):
        if pdfmetrics.stringWidth(text, font, size) <= max_w:
            return text
        while text and pdfmetrics.stringWidth(text + "…", font, size) > max_w:
            text = text[:-1]
        return text.rstrip() + "…"

    def page_background():
        c.setFillColor(OFFWHITE)
        c.rect(0, 0, W, H, stroke=0, fill=1)

    def header(right_text):
        logo_h = 15
        c.drawImage(f"{ASSETS}/logo-color.png", M, H - M - logo_h,
                    width=logo_h * LOGO_RATIO, height=logo_h,
                    mask="auto", preserveAspectRatio=True)
        c.setFont("Figtree", 8.5)
        c.setFillColor(MUTED)
        c.drawRightString(W - M, H - M - logo_h + 3, right_text)

    def footer(text):
        c.setFont("Figtree", 7.5)
        c.setFillColor(MUTED)
        c.drawString(M, 34, text)

    def section_label(text, x, y):
        c.setFont("FigtreeSemi", 8)
        c.setFillColor(PURPLE)
        c.drawString(x, y, text.upper())
        return y - 16

    # ================= PAGE 1: the brand's footprint =================
    page_background()
    header(f"Snapshot: {payload['snapshot']}")

    y = H - M - 62
    c.setFont("JakartaBold", 26)
    c.setFillColor(AMETHYST)
    c.drawString(M, y, f"Brand check: {payload['brand']}")

    y -= 30
    y = draw_wrapped(payload["headline"], M, y, "Jakarta", 12.5, AMETHYST,
                     W - 2 * M, leading=18)

    # ---- hero figure + supporting stats ----
    stats = payload.get("stats", [])
    hero = next((s for s in stats if s.get("coral")), stats[0] if stats else None)
    others = [s for s in stats if s is not hero][:5]

    y -= 30
    if hero:
        hero_h = 78
        card_top = y
        c.setFillColor(WHITE)
        c.roundRect(M, card_top - hero_h, W - 2 * M, hero_h, 12, stroke=0, fill=1)
        c.setFillColor(CORAL)
        c.rect(M, card_top - hero_h, 4, hero_h, stroke=0, fill=1)
        c.setFont("JakartaBold", 40)
        c.setFillColor(CORAL)
        c.drawString(M + 24, card_top - 50, str(hero["num"]))
        num_w = pdfmetrics.stringWidth(str(hero["num"]), "JakartaBold", 40)
        c.setFont("Figtree", 10.5)
        c.setFillColor(MUTED)
        for i, line in enumerate(wrap(hero["label"], "Figtree", 10.5,
                                     W - 2 * M - num_w - 60)):
            c.drawString(M + 24 + num_w + 20, card_top - 42 - i * 14, line)
        y = card_top - hero_h - 12

    if others:
        cols = min(3, len(others))
        gap = 10
        cw = (W - 2 * M - (cols - 1) * gap) / cols
        ch = 74
        for i, s in enumerate(others):
            col, row = i % cols, i // cols
            cx = M + col * (cw + gap)
            cy = y - ch - row * (ch + gap)
            c.setFillColor(WHITE)
            c.roundRect(cx, cy, cw, ch, 10, stroke=0, fill=1)
            c.setFont("JakartaBold", 19)
            c.setFillColor(AMETHYST)
            c.drawString(cx + 14, cy + ch - 30, str(s["num"]))
            c.setFont("Figtree", 8)
            c.setFillColor(MUTED)
            for j, line in enumerate(wrap(s["label"], "Figtree", 8, cw - 26)):
                c.drawString(cx + 14, cy + ch - 45 - j * 10.5, line)
        rows = (len(others) + cols - 1) // cols
        y = y - rows * ch - (rows - 1) * gap - 26

    # ---- analyst reading ----
    y = section_label("What this means", M, y)
    y = draw_wrapped(payload["reading"], M, y, "Figtree", 9.8, MUTED,
                     W - 2 * M, leading=15.5)
    y -= 30

    # ---- named findings and platform chart, side by side ----
    col_w = (W - 2 * M - 26) / 2
    left_x, right_x = M, M + col_w + 26
    block_top = y

    def exact_or_short(n):
        n = int(n or 0)
        return f"{n:,}" if n < 100_000 else _short(n)

    findings = []
    for g in payload.get("top_games_named", [])[:4]:
        findings.append((safe_text(g["name"]), f"{_short(g['visits'])} visits"))
    for it in payload.get("top_items_named", [])[:2]:
        if len(findings) >= 6:
            break
        findings.append((safe_text(it["name"]),
                         f"{exact_or_short(it['favorites'])} favourites"))

    if findings:
        ly = section_label("What we found", left_x, block_top)
        c.setFillColor(WHITE)
        rows_h = 15 + len(findings) * 22
        c.roundRect(left_x, ly - rows_h + 8, col_w, rows_h, 10, stroke=0, fill=1)
        ry = ly - 8
        for i, (name, metric) in enumerate(findings):
            if i:
                c.setStrokeColor(RULE)
                c.setLineWidth(0.6)
                c.line(left_x + 12, ry + 13, left_x + col_w - 12, ry + 13)
            c.setFont("FigtreeSemi", 8.6)
            c.setFillColor(AMETHYST)
            c.drawString(left_x + 12, ry,
                         ellipsize(name, "FigtreeSemi", 8.6, col_w - 24))
            c.setFont("Figtree", 8)
            c.setFillColor(MUTED)
            c.drawString(left_x + 12, ry - 10, metric)
            ry -= 22
        left_bottom = ly - rows_h + 8
    else:
        left_bottom = block_top

    platforms = payload.get("platform_views", [])
    if platforms:
        py_ = section_label("Where the conversation is", right_x, block_top)
        c.setFillColor(WHITE)
        chart_h = 46 + len(platforms) * 30
        c.roundRect(right_x, py_ - chart_h + 8, col_w, chart_h, 10, stroke=0, fill=1)
        top_val = max(p["views"] for p in platforms) or 1
        bar_x = right_x + 14
        bar_max = col_w - 28
        by = py_ - 6
        for p in platforms:
            c.setFont("FigtreeSemi", 8.4)
            c.setFillColor(AMETHYST)
            c.drawString(bar_x, by, p["platform"])
            c.setFont("Figtree", 8.4)
            c.setFillColor(MUTED)
            c.drawRightString(right_x + col_w - 14, by, f"{_short(p['views'])} views")
            bar_w = max(3, bar_max * p["views"] / top_val)
            c.setFillColor(TINT)
            c.roundRect(bar_x, by - 15, bar_max, 6, 3, stroke=0, fill=1)
            c.setFillColor(PURPLE)
            c.roundRect(bar_x, by - 15, bar_w, 6, 3, stroke=0, fill=1)
            by -= 30
        top_v = next((p.get("top_video") for p in platforms if p.get("top_video")), "")
        if top_v:
            c.setFont("Figtree", 7.4)
            c.setFillColor(MUTED)
            label = "Most viewed: " + safe_text(top_v)
            for i, line in enumerate(wrap(label, "Figtree", 7.4, col_w - 28)[:2]):
                c.drawString(bar_x, by - 2 + 10 - i * 10, line)
        right_bottom = py_ - chart_h + 8
    else:
        py_ = section_label("Where the conversation is", right_x, block_top)
        c.setFillColor(WHITE)
        c.roundRect(right_x, py_ - 66, col_w, 74, 10, stroke=0, fill=1)
        draw_wrapped(
            f"No YouTube gaming videos matched {payload['brand']} in the searches "
            "we ran. That absence is itself a signal: the conversation has not "
            "started on video yet.",
            right_x + 14, py_ - 6, "Figtree", 8.4, MUTED, col_w - 28, leading=12.5)
        right_bottom = py_ - 66

    # ---- coverage: what was searched and what matched ----
    cov = payload.get("coverage") or {}
    y = min(left_bottom, right_bottom) - 30
    y = section_label("What we searched", M, y)
    lines = []
    if cov.get("items_scanned"):
        lines.append(f"Roblox marketplace: {cov['items_scanned']} results scanned, "
                     f"{cov.get('items_matched', 0)} matched to {payload['brand']}.")
    if cov.get("games_scanned"):
        lines.append(f"Roblox experience search: {cov['games_scanned']} results scanned, "
                     f"{cov.get('games_matched', 0)} matched.")
    if cov.get("videos_scanned"):
        plats = ", ".join(cov.get("platforms") or [])
        lines.append(f"YouTube: {cov['videos_scanned']} videos across "
                     f"{payload['brand']} searches on {plats}.")
    else:
        lines.append("YouTube: no matching gaming videos found in the searches we ran.")
    lines.append("Everything above comes from public platform data at the snapshot date. "
                 "Creator-made content is player-made and unaffiliated with the brand.")
    y = draw_wrapped(" ".join(lines), M, y, "Figtree", 8, MUTED,
                     W - 2 * M, leading=12.5)

    footer(f"Built by a GEEIQ analyst. Data: GEEIQ platform and public sources, "
           f"{payload['snapshot']}.   Page 1 of 2")
    c.showPage()

    # ================= PAGE 2: virtual worlds, in one page =================
    page_background()
    header(f"Brand check: {payload['brand']}")

    y = H - M - 62
    c.setFont("JakartaBold", 26)
    c.setFillColor(AMETHYST)
    c.drawString(M, y, "Virtual worlds, in one page")

    y -= 30
    y = draw_wrapped(STANDING_BODY, M, y, "Figtree", 10.5, MUTED,
                     W - 2 * M, leading=17)

    # verified GEEIQ figures on the amethyst band
    y -= 34
    band_h = 84
    c.setFillColor(AMETHYST)
    c.roundRect(M, y - band_h, W - 2 * M, band_h, 12, stroke=0, fill=1)
    bw = (W - 2 * M) / 4
    for i, (num, label) in enumerate(STANDING_BAND):
        bx = M + 20 + i * bw
        c.setFont("JakartaBold", 20)
        c.setFillColor(WHITE)
        c.drawString(bx, y - 34, num)
        c.setFont("Figtree", 7.4)
        c.setFillColor(LABEL_LIGHT)
        for j, line in enumerate(wrap(label, "Figtree", 7.4, bw - 34)):
            c.drawString(bx, y - 48 - j * 9.5, line)
    y = y - band_h - 34

    # three short teaching blocks
    y = section_label("How brands enter virtual worlds", M, y)
    for title, body in HOW_IT_WORKS:
        c.setFont("JakartaBold", 11)
        c.setFillColor(AMETHYST)
        c.drawString(M, y, title)
        y = draw_wrapped(body, M, y - 15, "Figtree", 9.5, MUTED,
                         W - 2 * M - 40, leading=14.5)
        y -= 38

    # closing block: a tinted card carries the CTA, with the analyst avatar
    # leaning out of the top so the page ends on something with personality
    card_h = 128
    card_bottom = 142
    c.setFillColor(TINT)
    c.roundRect(M, card_bottom, W - 2 * M, card_h, 14, stroke=0, fill=1)

    avatar = f"{ASSETS}/avatar.png"
    av_w = 132
    text_w = W - 2 * M - 48 - (av_w - 10 if os.path.exists(avatar) else 0)
    ty = card_bottom + card_h - 30
    ty = draw_wrapped(CLOSING, M + 24, ty, "FigtreeSemi", 9.8, AMETHYST,
                      text_w, leading=14.5)
    ty -= 20
    c.setFont("FigtreeSemi", 9.2)
    c.setFillColor(PURPLE)
    c.drawString(M + 24, ty, LINKS)

    if os.path.exists(avatar):
        c.drawImage(avatar, W - M - av_w - 6, card_bottom + 4,
                    width=av_w, height=av_w * (352 / 295),
                    mask="auto", preserveAspectRatio=True)

    footer(f"Built by a GEEIQ analyst. Data: GEEIQ platform and public sources, "
           f"{payload['snapshot']}.   Page 2 of 2")

    c.save()
    return out_path


def _short(n):
    """Compact number for chart labels and finding rows. 44m, not 44.0m."""
    n = int(n or 0)

    def trim(v, suffix):
        txt = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{txt}{suffix}"

    if n >= 1_000_000_000:
        return trim(n / 1_000_000_000, "bn")
    if n >= 1_000_000:
        return trim(n / 1_000_000, "m")
    if n >= 1_000:
        return f"{n / 1000:.0f}k"
    return f"{n:,}"


if __name__ == "__main__":
    payload = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else "report.pdf"
    print(render(payload, out))
