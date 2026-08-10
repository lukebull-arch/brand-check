#!/usr/bin/env python3
"""GEEIQ brand check runner: brand name in, finished report out.

    python3 run.py --brand "KFC"                 # collect + build
    python3 run.py --brand "KFC" --csv-dir DIR   # reuse existing CSVs

Pipeline: collector -> classify rows -> compute figures -> judgment copy
(Claude API if ANTHROPIC_API_KEY is set, house-rule template otherwise)
-> render PDF -> write email draft + analyst summary alongside it.

Guardrails: every number in the report is computed here in code; the model
only selects and words. Its output is linted against the house writing rules
and every figure it uses is checked against the computed values. Anything
that fails twice falls back to the template so a report always ships.

Official matching, in three layers, because getting this wrong in either
direction damages the report:

1. Exact creator name, allowing for case and spacing ("Pizza Hut Official"
   runs The Hut). Punctuation stays significant so accounts imitating the
   brand ("Gregg's TM") stay out.
2. A punctuation variant plus Roblox's verified badge, the one signal an
   imitator cannot award itself.
3. A description declaring a brand-sanctioned activation, because partners
   often run these under their own account ("Formula E - Electric Lap"). Any
   disclaimer in the description voids the claim.

Reports always show both sides: the official footprint and the creator-made
one. See report/test_official.py.
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request

import brand_logo

# If fewer than this share of scanned videos actually name the brand, YouTube is
# mostly keyword collision: keep the figure for context but never let it lead.
YT_SIGNAL_FLOOR = 0.5

HERE = os.path.dirname(os.path.abspath(__file__))
COLLECTOR = os.path.join(HERE, "..", "collector", "grab.py")
VENV = os.path.join(HERE, ".venv")


# ---------- bootstrap: make sure reportlab is importable ----------
def ensure_reportlab():
    try:
        import reportlab  # noqa
        return
    except ImportError:
        pass
    py = os.path.join(VENV, "bin", "python3")
    if not os.path.exists(py):
        print("Setting up .venv with reportlab (first run only)...")
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
        subprocess.run([py, "-m", "pip", "install", "--quiet", "reportlab"], check=True)
    os.execv(py, [py] + sys.argv)


# ---------- classification and figures ----------
def base_brand(brand):
    """The brand with a trailing 'official' stripped: submissions and account
    names use it interchangeably ('Pizza Hut' vs 'Pizza Hut Official')."""
    b = brand.strip()
    return re.sub(r"\s*official\s*$", "", b, flags=re.I).strip() or b


def brand_terms(brand):
    terms = set()
    for t in (brand.lower().strip(), base_brand(brand).lower()):
        if t:
            terms.add(t)
            if " " in t:
                terms.add(t.replace(" ", ""))
    return terms


def _norm(s):
    """Lowercase with spacing removed: 'Pizza Hut' and 'PizzaHut' are the same
    account. Punctuation and symbols are kept, because that is exactly what
    separates a brand from an account imitating it: "Gregg's TM" is not Greggs."""
    return re.sub(r"\s+", "", (s or "").strip().lower())


def _loose(s):
    """Lowercase alphanumerics only. Collapses imitations onto the brand, so it
    is only ever consulted alongside a verified badge, never on its own."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def official_creator_norms(brand):
    """Creator names that count as the brand's own account."""
    n = _norm(base_brand(brand))
    return {n, n + "official", _norm(brand)} - {""}


def loose_creator_norms(brand):
    """Punctuation-insensitive forms, accepted only for verified accounts."""
    n = _loose(base_brand(brand))
    return {n, n + "official", _loose(brand)} - {""}


def sanctioned_pattern(brand):
    """Matches a description declaring a brand-sanctioned activation.

    A brand's own activation is often built and run by a partner studio, whose
    account name says nothing ("Formula E - Electric Lap" runs Formula E's
    official racing experience). The partnership is declared in the
    description, so that is where to look. The phrasings are deliberately
    narrow and must name the brand: "official" on its own is a word fan groups
    use about themselves constantly. Checked against 448 real descriptions
    across Greggs, KFC and adidas with no false positives.
    """
    b = re.escape(brand.strip()).replace(r"\ ", r"\s*")
    dash = r"[-‐-―−]"
    parts = [
        # \b matters: without it "unofficial Greggs" matches "official Greggs".
        rf"\bofficial(?:ly)?\s+(?:licensed\s+)?{b}\b",
        rf"\b{b}\s*{dash}\s*sponsored",
        rf"sponsored\s+by\s+{b}\b",
        rf"in\s+partnership\s+with\s+{b}\b",
        rf"official\s+partner\s+of\s+{b}\b",
        rf"\bofficially\s+licensed\b",
    ]
    return re.compile("|".join(parts), re.I)


# Fan builds say this about themselves constantly, and often in the same
# breath as calling themselves "the official <brand> fan group".
_DISCLAIMER = re.compile(
    r"\b(?:un\s*official"
    r"|not\s+(?:affiliated|endorsed|associated|sponsored|owned)"
    r"|no\s+affiliation"
    r"|fan[\s\-_]*(?:group|made|game|project|server|club)"
    r"|not\s+an?\s+official)\b", re.I)


def sanctioned_activation(brand, description):
    """True when a description declares the experience as the brand's own.

    Any disclaimer in the text voids it, whatever else the description claims.
    A build that calls itself a fan group is telling you what it is.
    """
    d = description or ""
    if _DISCLAIMER.search(d):
        return False
    return bool(sanctioned_pattern(brand).search(d))


def brand_pattern(brand):
    """Match the brand as a whole token. Substring matching turns Casiopea into
    Casio and inflates every figure it touches."""
    parts = [re.escape(t) for t in sorted(brand_terms(brand), key=len, reverse=True)]
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(parts) + r")(?![A-Za-z0-9])",
                      re.IGNORECASE)


def matches(text, terms):
    t = (text or "").lower()
    return any(term in t for term in terms)


def read_csv(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def to_int(s):
    s = str(s or "").replace(",", "").strip()
    return int(s) if s.isdigit() else 0


def fmt(n):
    if n >= 10_000_000_000:
        return f"{n / 1_000_000_000:.0f}bn"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}bn"
    if n >= 10_000_000:
        return f"{n / 1_000_000:.0f}m"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 100_000:
        return f"{n / 1000:.0f}k"
    if n >= 10_000:
        return f"{n / 1000:.1f}k"
    return f"{n:,}"


def analyse(csv_dir, brand):
    terms = brand_terms(brand)
    off_norms = official_creator_norms(brand)
    loose_norms = loose_creator_norms(brand)
    items = read_csv(os.path.join(csv_dir, "roblox_catalog_items.csv"))
    games = read_csv(os.path.join(csv_dir, "roblox_games.csv"))

    def is_official(creator, verified=False):
        """The brand's own account. An exact name, allowing for case and
        spacing, always counts. A punctuation variant counts only when Roblox
        has verified the account, which is the one signal an imitator cannot
        award itself. Marketplace rows carry no badge, so they need the exact
        name."""
        if _norm(creator) in off_norms:
            return True
        return bool(verified) and _loose(creator) in loose_norms

    official = [r for r in items if is_official(r["Creator"])]
    fan = [r for r in items if matches(r["Name"], terms) and not is_official(r["Creator"])]
    noise_items = [r for r in items if r not in official and r not in fan]
    creators = sorted({r["Creator"] for r in fan if r.get("Creator")})
    fav_key = lambda r: to_int(r.get("Favorites"))
    top_item = max(official + fan, key=fav_key, default=None)

    # An experience is the brand's own when its creator is the brand's
    # account, whatever the experience is called (The Hut never says Pizza
    # Hut).
    def is_official_game(r):
        if is_official(r.get("Creator"),
                       verified=r.get("Verified Creator") == "yes"):
            return True
        # Run by a partner, declared as the brand's in the description.
        return sanctioned_activation(brand, r.get("Description"))

    g_official = [r for r in games if is_official_game(r)]
    g_by_partner = [r for r in g_official
                    if not is_official(r.get("Creator"),
                                       verified=r.get("Verified Creator") == "yes")]

    # Accounts naming the brand that are not classified as it. Two kinds land
    # here and the data cannot tell them apart: imitations ("Gregg's TM",
    # "Greggs RBLX"), and partner accounts running a genuine sponsored
    # activation ("Formula E - Electric Lap", which Roblox describes as
    # officially sponsored). Both stay creator-made in the figures; the analyst
    # gets the list so a real activation is not reported as absent.
    near_pat = brand_pattern(brand)
    near = sorted({r["Creator"] for r in items + games
                   if r.get("Creator")
                   and (_loose(r["Creator"]) in loose_norms
                        or near_pat.search(r["Creator"]))
                   and not is_official(r.get("Creator"),
                                       verified=r.get("Verified Creator") == "yes")})
    g_match = [r for r in games if matches(r["Name"], terms) or r in g_official]
    noise_games = [r for r in games if r not in g_match]
    visits = sum(to_int(r.get("Visits")) for r in g_match)
    official_visits = sum(to_int(r.get("Visits")) for r in g_official)
    live = sum(to_int(r.get("Active Players")) for r in g_match)
    top_game = max(g_match, key=lambda r: to_int(r.get("Visits")), default=None)
    top_official_game = max(g_official, key=lambda r: to_int(r.get("Visits")), default=None)
    rated = [int(r["Like %"]) for r in g_match
             if str(r.get("Like %", "")).strip().isdigit()]

    # YouTube search returns anything the algorithm thinks is related, so a
    # keyword-collision video (a piano tutorial for "Casio") can carry hundreds
    # of millions of views that have nothing to do with the brand. Only videos
    # that name the brand in the title or channel count towards the figures.
    pat = brand_pattern(brand)
    yt, yt_scanned, yt_dropped = {}, 0, []
    for p in ("roblox", "fortnite", "minecraft"):
        rows = read_csv(os.path.join(csv_dir, f"youtube_{p}.csv"))
        if not rows:
            continue
        yt_scanned += len(rows)
        named = [r for r in rows
                 if pat.search(r.get("Title", "") or "")
                 or pat.search(r.get("Creator", "") or "")]
        dropped = sorted((r for r in rows if r not in named),
                         key=lambda r: to_int(r.get("Views")), reverse=True)
        yt_dropped.extend(
            f"{(r.get('Title') or '')[:60]} ({fmt(to_int(r.get('Views')))} views)"
            for r in dropped[:3])
        if named:
            yt[p] = {
                "videos": len(named),
                "views": sum(to_int(r.get("Views")) for r in named),
                "top": max(named, key=lambda r: to_int(r.get("Views"))),
                "scanned": len(rows),
            }

    return {
        "brand": brand,
        "items_total": len(items),
        "items_official": len(official),
        "items_fan": len(fan),
        "items_noise": len(noise_items),
        "distinct_creators": len(creators),
        "top_item": {"name": top_item["Name"], "favorites": to_int(top_item.get("Favorites"))} if top_item else None,
        "games_matching": len(g_match),
        "games_official": len(g_official),
        "games_noise": len(noise_games),
        "combined_visits": visits,
        "official_visits": official_visits,
        "live_players": live,
        "top_game": {"name": top_game["Name"], "visits": to_int(top_game.get("Visits")),
                     "like_pct": top_game.get("Like %"), "creator": top_game.get("Creator")} if top_game else None,
        "top_official_game": {"name": top_official_game["Name"],
                              "visits": to_int(top_official_game.get("Visits")),
                              "like_pct": top_official_game.get("Like %"),
                              "creator": top_official_game.get("Creator")} if top_official_game else None,
        "avg_like_pct": round(sum(rated) / len(rated)) if rated else None,
        "youtube": yt,
        "youtube_scanned": yt_scanned,
        "youtube_named": sum(v["videos"] for v in yt.values()),
        "youtube_dropped_examples": yt_dropped[:6],
        "youtube_ratio": round(sum(v["videos"] for v in yt.values()) / yt_scanned, 2)
        if yt_scanned else 0,
        "youtube_thin": bool(yt_scanned) and (
            sum(v["videos"] for v in yt.values()) / yt_scanned) < YT_SIGNAL_FLOOR,
        # Named specifics: what a brand marketer actually wants to see
        "top_games_named": [
            {"name": r["Name"], "visits": to_int(r.get("Visits")),
             "like_pct": r.get("Like %"), "creator": r.get("Creator"),
             "official": bool(is_official_game(r))}
            for r in sorted(g_match, key=lambda r: to_int(r.get("Visits")), reverse=True)[:4]
            if to_int(r.get("Visits"))
        ],
        "top_items_named": [
            {"name": r["Name"], "favorites": to_int(r.get("Favorites")),
             "creator": r.get("Creator"), "price": r.get("Price"),
             "official": bool(is_official(r.get("Creator")))}
            for r in sorted(official + fan, key=fav_key, reverse=True)[:3]
            if to_int(r.get("Favorites"))
        ],
        "platform_views": [
            {"platform": p.capitalize(), "views": v["views"], "videos": v["videos"],
             "top_video": v["top"].get("Title", "")}
            for p, v in yt.items() if v["views"]
        ],
        "near_official_creators": near,
        "official_via_partner": [f"{r['Name']} (run by {r.get('Creator')})"
                                 for r in g_by_partner],
        "sample_official": [r["Name"] for r in official[:8]],
        "sample_official_games": [f"{r['Name']} (by {r.get('Creator')})" for r in g_official[:8]],
        "sample_fan": [f"{r['Name']} (by {r['Creator']})" for r in fan[:8]],
        "sample_noise": [r["Name"] for r in noise_items[:8]],
    }


def candidates(a):
    """Candidate stats with exact formatted values. The model may only use these."""
    out = []
    if a["combined_visits"]:
        out.append({"num": fmt(a["combined_visits"]),
                    "label": f"lifetime visits across {a['brand']} experiences on Roblox"})
    yt_views = sum(v["views"] for v in a["youtube"].values())
    yt_videos = sum(v["videos"] for v in a["youtube"].values())
    if yt_views:
        out.append({"num": fmt(yt_views),
                    "label": f"YouTube views on videos naming {a['brand']} "
                             f"in gaming content"})
    if a["games_official"]:
        out.append({"num": str(a["games_official"]),
                    "label": f"official {a['brand']} experiences live on Roblox"})
    if a["official_visits"]:
        out.append({"num": fmt(a["official_visits"]),
                    "label": f"lifetime visits to the brand's own experiences"})
    if a["games_matching"]:
        out.append({"num": str(a["games_matching"]),
                    "label": f"{a['brand']} experiences in the top Roblox search results"})
    if a["items_official"]:
        out.append({"num": str(a["items_official"]),
                    "label": f"official {a['brand']} items on the marketplace"})
    if a["items_fan"]:
        out.append({"num": str(a["items_fan"]),
                    "label": f"creator-made {a['brand']} items on the marketplace"})
    if a["distinct_creators"]:
        out.append({"num": str(a["distinct_creators"]),
                    "label": f"different creators making {a['brand']} content"})
    if a["top_game"] and a["top_game"]["visits"]:
        out.append({"num": fmt(a["top_game"]["visits"]),
                    "label": f"visits to the most popular {a['brand']} experience"})
    if a["top_item"] and a["top_item"]["favorites"]:
        out.append({"num": fmt(a["top_item"]["favorites"]),
                    "label": f"favourites on the most loved {a['brand']} item"})
    if a["avg_like_pct"]:
        out.append({"num": f"{a['avg_like_pct']}%",
                    "label": f"average rating across rated {a['brand']} experiences"})
    if yt_videos:
        out.append({"num": str(yt_videos),
                    "label": f"videos naming {a['brand']} across Roblox, "
                             f"Fortnite and Minecraft searches"})
    if a["live_players"]:
        out.append({"num": fmt(a["live_players"]),
                    "label": f"players inside {a['brand']} experiences at this snapshot"})

    # A hero figure that needs apologising for is not a hero figure. When most
    # scanned videos were keyword collisions, push YouTube down to context so a
    # Roblox figure leads instead.
    if a.get("youtube_thin"):
        yt_entries = [c for c in out if "YouTube views" in c["label"]
                      or c["label"].startswith("videos naming")]
        out = [c for c in out if c not in yt_entries]
        for c in yt_entries:
            if "YouTube views" in c["label"]:
                c["label"] = (f"YouTube views on videos naming {a['brand']}, "
                              f"mostly outside gaming")
        out.extend(yt_entries)
    return out


# ---------- copy: Claude with guardrails, template as fallback ----------
BANNED = ["ecosystem", "intelligence platform", "seamless", "leverage", "unlock",
          "branded activations", "benchmark performance", "drive roi"]
NOT_X_RE = re.compile(r"\b(?:is|are|was|were)?n[o']t\s+(?:just\s+)?[^,.;:]{2,40},\s*(?:it'?s|but|they'?re)\b", re.I)


def lint(text):
    problems = []
    if "—" in text or "–" in text:
        problems.append("em/en dash")
    if "!" in text:
        problems.append("exclamation mark")
    for b in BANNED:
        if b in text.lower():
            problems.append(f"banned word: {b}")
    if NOT_X_RE.search(text):
        problems.append("'not X, it's Y' construction")
    return problems


def template_copy(a, cands):
    stats = cands[:6]
    if stats:
        stats[0] = {**stats[0], "coral": True}
    has_official = a["items_official"] or a["games_official"]
    if has_official:
        angle = "official"
        if a["games_official"] and a["official_visits"]:
            headline = (f"{a['brand']} runs an official presence on Roblox: "
                        f"{a['games_official']} live experience"
                        f"{'s' if a['games_official'] != 1 else ''} with "
                        f"{fmt(a['official_visits'])} lifetime visits, plus what "
                        "players have built around the brand.")
        elif a["combined_visits"]:
            headline = (f"{a['brand']} runs an official presence on Roblox, and players "
                        f"have built around it: {fmt(a['combined_visits'])} lifetime visits "
                        "across matching experiences.")
        elif a["top_item"] and a["top_item"]["favorites"]:
            headline = (f"{a['brand']} runs an official presence on Roblox: "
                        f"{a['items_official']} marketplace items, and the most loved "
                        f"has {fmt(a['top_item']['favorites'])} favourites.")
        else:
            headline = (f"{a['brand']} runs an official presence on Roblox with "
                        f"{a['items_official']} items on the marketplace.")
    else:
        angle = "whitespace"
        if a["combined_visits"]:
            headline = (f"We found {fmt(a['combined_visits'])} lifetime visits across "
                        f"creator-made {a['brand']} experiences on Roblox. None are official.")
        else:
            headline = (f"We found {a['items_fan']} creator-made {a['brand']} items "
                        "on the Roblox marketplace. None are official.")
    tg = a["top_game"]
    reading_bits = []
    if angle == "whitespace":
        reading_bits.append("Players built this presence with no involvement from the brand.")
    elif a["items_fan"] > a["items_official"]:
        reading_bits.append("The official catalogue sits alongside a larger creator-made footprint.")
    elif a["items_fan"]:
        reading_bits.append("A small creator-made footprint sits alongside the official catalogue.")
    else:
        reading_bits.append("The presence is almost entirely first party so far.")
    if tg:
        reading_bits.append(
            f"Attention concentrates in the standouts: {tg['name']} alone has "
            f"{fmt(tg['visits'])} visits.")
    reading_bits.append(
        f"Demand for {a['brand']} in virtual worlds already exists. "
        "The open question is who serves it." if angle == "whitespace" else
        f"The next question is how the official presence captures the demand "
        "players are already showing.")
    bullet_lines = "\n".join(f"- {s['num']} {s['label']}" for s in stats[:3])
    email_body = (
        f"Hi [first name],\n\n"
        f"Thanks for asking us to look at {a['brand']}. Your report is attached: "
        "one page, built by a GEEIQ analyst from our platform data.\n\n"
        f"The headline: {headline}\n\n"
        f"Numbers worth your attention:\n{bullet_lines}\n\n"
        "The report also covers how your category shows up across Roblox, "
        "Fortnite and other platforms, and where brands usually get their "
        "first move wrong.\n\n"
        f"If you would like a walkthrough of what is in there and what it means "
        f"for {a['brand']}, reply to this email and I will set up 20 minutes.\n\n"
        "[analyst name], GEEIQ")
    return {
        "headline": headline,
        "stats": stats,
        "reading": " ".join(reading_bits),
        "email_subject": f"Your GEEIQ brand check: {a['brand']}",
        "email_body": email_body,
        "source": "template",
    }


CLAUDE_SYSTEM = """You are a GEEIQ analyst writing the copy for a one-page brand check report.
You are given computed figures. You must not invent, adjust or recompute any number:
use the candidate stats exactly as given (num and label may be lightly reworded but the
num string must be unchanged). Pick the 4 to 6 strongest, put "coral": true on exactly
one (the single takeaway). Write a one-sentence headline led by the strongest number,
and an analyst reading of three to five sentences, 90 words at most: it has a
fixed slot on the page and longer copy pushes the layout out of shape.

Both sides, always: when the brand has an official presence (figures.items_official
or figures.games_official above zero), still report the creator-made footprint
alongside it, and when the presence is entirely creator-made say no official
presence exists. The contrast between official and player-made is the story;
never let one side crowd the other out entirely.

If figures.youtube_thin is true, the YouTube numbers are mostly keyword
collisions rather than brand content: do not lead the headline with them, do not
treat them as the main finding, and if you cite them at all say plainly that
most of that view volume sits outside gaming. Lead on the Roblox figures.

Writing rules, absolute: UK English. No em dashes, use full stops, commas or colons.
No exclamation marks. Never use: ecosystem, intelligence platform, seamless, leverage,
unlock, branded activations, benchmark performance, drive ROI. No "not X, it's Y" or
"not X, but Y" constructions. Sentence case. Creator-made content is player-made and
unofficial: never imply the brand made or endorsed it.

Also draft the delivery email as plain text with this exact structure:
- Greeting line, exactly "Hi [first name],"
- One short paragraph: thank them for asking us to look at the brand, and say
  the report is attached: one page, built by a GEEIQ analyst from our platform
  data.
- One paragraph starting exactly "The headline: " followed by the single
  strongest finding in one sentence, brand name capitalised as the brand writes
  it.
- The line "Numbers worth your attention:" then 2 or 3 bullets, each a hyphen
  and one candidate stat (num string unchanged) with a short plain label.
- One line on what else the report covers: how their category shows up across
  Roblox, Fortnite and other platforms, and where brands usually get their
  first move wrong.
- One closing line offering a 20 minute walkthrough of what it means for the
  brand, asking them to reply to this email.
- Sign-off exactly "[analyst name], GEEIQ"
The greeting and sign-off placeholders stay literal square brackets: they are
substituted later, never invent names. Make no claims in the email or the
reading beyond the provided figures: no trends, dips, comparisons over time,
or attributions the data does not contain.

Respond with ONLY a JSON object:
{"headline": str, "stats": [{"num": str, "label": str, "coral": bool}],
 "reading": str, "email_subject": str, "email_body": str, "notes_for_analyst": str}
notes_for_analyst: anything odd in the data, likely false positives or lookalikes."""


def claude_copy(a, cands, api_key):
    body = {
        "model": os.environ.get("BRAND_CHECK_MODEL", "claude-sonnet-5"),
        "max_tokens": 3000,
        "system": CLAUDE_SYSTEM,
        "messages": [{"role": "user", "content": json.dumps({
            "figures": a, "candidate_stats": cands}, ensure_ascii=False)}],
    }
    feedback = None
    for attempt in (1, 2):
        msgs = body["messages"][:]
        if feedback:
            msgs.append({"role": "user", "content": feedback})
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({**body, "messages": msgs}).encode(),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.load(r)
        text = "".join(b.get("text", "") for b in resp.get("content", []))
        try:
            out = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except Exception:
            print(f"  claude attempt {attempt} rejected: reply was not parseable JSON "
                  f"(stop_reason={resp.get('stop_reason')}, {len(text)} chars)")
            feedback = "Your reply was not valid JSON. Respond with only the JSON object."
            continue
        # guardrail 1: every number must come from the candidates
        allowed = {c["num"] for c in cands}
        bad_nums = [s["num"] for s in out.get("stats", []) if s["num"] not in allowed]
        # guardrail 2: house style lint
        prose = " ".join([out.get("headline", ""), out.get("reading", ""),
                          out.get("email_subject", ""), out.get("email_body", "")]
                         + [s.get("label", "") for s in out.get("stats", [])])
        problems = lint(prose)
        if bad_nums:
            problems.append(f"stats not in candidate list: {bad_nums}")
        corals = sum(1 for s in out.get("stats", []) if s.get("coral"))
        if corals != 1:
            problems.append("exactly one stat must have coral true")
        body_txt = out.get("email_body", "")
        if "[first name]" not in body_txt or "[analyst name]" not in body_txt:
            problems.append("email must keep the literal [first name] and [analyst name] placeholders")
        if not problems:
            out["source"] = "claude"
            return out
        print(f"  claude attempt {attempt} rejected: {'; '.join(problems)}")
        feedback = ("Fix these problems and resend the full JSON: " + "; ".join(problems))
    print("  claude output failed guardrails twice; falling back to template")
    return None


# ---------- main ----------
def main():
    ensure_reportlab()
    from build_report import render

    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--csv-dir", help="skip collection, use CSVs from this dir")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-llm", action="store_true", help="force template copy")
    args = ap.parse_args()

    slug = re.sub(r"[^a-z0-9]+", "-", args.brand.lower()).strip("-")
    out_dir = args.out_dir or os.path.join(HERE, "out", slug)
    os.makedirs(out_dir, exist_ok=True)

    csv_dir = args.csv_dir
    if not csv_dir:
        csv_dir = os.path.join(out_dir, "data")
        print("== collecting ==")
        result = subprocess.run([sys.executable, COLLECTOR, "--brand", args.brand,
                                 "--out", csv_dir])
        if result.returncode != 0:
            print(f"collector exited {result.returncode}; building from whatever was collected")

    print("== analysing ==")
    a = analyse(csv_dir, args.brand)
    cands = candidates(a)
    if not cands:
        print("No usable figures found. Check the CSVs before building a report.")
        sys.exit(2)

    print("== writing copy ==")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    copy = None
    if api_key and not args.no_llm:
        try:
            copy = claude_copy(a, cands, api_key)
        except Exception as e:
            print(f"Claude call failed ({e}); using template copy")
    if not copy:
        copy = template_copy(a, cands)
    print(f"  copy source: {copy['source']}")

    print("== brand logo ==")
    logo = None
    try:
        logo = brand_logo.fetch(args.brand)
        print(f"  {logo['source']} | matched {logo['matched']}" if logo
              else "  no logo found, report will show the snapshot date instead")
    except Exception as e:
        print(f"  logo lookup skipped ({type(e).__name__})")

    snapshot = datetime.date.today().strftime("%B %Y")
    # The hero figure is decided here, not by the model: it is the top-priority
    # computed candidate, so the biggest credible number always leads the page.
    stats = [dict(s) for s in copy["stats"]]
    hero_num = cands[0]["num"]
    if not any(s["num"] == hero_num for s in stats):
        stats.insert(0, dict(cands[0]))
    for s in stats:
        s["coral"] = s["num"] == hero_num
    stats.sort(key=lambda s: not s["coral"])

    payload = {"brand": args.brand, "snapshot": snapshot,
               "headline": copy["headline"], "stats": stats,
               "reading": copy["reading"],
               "brand_logo": logo,
               "coverage": {
                   "items_scanned": a["items_total"], "items_matched":
                       a["items_official"] + a["items_fan"],
                   "games_scanned": a["games_matching"] + a["games_noise"],
                   "games_matched": a["games_matching"],
                   "videos_scanned": a["youtube_scanned"],
                   "videos_named": a["youtube_named"],
                   "platforms": [p.capitalize() for p in a["youtube"]],
               },
               "top_games_named": a["top_games_named"],
               "top_items_named": a["top_items_named"],
               "platform_views": a["platform_views"]}

    print("== rendering ==")
    stamp = datetime.date.today().strftime("%Y-%m")
    pdf_path = os.path.join(out_dir, f"GEEIQ_Brand_check_{args.brand.replace(' ', '_')}_{stamp}.pdf")
    render(payload, pdf_path)

    email_path = os.path.join(out_dir, "email_draft.txt")
    with open(email_path, "w") as f:
        f.write(f"Subject: {copy['email_subject']}\n\n{copy['email_body']}\n")

    summary_path = os.path.join(out_dir, "analyst_summary.txt")
    with open(summary_path, "w") as f:
        f.write(f"Brand check summary: {args.brand} ({snapshot})\n")
        f.write(f"Copy source: {copy['source']}\n")
        if logo:
            f.write(f"Brand logo: {logo['source']}\n")
            f.write(f"Logo matched entity: {logo['matched']} "
                    f"<- check this is the right company\n\n")
        else:
            f.write("Brand logo: none found\n\n")
        f.write(json.dumps({k: v for k, v in a.items()
                            if not k.startswith("sample_")}, indent=2))
        if a.get("youtube_dropped_examples"):
            f.write("\n\nYouTube videos excluded as keyword collisions "
                    "(did not name the brand):\n - "
                    + "\n - ".join(a["youtube_dropped_examples"]))
        if a.get("official_via_partner"):
            f.write("\n\nCounted as official on the strength of the experience "
                    "description, not the account name (a partner studio runs "
                    "these for the brand): "
                    + json.dumps(a["official_via_partner"]))
        near_list = a.get("near_official_creators") or []
        if near_list:
            shown = near_list[:12]
            more = len(near_list) - len(shown)
            f.write("\n\nCHECK THESE: accounts naming the brand that are counted as "
                    "creator-made, not official. Imitators mostly, but a partner "
                    "account running a sponsored activation looks the same in the "
                    "data, so confirm before the report says no official presence: "
                    + json.dumps(shown)
                    + (f" (+{more} more)" if more else ""))
        f.write("\n\nSample official rows: " + json.dumps(a["sample_official"]))
        f.write("\nSample official experiences: " + json.dumps(a["sample_official_games"]))
        f.write("\nSample creator-made rows: " + json.dumps(a["sample_fan"]))
        f.write("\nSample excluded rows: " + json.dumps(a["sample_noise"]))
        if copy.get("notes_for_analyst"):
            f.write("\n\nModel notes: " + copy["notes_for_analyst"])

    print(f"\nDone.\n  PDF: {pdf_path}\n  Email: {email_path}\n  Summary: {summary_path}")


if __name__ == "__main__":
    main()
