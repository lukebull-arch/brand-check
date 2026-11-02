#!/usr/bin/env python3
"""GEEIQ brand check collector.

Pulls the brand check source data straight from platform APIs, replacing the
browser extension step. Produces CSVs matching the data grabber's contract
(plus engagement columns the DOM never had).

Usage:
    python3 grab.py --brand "KFC"
    python3 grab.py --brand "adidas" --out ./out --pages 8

Auth:
    Roblox search returns nothing to logged-out sessions. Put your
    .ROBLOSECURITY cookie value in ~/.config/geeiq/roblosecurity (chmod 600)
    or the ROBLOSECURITY env var. Get it from your own browser: DevTools >
    Application > Cookies > roblox.com. Treat it like a password.

    YouTube needs a YouTube Data API v3 key in YOUTUBE_API_KEY. Without it
    the YouTube CSVs are skipped with a warning.

Stdlib only. Polite pacing between requests, single retry on rate limits.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "GEEIQ brand check collector (internal tool; contact luke.bull@geeiq.com)"
PAUSE_S = 1.2
COOKIE_PATH = os.path.expanduser("~/.config/geeiq/roblosecurity")
YT_PLATFORMS = ["roblox", "fortnite", "minecraft"]


def http_json(url, cookie=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    if cookie:
        req.add_header("Cookie", f".ROBLOSECURITY={cookie}")
    for attempt, wait in ((1, 20), (2, 45), (3, 90), (4, 0)):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and wait:
                print(f"  rate limited, backing off {wait}s...")
                time.sleep(wait)
                continue
            raise
    return None


def load_cookie(args):
    if args.no_auth:
        return None
    if os.environ.get("ROBLOSECURITY"):
        return os.environ["ROBLOSECURITY"].strip()
    if os.path.exists(COOKIE_PATH):
        return open(COOKIE_PATH).read().strip()
    return None


ORG_SUFFIXES = {"fc", "afc", "f.c.", "cf", "sc", "plc", "ag", "inc", "inc.",
                "ltd", "ltd.", "llc", "gmbh", "sa", "co", "co.", "group"}


def brand_variants(brand):
    """The names a brand actually appears under. Fans write 'Chelsea', not
    'Chelsea (FC)': a suffixed or bracketed submission must also search and
    match the core name, or the whole catalogue reads as noise (a Chelsea FC
    run undercounted 19x this way)."""
    out, seen = [], set()

    def add(name):
        name = " ".join(name.split()).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)

    add(brand)
    no_parens = re.sub(r"\s*\([^)]*\)", "", brand)
    add(no_parens)
    words = no_parens.split()
    if len(words) > 1 and words[-1].lower().strip(".") in {x.strip(".") for x in ORG_SUFFIXES}:
        add(" ".join(words[:-1]))
    return out


ITEM_PAGE_CEILING = 40  # 40 x 30 = 1,200 rows, beyond Roblox's ~1,000-row query cap
QUERY_CAP_HINT = 960    # a query exhausting at/above this almost certainly hit the cap


def grab_items(brand, cookie, pages, out_dir):
    """Marketplace items via catalog search API.

    Runs every brand variant as its own query and paginates each until the
    cursor is exhausted. There is no page limit by default: a Chelsea FC run
    once stopped at 5 pages (54 matched items) when the real catalogue held
    1,047+, and nothing said so. Roblox itself caps a single query at roughly
    1,000 rows; when a query lands there the count is a floor, not a total,
    and the collector says so out loud.
    """
    variants = brand_variants(brand)
    rows, seen = [], set()
    truncated = False
    for term in variants:
        cursor, page, fetched = "", 0, 0
        print(f'  items query: "{term}"')
        while True:
            page += 1
            q = urllib.parse.urlencode({"Keyword": term, "Limit": 30, "Cursor": cursor})
            data = http_json(f"https://catalog.roblox.com/v1/search/items/details?{q}", cookie)
            batch = data.get("data") or []
            fetched += len(batch)
            fresh = 0
            for d in batch:
                if d.get("id") in seen:
                    continue
                seen.add(d.get("id"))
                fresh += 1
                kind = "bundles" if d.get("itemType") == "Bundle" else "catalog"
                slug = re.sub(r"[^A-Za-z0-9]+", "-", d.get("name", "")).strip("-") or "item"
                rows.append({
                    "Name": d.get("name", ""),
                    "ID": d.get("id", ""),
                    "URL": f"https://www.roblox.com/{kind}/{d.get('id')}/{slug}",
                    "Creator": d.get("creatorName", ""),
                    "Creator Type": d.get("creatorType", ""),
                    "Price": d.get("price", ""),
                    "Favorites": d.get("favoriteCount", ""),
                    "Item Type": d.get("itemType", ""),
                    "Created": (d.get("itemCreatedUtc") or "")[:10],
                })
            cursor = data.get("nextPageCursor")
            print(f"    page {page}: {len(batch)} rows, {fresh} new ({len(rows)} total)")
            if not cursor or not batch:
                break
            if pages and page >= pages:
                truncated = True
                print(f"    WARNING: stopped at your --pages limit ({pages}) with more "
                      f"results still available. Counts are a truncated sample. "
                      f"Rerun without --pages to collect everything.")
                break
            if page >= ITEM_PAGE_CEILING:
                truncated = True
                print(f"    WARNING: stopped at the {ITEM_PAGE_CEILING}-page safety "
                      f"ceiling with a live cursor. Counts are a floor.")
                break
            time.sleep(PAUSE_S)
        if fetched >= QUERY_CAP_HINT:
            truncated = True
            print(f'    NOTE: "{term}" returned {fetched} rows, which is Roblox\'s '
                  f"~1,000-row ceiling for a single query. More items likely "
                  f"exist. Report this count as 'at least N', never as a total.")
    n_match = mark_brand_match(brand, rows)
    report_short_name_share(brand, rows, n_match)
    path = os.path.join(out_dir, "roblox_catalog_items.csv")
    write_csv(path, rows)
    return len(rows), truncated


def grab_games(brand, cookie, pages, out_dir):
    """Experiences via the omni-search API the site itself uses.

    Every brand variant is queried; results are deduped by universe. Game
    search usually exhausts naturally within a few pages, but if a page token
    remains at the cap the collector says so rather than presenting a sample
    as a census.
    """
    rows, seen_uni = [], set()
    truncated = False
    session = "geeiq-brand-check"
    for term in brand_variants(brand):
        token = ""
        print(f'  games query: "{term}"')
        for page in range(pages):
            q = urllib.parse.urlencode({
                "searchQuery": term, "pageType": "all",
                "sessionId": session, "pageToken": token,
            })
            data = http_json(f"https://apis.roblox.com/search-api/omni-search?{q}", cookie)
            batch = []
            for group in data.get("searchResults") or []:
                if group.get("contentGroupType") != "Game":
                    continue
                batch.extend(group.get("contents") or [])
            fresh = 0
            for g in batch:
                key = g.get("universeId") or g.get("rootPlaceId")
                if key in seen_uni:
                    continue
                seen_uni.add(key)
                fresh += 1
                up = g.get("totalUpVotes") or 0
                down = g.get("totalDownVotes") or 0
                like = round(100 * up / (up + down)) if (up + down) > 0 else "N/A"
                slug = re.sub(r"[^A-Za-z0-9]+", "-", g.get("name", "")).strip("-") or "game"
                rows.append({
                    "Name": g.get("name", ""),
                    "ID": g.get("rootPlaceId", ""),
                    "Universe ID": g.get("universeId", ""),
                    "URL": f"https://www.roblox.com/games/{g.get('rootPlaceId')}/{slug}",
                    "Like %": like,
                    "Active Players": g.get("playerCount", 0),
                    "Creator": g.get("creatorName", ""),
                    "Up Votes": up,
                    "Down Votes": down,
                    "Sponsored": "yes" if g.get("isSponsored") else "",
                })
            print(f"    page {page + 1}: {len(batch)} rows, {fresh} new ({len(rows)} total)")
            token = data.get("nextPageToken")
            if not token or not batch:
                break
            time.sleep(PAUSE_S)
        if token:
            truncated = True
            print(f"    WARNING: stopped at the {pages}-page games limit with more "
                  f"results still available. Counts are a truncated sample; "
                  f"rerun with a higher --pages if the tail matters.")

    # Enrich with lifetime visits, favourites and creator from the games API.
    # Search leaves creatorName empty and has no reach metric; this fills both.
    by_universe = {str(r["Universe ID"]): r for r in rows if r["Universe ID"]}
    ids = list(by_universe.keys())
    for i in range(0, len(ids), 50):
        chunk = ",".join(ids[i:i + 50])
        try:
            data = http_json(f"https://games.roblox.com/v1/games?universeIds={chunk}", cookie)
        except Exception as e:
            print(f"  games enrichment batch failed ({e}); continuing")
            continue
        for g in data.get("data") or []:
            row = by_universe.get(str(g.get("id")))
            if not row:
                continue
            creator = g.get("creator") or {}
            row["Visits"] = g.get("visits", "")
            row["Favorites"] = g.get("favoritedCount", "")
            row["Creator"] = creator.get("name", "")
            row["Creator Type"] = creator.get("type", "")
            row["Verified Creator"] = "yes" if creator.get("hasVerifiedBadge") else ""
            # Partner-run brand activations declare themselves in the
            # description, not the account name ("Formula E - Electric Lap"
            # runs Formula E's official experience). Keep it for classification.
            row["Description"] = re.sub(r"\s+", " ", (g.get("description") or ""))[:2000]
        print(f"  games enrichment: {min(i + 50, len(ids))}/{len(ids)}")
        time.sleep(PAUSE_S)
    for r in rows:  # ensure consistent columns even if a batch failed
        for col in ("Visits", "Favorites", "Creator Type", "Verified Creator",
                    "Description"):
            r.setdefault(col, "")

    # Search pads weak queries with popular or semantically similar games.
    # Stamp each row so downstream counting is mechanical, not judgment.
    n_match = mark_brand_match(brand, rows)
    if rows and n_match == 0:
        print("  WARNING: none of the returned experiences mention the brand. "
              "Roblox search filled the results with unrelated popular games. "
              "Report 'no matching experiences found'; do NOT use this CSV's "
              "visit or player totals.")

    path = os.path.join(out_dir, "roblox_games.csv")
    write_csv(path, rows)
    return len(rows)


def mark_brand_match(brand, rows):
    """Add a Brand Match column: brand term in Name, Creator, both, or neither.

    Matches any brand variant, so 'Chelsea 25/26 Home Kit' counts for a
    'Chelsea FC' run. The literal-input-only version marked 95% of a real
    catalogue as noise.
    """
    terms = [v.lower() for v in brand_variants(brand)]
    n = 0
    for r in rows:
        name_l = str(r.get("Name", "")).lower()
        creator_l = str(r.get("Creator", "")).lower()
        in_name = any(t in name_l for t in terms)
        in_creator = any(t in creator_l for t in terms)
        r["Brand Match"] = ("name+creator" if in_name and in_creator
                            else "name" if in_name
                            else "creator" if in_creator else "")
        n += 1 if r["Brand Match"] else 0
    return n


def report_short_name_share(brand, rows, n_match):
    """Say how many matches rest on the short name alone.

    'Chelsea' catches the club's kits and also a person called Chelsea. The
    count is still the right one to collect, but the analyst has to see the
    ambiguity rather than inherit it silently."""
    variants = brand_variants(brand)
    if len(variants) < 2 or not n_match:
        return
    full = variants[0].lower()
    short_only = sum(1 for r in rows if r.get("Brand Match")
                     and full not in str(r.get("Name", "")).lower()
                     and full not in str(r.get("Creator", "")).lower())
    if short_only:
        pct = round(100 * short_only / n_match)
        print(f'  NOTE: {short_only} of {n_match} matches ({pct}%) name only '
              f'"{variants[-1]}", not "{variants[0]}". Skim them before quoting: '
              f"the short name can belong to something else entirely.")


def grab_youtube(brand, api_key, out_dir, yt_pages=2):
    """YouTube presence per platform via the official Data API.

    Searches with the core brand name (fans title videos 'Chelsea', never
    'Chelsea (FC)') and paginates yt_pages deep. YouTube search is
    relevance-ranked and never exhaustive: whatever comes back is a top
    sample, so view totals built from it are floors, not totals.
    """
    core = brand_variants(brand)[-1]
    total = 0
    for platform in YT_PLATFORMS:
        rows, token = [], ""
        for _ in range(max(1, yt_pages)):
            params = {
                "part": "snippet", "q": f"{core} {platform}", "type": "video",
                "maxResults": 50, "key": api_key,
            }
            if token:
                params["pageToken"] = token
            q = urllib.parse.urlencode(params)
            data = http_json(f"https://www.googleapis.com/youtube/v3/search?{q}")
            ids = [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]
            stats = {}
            if ids:
                q2 = urllib.parse.urlencode({
                    "part": "statistics", "id": ",".join(ids), "key": api_key,
                })
                vdata = http_json(f"https://www.googleapis.com/youtube/v3/videos?{q2}")
                stats = {v["id"]: v.get("statistics", {}) for v in vdata.get("items", [])}
            for item in data.get("items", []):
                vid = item.get("id", {}).get("videoId")
                if not vid:
                    continue
                sn = item["snippet"]
                rows.append({
                    "Title": sn.get("title", ""),
                    "URL": f"https://www.youtube.com/watch?v={vid}",
                    "Video ID": vid,
                    "Creator": sn.get("channelTitle", ""),
                    "Creator URL": f"https://www.youtube.com/channel/{sn.get('channelId', '')}",
                    "Views": stats.get(vid, {}).get("viewCount", ""),
                    "Posted": (sn.get("publishedAt") or "")[:10],
                    "Platform": platform,
                })
            token = data.get("nextPageToken")
            if not token:
                break
            time.sleep(PAUSE_S)
        write_csv(os.path.join(out_dir, f"youtube_{platform}.csv"), rows)
        print(f"  youtube {platform}: {len(rows)} rows (top sample, not a census)")
        total += len(rows)
        time.sleep(PAUSE_S)
    return total


def write_csv(path, rows):
    if not rows:
        # still write the header-only file so downstream sees the slot existed
        open(path, "w").write("")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="GEEIQ brand check collector")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--out", default=None, help="output dir (default ./out/<brand>)")
    ap.add_argument("--pages", type=int, default=0,
                    help="cap on item pages per query (default 0: collect "
                         "everything until the cursor is exhausted)")
    ap.add_argument("--game-pages", type=int, default=10,
                    help="max experience-search pages per query (search "
                         "exhausts naturally well before this)")
    ap.add_argument("--yt-pages", type=int, default=2,
                    help="YouTube search pages per platform (50 videos each)")
    ap.add_argument("--no-auth", action="store_true", help="skip the Roblox cookie (returns empty results; for testing)")
    args = ap.parse_args()

    slug = re.sub(r"[^a-z0-9]+", "-", args.brand.lower()).strip("-")
    out_dir = args.out or os.path.join("out", slug)
    os.makedirs(out_dir, exist_ok=True)

    cookie = load_cookie(args)
    if not cookie and not args.no_auth:
        print("NOTE: no Roblox cookie found, continuing unauthenticated. This "
              "currently works; if results come back empty, add your cookie to "
              "~/.config/geeiq/roblosecurity and rerun.")

    variants = brand_variants(args.brand)
    print(f"Collecting for brand: {args.brand} -> {out_dir}")
    if len(variants) > 1:
        print(f"  querying as: {', '.join(variants)}")
    n_items, items_truncated = grab_items(args.brand, cookie, args.pages, out_dir)
    n_games = grab_games(args.brand, cookie, args.game_pages, out_dir)

    yt_key = os.environ.get("YOUTUBE_API_KEY")
    n_videos = 0
    if yt_key:
        n_videos = grab_youtube(args.brand, yt_key, out_dir, args.yt_pages)
    else:
        print("NOTE: YOUTUBE_API_KEY not set, skipping YouTube CSVs.")

    # Written next to the CSVs so the ceiling travels with the data, not just
    # in this log where a later reader will never see it.
    with open(os.path.join(out_dir, "collection_notes.json"), "w") as f:
        json.dump({"brand": args.brand, "queried_as": variants,
                   "items_truncated": items_truncated, "items": n_items,
                   "games": n_games, "videos": n_videos}, f, indent=2)

    status = "AT LEAST (a query hit a cap; see warnings above)" if items_truncated else "complete"
    print(f"Done. items={n_items} ({status}) games={n_games} videos={n_videos}")
    if items_truncated:
        print("Write the marketplace figures as 'at least N'. They are a floor.")
    if n_items == 0 and n_games == 0:
        print("Both Roblox sources came back empty. That usually means the "
              "cookie is missing or expired, so refresh it and rerun.")
        sys.exit(2)


if __name__ == "__main__":
    main()
