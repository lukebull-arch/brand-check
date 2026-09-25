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
# The campaign landing page. The QR carries per-brand UTMs so every letter is
# attributable in GA4; the URL printed as text stays short and typeable.
CTA_PAGE = "https://geeiq.com/meet-report"
CTA_URL = CTA_PAGE  # overridden per render with UTMs via cta_url in the payload
CTA_URL_PRINTED = "geeiq.com/meet-report"


# Sender per brand, from the Direct Mail sheet. The /meet page whitelists
# ref to rachel|xaha|cody: it personalises the heading, tags the HubSpot
# submission and picks that sender's calendar embed.
SENDER_BY_SLUG = {
    # Xaha
    "snickers": "xaha", "starbucks": "xaha", "heinz": "xaha",
    "walkers": "xaha", "old-el-paso": "xaha", "kinder": "xaha",
    "domino-s": "xaha", "dominos": "xaha", "cadbury": "xaha",
    "haribo": "xaha", "nando-s": "xaha", "nandos": "xaha",
    # Rachel
    "lidl": "rachel", "tesco": "rachel", "john-lewis": "rachel",
    "aldi": "rachel", "aston-villa": "rachel",
    "brighton-hove-albion": "rachel", "brighton-hove-albion-fc": "rachel",
    "dp-world-tour": "rachel", "premier-padel": "rachel",
    "world-tennis": "rachel", "england-rugby": "rachel",
    # Cody
    "nothing": "cody", "disney": "cody", "fanatics": "cody",
    "sony-pictures-entertainment": "cody", "sony-pictures": "cody", "lg": "cody", "hasbro": "cody",
    "cineworld": "cody", "odeon": "cody", "merlin-entertainment": "cody",
    "merlin-entertainments": "cody", "ryanair": "cody", "visitbritain": "cody",
    "visit-britain": "cody", "dyson": "cody",
}


def brand_slug(brand):
    slug = "".join(c if c.isalnum() else "-" for c in (brand or "").lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def campaign_qr_url(brand):
    """Short per-SDR link, identical to the URL printed on the business card
    in the same parcel: card and report scan to the same place. The short
    string keeps the code at a low version, which is what lets the GEEIQ icon
    sit in the middle without costing reliability. Brand attribution comes
    from the form's Company field, not the URL (Luke, 15 Sep 2026)."""
    sender = SENDER_BY_SLUG.get(brand_slug(brand))
    return f"https://geeiq.com/{sender}" if sender else CTA_PAGE


ICON = os.path.join(HERE, "assets", "icon.png")


def qr_data_uri(url, light="#FAF7F2", px=1200, icon_frac=0.20):
    """Dark amethyst QR with the GEEIQ icon centred, to Hayley's card spec.
    Error correction H: the icon occludes about 20% of the code, and a SHORT
    url at level M fails to decode with it (tested 9 Sep 2026). Returns a
    base64 PNG string."""
    import base64
    import io
    import segno
    from PIL import Image
    qr = segno.make(url, error="h")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=20, border=4, dark="#2E204D", light=light)
    im = Image.open(buf).convert("RGBA").resize((px, px), Image.LANCZOS)
    if os.path.exists(ICON):
        side = int(px * icon_frac)
        icon = Image.open(ICON).convert("RGBA").resize((side, side), Image.LANCZOS)
        pad = int(side * 1.14)
        r, g, b = tuple(int(light.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        plate = Image.new("RGBA", (pad, pad), (r, g, b, 255))
        plate.paste(icon, ((pad - side) // 2, (pad - side) // 2), icon)
        im.paste(plate, ((px - pad) // 2, (px - pad) // 2), plate)
    out = io.BytesIO()
    im.convert("RGB").save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


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
    at_least = "at least " if c.get("items_truncated") else ""
    bits = [f"What we searched: Roblox marketplace, {at_least}{c.get('items_scanned', 0):,} "
            f"results scanned, {at_least}{c.get('items_matched', 0):,} matched to {brand}."]
    if c.get("context_label") and c.get("items_named_raw", 0) > c.get("items_matched", 0):
        other = c["items_named_raw"] - c["items_matched"]
        bits.append(f"The name {brand} also appears on {other:,} listings that are not "
                    f"{c['context_label']} products, and those are excluded from every figure.")
    if c.get("items_truncated"):
        bits.append("Roblox limits how many results one search returns, and that "
                    "limit was reached, so the marketplace figures here are a "
                    "floor rather than a total.")
    bits.append(f"Roblox experience search: {c.get('games_scanned', 0):,} results scanned, "
                f"{c.get('games_matched', 0):,} matched.")
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



# A reader who opens the parcel cold needs two things before any number:
# why this page exists, and what the Roblox words mean. Same strip on every
# report, placed between the headline and the hero figure.
READ_ME_CSS = (".readme { background:#EEEDFE; border-radius:10px; padding:9px 14px; margin:0 0 4mm 0; "
               "font-size:11px; line-height:1.5; color:var(--ink-soft); } "
               ".readme p { margin:0; } .readme p + p { margin-top:3px; } "
               ".readme b { font-weight:600; color:var(--ink); }")


def readme_html(subject, sender=None, page1_text=""):
    """The "why you have this / how to read it" strip. Names the sender and
    the purpose, and only defines the words page 1 actually uses."""
    t = (page1_text or "").lower()
    who = (html.escape(sender, quote=False) + " at GEEIQ") if sender else "GEEIQ"
    why = ('<p><b>Why you have this.</b> ' + who + ' looked up ' + html.escape(subject, quote=False)
           + ' on Roblox and sent you this page to start a conversation. GEEIQ measures how brands show up '
           'inside video games. On Roblox, most of the games are built by the players themselves.</p>')
    parts = []
    if "experience" in t:
        parts.append("Experiences are those player-built games" + (", and a visit is one play session" if "visit" in t else "") + ".")
    if "item" in t or "favourite" in t:
        parts.append("Items are avatar clothes and accessories that players design"
                     + ("; a favourite is a player saving one" if "favourite" in t else "") + ".")
    parts.append("Fan-made means made by players rather than the brand.")
    return '<div class="readme">' + why + '<p><b>How to read it.</b> ' + " ".join(parts) + '</p></div>'


SENDER_NAMES = {"rachel": "Rachel", "xaha": "Xaha", "cody": "Cody"}


def personalise(page_html, url):
    """Name the sender on the page and say what the QR code does. Applied at
    finish time so standard and hybrid reports get it the same way.
    Idempotent: safe to run on a page that already has it."""
    import re as _re
    sender = SENDER_NAMES.get(url.rstrip("/").rsplit("/", 1)[-1])
    if not sender:
        return page_html
    h = page_html
    h = h.replace("<span>Scan for a full walkthrough</span>", f"<span>Scan to book a walkthrough with {sender}</span>")
    h = h.replace('<p class="scan-line">Scan for a full walkthrough</p>',
                  f'<p class="scan-line">Scan to book a walkthrough with {sender} at GEEIQ</p>')
    h = h.replace("every day, so we can show you what is driving it, how your category compares, and where the opening is.",
                  f"every day. In a walkthrough, {sender} can show you what is driving it, how your category compares, "
                  "and where the opening is.")
    h = h.replace("around the brands they love, with or without permission.", "around the brands they love.")
    h = _re.sub(r"Built by a GEEIQ analyst(?: and sent by \w+ at GEEIQ)?\. Data:",
                f"Built by a GEEIQ analyst and sent by {sender} at GEEIQ. Data:", h)
    # rebuild the strip with the sender and page-aware definitions
    m = _re.search(r'<div class="readme">.*?</div>', h, _re.S)
    if m:
        sm = _re.search(r"looked up (.*?) on Roblox and sent you", m.group(0)) or \
             _re.search(r"players, for (.*?)\. This page is what we found", m.group(0))
        subject = html.unescape(sm.group(1)) if sm else ""
        p1_end = h.find('<div class="foot">', m.end())
        p1_text = _re.sub(r"<[^>]+>", " ", h[m.end():p1_end if p1_end > 0 else len(h)])
        h = h[:m.start()] + readme_html(subject, sender, p1_text) + h[m.end():]
    return h


def add_readme(page_html, subject):
    """Insert (or replace) the read-me strip and its CSS in a filled report."""
    import re as _re
    block = readme_html(subject, None, page_html)
    if 'class="readme"' in page_html:
        return _re.sub(r'<div class="readme">.*?</div>', lambda m: block, page_html, count=1, flags=_re.S)
    if ".readme {" not in page_html:
        page_html = page_html.replace("</style>", READ_ME_CSS + "\n</style>", 1)
    i = page_html.index('<div class="hero">')
    return page_html[:i] + block + "\n  " + page_html[i:]


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

    # Accounts and groups trading on the brand's name. Stated as a plain count
    # of accounts using the name, never as "unofficial": a sponsored partner
    # account looks identical in public data, and that claim is only safe once
    # the GEEIQ platform has been checked (the KTM and Aston Martin lesson).
    # Who is actually making the items. For a brand with no official presence
    # this is the argument in one panel: named people, already at work.
    top_creators = [c for c in (payload.get("top_creators") or []) if c.get("name")]
    creators_section = ""
    if len(top_creators) >= 3:
        rows = "\n".join(
            f'      <div class="row"><span>{_esc(c["name"])}</span>'
            f'<span>{c["items"]} items</span></div>' for c in top_creators[:6])
        creators_section = ('  <p class="sec">Most active creators</p>\n'
                            '  <div class="panel" style="margin-bottom:6mm;">\n'
                            + rows + "\n  </div>\n")

    name_users = [n for n in (payload.get("name_users") or []) if n]
    names_section = ""
    if len(name_users) >= 3:
        shown = name_users[:12]
        more = len(name_users) - len(shown)
        rows = "\n".join(f"      <span>{_esc(n)}</span>" for n in shown)
        tail = (f'  <p class="lbl" style="font-size:10.5px;color:#8C82A6;'
                f'margin-top:6px;">and {more} more</p>\n' if more else "")
        names_section = (
            f'  <p class="sec">Accounts using the {_esc(payload["brand"])} '
            f'name ({len(name_users)})</p>\n'
            '  <div class="panel" style="margin-bottom:6mm;">\n'
            '    <div class="names">\n' + rows + "\n    </div>\n"
            + tail + "  </div>\n")

    brand_logo = (payload.get("brand_logo") or {}).get("path") if isinstance(
        payload.get("brand_logo"), dict) else payload.get("brand_logo")
    brand_logo_img = (f'<img src="{_file_uri(brand_logo)}" style="height:34px;max-width:60mm;object-fit:contain;">'
                      if brand_logo and os.path.exists(brand_logo) else "")
    avatar_img = (f'<img src="{_file_uri(AVATAR)}" style="height:150px;flex:none;">'
                  if os.path.exists(AVATAR) else "")

    # Two codes per report, both to the same short per-SDR url: 30mm at the
    # top of page 1 beside the headline, 26mm in the page 2 CTA. Built with
    # the GEEIQ icon centred, on each block's own background colour.
    qr_top = ""
    qr_img = ""
    try:
        url = campaign_qr_url(payload.get("brand"))
        qr_top = ('<div class="qr qr-top">'
                  f'<img src="data:image/png;base64,{qr_data_uri(url, "#FAF7F2")}">'
                  '<span>Scan for a full walkthrough</span></div>')
        qr_img = ('<div class="qr">'
                  f'<img src="data:image/png;base64,{qr_data_uri(url, "#EEEDFE")}">'
                  '</div>')
    except Exception as e:
        print(f"  note: no QR code in this build ({e})")

    headline = payload.get("headline", "")
    h1_class = "long" if len(headline) > 115 else ""

    filled = tpl.format(
        brand=_esc(payload["brand"]),
        snapshot=_esc(payload.get("snapshot", "")),
        headline=_esc(payload.get("headline", "")),
        hero_num=_esc(hero.get("num", "")),
        hero_label=_esc(hero.get("label", "")),
        cards=cards,
        official_section=official_section,
        highlights_section=highlights_section,
        names_section=names_section,
        creators_section=creators_section,
        reading=_esc(payload.get("reading", "")),
        method=_esc(_method_text(payload)),
        geeiq_logo=_file_uri(GEEIQ_LOGO),
        brand_logo_img=brand_logo_img,
        avatar_img=avatar_img,
        qr_img=qr_img,
        qr_top=qr_top,
        h1_class=h1_class,
    )

    filled = add_readme(filled, payload["brand"])

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
