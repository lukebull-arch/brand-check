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
    """GET with patient retries. Datacenter IPs (CI runners) get rate limited
    aggressively, so back off exponentially and honour Retry-After."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    if cookie:
        req.add_header("Cookie", f".ROBLOSECURITY={cookie}")
    delay = 15
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 5:
                wait = max(delay, int(e.headers.get("Retry-After") or 0))
                print(f"  rate limited ({e.code}), waiting {wait}s (attempt {attempt + 1}/5)...")
                time.sleep(wait)
                delay = min(delay * 2, 120)
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


def grab_items(brand, cookie, pages, out_dir):
    """Marketplace items via catalog search API."""
    rows, cursor = [], ""
    for page in range(pages):
        q = urllib.parse.urlencode({"Keyword": brand, "Limit": 30, "Cursor": cursor})
        try:
            data = http_json(f"https://catalog.roblox.com/v1/search/items/details?{q}", cookie)
        except Exception as e:
            print(f"  items page {page + 1} failed ({e}); keeping {len(rows)} rows collected so far")
            break
        batch = data.get("data") or []
        for d in batch:
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
        print(f"  items page {page + 1}: {len(batch)} rows")
        if not cursor or not batch:
            break
        time.sleep(PAUSE_S)
    path = os.path.join(out_dir, "roblox_catalog_items.csv")
    write_csv(path, rows)
    return len(rows)


def grab_games(brand, cookie, pages, out_dir):
    """Experiences via the omni-search API the site itself uses."""
    rows, token = [], ""
    session = "geeiq-brand-check"
    for page in range(pages):
        q = urllib.parse.urlencode({
            "searchQuery": brand, "pageType": "all",
            "sessionId": session, "pageToken": token,
        })
        try:
            data = http_json(f"https://apis.roblox.com/search-api/omni-search?{q}", cookie)
        except Exception as e:
            print(f"  games page {page + 1} failed ({e}); keeping {len(rows)} rows collected so far")
            break
        batch = []
        for group in data.get("searchResults") or []:
            if group.get("contentGroupType") != "Game":
                continue
            batch.extend(group.get("contents") or [])
        for g in batch:
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
        token = data.get("nextPageToken")
        print(f"  games page {page + 1}: {len(batch)} rows")
        if not token or not batch:
            break
        time.sleep(PAUSE_S)

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
        print(f"  games enrichment: {min(i + 50, len(ids))}/{len(ids)}")
        time.sleep(PAUSE_S)
    for r in rows:  # ensure consistent columns even if a batch failed
        for col in ("Visits", "Favorites", "Creator Type", "Verified Creator"):
            r.setdefault(col, "")

    path = os.path.join(out_dir, "roblox_games.csv")
    write_csv(path, rows)
    return len(rows)


def grab_youtube(brand, api_key, out_dir):
    """YouTube presence per platform via the official Data API."""
    total = 0
    for platform in YT_PLATFORMS:
        rows = []
        q = urllib.parse.urlencode({
            "part": "snippet", "q": f"{brand} {platform}", "type": "video",
            "maxResults": 50, "key": api_key,
        })
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
        write_csv(os.path.join(out_dir, f"youtube_{platform}.csv"), rows)
        print(f"  youtube {platform}: {len(rows)} rows")
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
    ap.add_argument("--pages", type=int, default=5, help="max pages per Roblox source")
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

    print(f"Collecting for brand: {args.brand} -> {out_dir}")
    n_items = grab_items(args.brand, cookie, args.pages, out_dir)
    n_games = grab_games(args.brand, cookie, args.pages, out_dir)

    yt_key = os.environ.get("YOUTUBE_API_KEY")
    n_videos = 0
    if yt_key:
        n_videos = grab_youtube(args.brand, yt_key, out_dir)
    else:
        print("NOTE: YOUTUBE_API_KEY not set, skipping YouTube CSVs.")

    print(f"Done. items={n_items} games={n_games} videos={n_videos}")
    if n_items == 0 and n_games == 0:
        print("Both Roblox sources came back empty. That usually means the "
              "cookie is missing or expired, so refresh it and rerun.")
        sys.exit(2)


if __name__ == "__main__":
    main()
