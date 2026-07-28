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
def brand_terms(brand):
    b = brand.lower().strip()
    terms = {b}
    if " " in b:
        terms.add(b.replace(" ", ""))
    return terms


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
    items = read_csv(os.path.join(csv_dir, "roblox_catalog_items.csv"))
    games = read_csv(os.path.join(csv_dir, "roblox_games.csv"))

    def is_official(creator):
        c = (creator or "").lower().strip()
        return c in terms

    official = [r for r in items if is_official(r["Creator"])]
    fan = [r for r in items if matches(r["Name"], terms) and not is_official(r["Creator"])]
    noise_items = [r for r in items if r not in official and r not in fan]
    creators = sorted({r["Creator"] for r in fan if r.get("Creator")})
    fav_key = lambda r: to_int(r.get("Favorites"))
    top_item = max(official + fan, key=fav_key, default=None)

    g_match = [r for r in games if matches(r["Name"], terms)]
    noise_games = [r for r in games if r not in g_match]
    visits = sum(to_int(r.get("Visits")) for r in g_match)
    live = sum(to_int(r.get("Active Players")) for r in g_match)
    top_game = max(g_match, key=lambda r: to_int(r.get("Visits")), default=None)
    rated = [int(r["Like %"]) for r in g_match
             if str(r.get("Like %", "")).strip().isdigit()]

    yt = {}
    for p in ("roblox", "fortnite", "minecraft"):
        rows = read_csv(os.path.join(csv_dir, f"youtube_{p}.csv"))
        if rows:
            yt[p] = {
                "videos": len(rows),
                "views": sum(to_int(r.get("Views")) for r in rows),
                "top": max(rows, key=lambda r: to_int(r.get("Views"))),
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
        "games_noise": len(noise_games),
        "combined_visits": visits,
        "live_players": live,
        "top_game": {"name": top_game["Name"], "visits": to_int(top_game.get("Visits")),
                     "like_pct": top_game.get("Like %"), "creator": top_game.get("Creator")} if top_game else None,
        "avg_like_pct": round(sum(rated) / len(rated)) if rated else None,
        "youtube": yt,
        # Named specifics: what a brand marketer actually wants to see
        "top_games_named": [
            {"name": r["Name"], "visits": to_int(r.get("Visits")),
             "like_pct": r.get("Like %"), "creator": r.get("Creator")}
            for r in sorted(g_match, key=lambda r: to_int(r.get("Visits")), reverse=True)[:4]
            if to_int(r.get("Visits"))
        ],
        "top_items_named": [
            {"name": r["Name"], "favorites": to_int(r.get("Favorites")),
             "creator": r.get("Creator"), "price": r.get("Price")}
            for r in sorted(official + fan, key=fav_key, reverse=True)[:3]
            if to_int(r.get("Favorites"))
        ],
        "platform_views": [
            {"platform": p.capitalize(), "views": v["views"], "videos": v["videos"],
             "top_video": v["top"].get("Title", "")}
            for p, v in yt.items() if v["views"]
        ],
        "sample_official": [r["Name"] for r in official[:8]],
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
                    "label": f"YouTube views across {a['brand']} gaming videos analysed"})
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
                    "label": f"{a['brand']} videos found across Roblox, Fortnite and Minecraft searches"})
    if a["live_players"]:
        out.append({"num": fmt(a["live_players"]),
                    "label": f"players inside {a['brand']} experiences at this snapshot"})
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
    if a["items_official"]:
        angle = "official"
        if a["combined_visits"]:
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
    email_body = (
        f"Hi [first name],\n\nYour brand check is attached. The headline: "
        f"{headline[0].lower()}{headline[1:]}\n\nIf you would like a walkthrough "
        "of what is in there and what your category is doing, I am happy to set "
        "up 20 minutes.\n\n[analyst name], GEEIQ")
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
and a two to four sentence analyst reading.

Writing rules, absolute: UK English. No em dashes, use full stops, commas or colons.
No exclamation marks. Never use: ecosystem, intelligence platform, seamless, leverage,
unlock, branded activations, benchmark performance, drive ROI. No "not X, it's Y" or
"not X, but Y" constructions. Sentence case. Creator-made content is player-made and
unofficial: never imply the brand made or endorsed it.

Also draft a short delivery email (2-3 sentences, personal, one specific finding,
offer of a walkthrough). The greeting must be exactly "Hi [first name]," and the
sign-off exactly "[analyst name], GEEIQ" with the literal square-bracket
placeholders unchanged: they are substituted later, never invent names. Make no
claims in the email or the reading beyond the provided figures: no trends, dips,
comparisons over time, or attributions the data does not contain.

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
            print(f"   claude attempt {attempt} rejected: reply was not parseable JSON "
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
        print(f"   claude attempt {attempt} rejected: {'; '.join(problems)}")
        feedback = ("Fix these problems and resend the full JSON: " + "; ".join(problems))
    print("   claude output failed guardrails twice; falling back to template")
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
    print(f"   copy source: {copy['source']}")

    print("== brand logo ==")
    logo = None
    try:
        logo = brand_logo.fetch(args.brand)
        print(f"   {logo['source']} | matched {logo['matched']}" if logo
              else "   no logo found, report will show the snapshot date instead")
    except Exception as e:
        print(f"   logo lookup skipped ({type(e).__name__})")

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
                   "videos_scanned": sum(v["videos"] for v in a["youtube"].values()),
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
            f.write(f"Logo matched entity: {logo['matched']}  "
                    f"<- check this is the right company\n\n")
        else:
            f.write("Brand logo: none found\n\n")
        f.write(json.dumps({k: v for k, v in a.items()
                            if not k.startswith("sample_")}, indent=2))
        f.write("\n\nSample official rows: " + json.dumps(a["sample_official"]))
        f.write("\nSample creator-made rows: " + json.dumps(a["sample_fan"]))
        f.write("\nSample excluded rows: " + json.dumps(a["sample_noise"]))
        if copy.get("notes_for_analyst"):
            f.write("\n\nModel notes: " + copy["notes_for_analyst"])

    print(f"\nDone.\n  PDF:     {pdf_path}\n  Email:   {email_path}\n  Summary: {summary_path}")


if __name__ == "__main__":
    main()
