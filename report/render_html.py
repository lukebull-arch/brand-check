#!/usr/bin/env python3
"""Render the brand check PDF from the HTML template via headless Chrome.

The design is the KTM-corrected layout the sales team approved on 11 Aug 2026:
less copy, one hero figure, three cards, white panels, the standing page 2.
report/template.html is the single source of the look; this module only fills
it and prints it.

render(payload, out_path) is a drop-in for build_report.render. If no Chrome
or Chromium binary can be found, it raises, and run.py falls back to the old
ReportLab renderer so a report always ships.
"""
import html
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
GEEIQ_LOGO = os.path.join(HERE, "assets", "logo-color.png")
AVATAR = os.path.join(HERE, "assets", "avatar.png")

CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
]


def _chrome():
    for c in CHROME_CANDIDATES:
        if not c:
            continue
        path = c if os.path.sep in c and os.path.exists(c) else shutil.which(c)
        if path:
            return path
    raise RuntimeError("no Chrome or Chromium binary found (set CHROME_BIN)")


def _esc(s):
    return html.escape(str(s or ""), quote=False)


def _file_uri(path):
    return "file://" + os.path.abspath(path)


def _method_text(payload):
    c = payload.get("coverage", {})
    brand = payload["brand"]
    bits = [f"What we searched: Roblox marketplace, {c.get('items_scanned', 0)} results scanned, "
            f"{c.get('items_matched', 0)} matched to {brand}."]
    bits.append(f"Roblox experience search: {c.get('games_scanned', 0)} results scanned, "
                f"{c.get('games_matched', 0)} matched.")
    if c.get("videos_scanned"):
        plats = ", ".join(c.get("platforms") or [])
        if payload.get("youtube_suspect"):
            bits.append(f"YouTube: {c.get('videos_scanned', 0)} videos scanned across {brand} "
                        f"searches on {plats}; the view volume was mostly real-world content "
                        "naming the brand, so no YouTube figure is quoted in this report.")
        else:
            bits.append(f"YouTube: {c.get('videos_scanned', 0)} videos scanned across {brand} "
                        f"searches on {plats}, {c.get('videos_named', 0)} named the brand and "
                        "count towards the figures above.")
    bits.append("Everything above comes from public platform data at the snapshot date. "
                "Creator-made content is player-made and unaffiliated with the brand. "
                "Counts describe what we found, not platform totals.")
    return " ".join(bits)


def _rows(entries, kind):
    out = []
    for e in entries[:3]:
        name = _esc(e.get("name", ""))
        creator = _esc(e.get("creator", ""))
        left = f"{name} &middot; by {creator}" if creator else name
        if e.get("official"):
            left += " <span style=\"color:#7C68FB;font-weight:600;\">(official)</span>"
        if kind == "games":
            right = f"{_fmt(e.get('visits', 0))} visits"
        else:
            right = f"{_fmt(e.get('favorites', 0))} favourites"
        out.append(f'    <div class="row"><span>{left}</span><span class="r">{right}</span></div>')
    return "\n".join(out)


def _fmt(n):
    n = int(n or 0)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}bn"
    if n >= 10_000_000:
        return f"{n / 1_000_000:.0f}m"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    return f"{n:,}"


def render(payload, out_path):
    tpl = open(TEMPLATE).read()

    stats = payload.get("stats") or []
    hero = next((s for s in stats if s.get("coral")), stats[0] if stats else
                {"num": "", "label": ""})
    rest = [s for s in stats if s is not hero][:3]
    cards = "\n".join(
        f'    <div class="card"><span class="num">{_esc(s["num"])}</span>'
        f'<span class="lbl">{_esc(s["label"])}</span></div>' for s in rest)

    # Official experiences get their own panel only when they exist; most
    # brands have none and the section vanishes rather than reporting absence
    # twice (the headline already carries that).
    official_games = [g for g in (payload.get("top_games_named") or []) if g.get("official")]
    official_section = ""
    if official_games:
        rows = _rows(official_games, "games")
        official_section = ('  <p class="sec">Official activity</p>\n'
                            '  <div class="panel" style="margin-bottom:6mm;">\n'
                            f"{rows}\n  </div>\n")

    # Highlights: matched experiences by visits first, then loved items.
    fan_games = [g for g in (payload.get("top_games_named") or []) if not g.get("official")]
    items = payload.get("top_items_named") or []
    highlights_section = ""
    if fan_games or items:
        parts = []
        if fan_games:
            parts.append(_rows(fan_games, "games"))
        if items:
            parts.append(_rows(items, "items"))
        title = "Highlights" if (fan_games and items) else (
            "Top experiences by visits" if fan_games else "Most loved items")
        highlights_section = (f'  <p class="sec">{title}</p>\n'
                              '  <div class="panel" style="margin-bottom:6mm;">\n'
                              + "\n".join(parts) + "\n  </div>\n")

    brand_logo = (payload.get("brand_logo") or {}).get("path") if isinstance(
        payload.get("brand_logo"), dict) else payload.get("brand_logo")
    brand_logo_img = (f'<img src="{_file_uri(brand_logo)}" style="height:34px;max-width:60mm;object-fit:contain;">'
                      if brand_logo and os.path.exists(brand_logo) else "")
    avatar_img = (f'<img src="{_file_uri(AVATAR)}" style="height:150px;flex:none;">'
                  if os.path.exists(AVATAR) else "")

    filled = tpl.format(
        brand=_esc(payload["brand"]),
        snapshot=_esc(payload.get("snapshot", "")),
        headline=_esc(payload.get("headline", "")),
        hero_num=_esc(hero.get("num", "")),
        hero_label=_esc(hero.get("label", "")),
        cards=cards,
        official_section=official_section,
        highlights_section=highlights_section,
        reading=_esc(payload.get("reading", "")),
        method=_esc(_method_text(payload)),
        geeiq_logo=_file_uri(GEEIQ_LOGO),
        brand_logo_img=brand_logo_img,
        avatar_img=avatar_img,
    )

    workdir = os.path.dirname(os.path.abspath(out_path)) or "."
    html_path = os.path.join(workdir, "report.html")
    with open(html_path, "w") as f:
        f.write(filled)

    chrome = _chrome()
    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--virtual-time-budget=10000",
           f"--print-to-pdf={os.path.abspath(out_path)}", _file_uri(html_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 10_000:
        raise RuntimeError(f"Chrome print failed: {res.stderr[-400:]}")
    return out_path
