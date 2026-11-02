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

Brand-name variants: official accounts rarely match the submitted string
exactly ("Pizza Hut Official" runs The Hut, not "Pizza Hut"). So every
search runs the submitted name, the base name with a trailing "official"
stripped, and base + "official". When an official-looking creator turns up
in the item results, their full store and their group's experiences are
pulled too, so official items and experiences no longer depend on keyword
luck.
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
PAGE_SIZE = 120     # v1/search/items returns ids 120 at a time; details come in one POST per page
PAGE_CEILING = 12   # 12 x 120 = 1,440 rows, past Roblox's own per-query ceiling
QUERY_CAP_HINT = 960  # a query ending at or above this almost certainly hit that cap
PAUSE_S = 1.2
COOKIE_PATH = os.path.expanduser("~/.config/geeiq/roblosecurity")
YT_PLATFORMS = ["roblox", "fortnite", "minecraft"]


# Adaptive pacing. A residential IP gets a 429 every hundred requests or so;
# a GitHub runner got one on nearly every page and then sat through a
# 15/30/60 s cascade per page (a proof run spent 2,400 s on 38 pages). The
# cheapest request is the one not sent: after a 429 the gap between requests
# grows and stays grown while the limiter keeps biting, and shrinks slowly
# once requests succeed again.
_pace = {"gap": 0.0, "last": 0.0}
PACE_MAX = 40.0


def _wait_turn():
    due = _pace["last"] + _pace["gap"]
    now = time.monotonic()
    if due > now:
        time.sleep(due - now)
    _pace["last"] = time.monotonic()


def _paced_ok():
    _pace["gap"] = max(0.0, _pace["gap"] * 0.85) if _pace["gap"] > 1.0 else 0.0


def _paced_limited():
    _pace["gap"] = min(PACE_MAX, max(8.0, _pace["gap"] * 2))


def _request(req):
    """Send with patient retries. Honours Retry-After, backs off on 429/503,
    and feeds the adaptive pace either way."""
    delay = 10
    for attempt in range(6):
        _wait_turn()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _paced_ok()
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 5:
                _paced_limited()
                wait = max(delay, int(e.headers.get("Retry-After") or 0))
                print(f"    rate limited ({e.code}), waiting {wait}s, pace now "
                      f"{_pace['gap']:.0f}s (attempt {attempt + 1}/5)...")
                time.sleep(wait)
                delay = min(delay * 2, 90)
                continue
            raise
    return None


def http_json(url, cookie=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    if cookie:
        req.add_header("Cookie", f".ROBLOSECURITY={cookie}")
    return _request(req)


_csrf = {"token": ""}


def http_post_json(url, body, cookie=None):
    """POST with Roblox's CSRF handshake: the first call answers 403 with the
    token to use, and the token is reused until it stops working."""
    for _ in range(2):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"User-Agent": UA, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        if _csrf["token"]:
            req.add_header("X-CSRF-TOKEN", _csrf["token"])
        if cookie:
            req.add_header("Cookie", f".ROBLOSECURITY={cookie}")
        try:
            return _request(req)
        except urllib.error.HTTPError as e:
            tok = e.headers.get("x-csrf-token") if e.code == 403 else None
            if tok and tok != _csrf["token"]:
                _csrf["token"] = tok
                continue
            raise
    return None


def item_details(ids, cookie=None):
    """Full rows for up to 120 (id, itemType) pairs in one call."""
    if not ids:
        return []
    data = http_post_json("https://catalog.roblox.com/v1/catalog/items/details",
                          {"items": [{"itemType": t, "id": i} for i, t in ids]}, cookie)
    return (data or {}).get("data") or []


def load_cookie(args):
    if args.no_auth:
        return None
    if os.environ.get("ROBLOSECURITY"):
        return os.environ["ROBLOSECURITY"].strip()
    if os.path.exists(COOKIE_PATH):
        return open(COOKIE_PATH).read().strip()
    return None


def _norm(s):
    """Lowercase with spacing removed, so 'Pizza Hut' and 'PizzaHut' are one
    account. Punctuation and symbols stay significant: this decides whose whole
    store gets pulled, and "Gregg's TM" is not Greggs. Kept identical to the
    rule in report/run.py, because the two drifting apart is how an imitator
    ends up in a brand's own figures."""
    return re.sub(r"\s+", "", (s or "").strip().lower())


ORG_SUFFIXES = {"fc", "afc", "cf", "sc", "plc", "ag", "inc", "ltd", "llc",
                "gmbh", "sa", "co", "group"}


def brand_queries(brand):
    """Every name the brand's content actually appears under: the submitted
    string, the same string with brackets and a company suffix removed, the
    base name with a trailing 'official' stripped, and base + 'official'.

    The bracket and suffix stripping matters as much as the pagination fix:
    fans title a kit 'Chelsea 25/26 Home', never 'Chelsea (FC) 25/26 Home',
    so a submitted 'Chelsea FC' that only ever queries itself misses the
    catalogue it was sent to find."""
    b = " ".join(brand.split())
    plain = " ".join(re.sub(r"\s*\([^)]*\)", "", b).split()) or b
    words = plain.split()
    if len(words) > 1 and words[-1].lower().strip(".") in ORG_SUFFIXES:
        plain = " ".join(words[:-1])
    base = re.sub(r"\s*official\s*$", "", plain, flags=re.I).strip() or plain
    queries, seen = [], set()
    # Fans drop apostrophes ("McDonalds", "Dominos"), and Roblox search treats
    # the two spellings as different queries, so both must be swept.
    import unicodedata
    cands = [b, plain, base, f"{base} official"]
    cands += [c.replace("'", "") for c in list(cands) if "'" in c]
    cands += [f for f in (unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
              for c in list(cands)) if f and f not in cands]
    for q in cands:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    return base, queries


def official_creator_norms(brand):
    """Normalised creator names that count as the brand's own account."""
    base, _ = brand_queries(brand)
    n = _norm(base)
    return {n, n + "official", _norm(brand)} - {""}


def item_row(d):
    kind = "bundles" if d.get("itemType") == "Bundle" else "catalog"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", d.get("name", "")).strip("-") or "item"
    return {
        "Name": d.get("name", ""),
        "ID": d.get("id", ""),
        "URL": f"https://www.roblox.com/{kind}/{d.get('id')}/{slug}",
        "Creator": d.get("creatorName", ""),
        "Creator Type": d.get("creatorType", ""),
        "Creator ID": d.get("creatorTargetId", ""),
        # Roblox's own badge. It cannot classify an account on its own (verified
        # UGC studios make fan items too), but it is the one signal an imitator
        # cannot award itself, so the report may not claim absence over it.
        "Creator Verified": "yes" if d.get("creatorHasVerifiedBadge") else "",
        "Price": d.get("price", ""),
        "Favorites": d.get("favoriteCount", ""),
        "Item Type": d.get("itemType", ""),
        "Created": (d.get("itemCreatedUtc") or "")[:10],
    }


def grab_items(brand, cookie, pages, out_dir, budget_s=0):
    """Marketplace items via catalog search API, across brand-name variants,
    then the full store of any official-looking creator found."""
    base, queries = brand_queries(brand)
    off_norms = official_creator_norms(brand)
    rows, seen = [], set()

    def add(d):
        r = item_row(d)
        key = str(r["ID"])
        if key and key not in seen:
            seen.add(key)
            rows.append(r)
            return 1
        return 0

    truncated = []
    # Exhaustive pulls plus rate-limit backoffs can outlast the CI job. Stop on
    # a clock rather than being killed mid-run: a labelled floor still ships a
    # report, a killed job ships nothing.
    deadline = (time.monotonic() + budget_s) if budget_s else None
    # Roblox caps a single query at ~1,000 rows PER SORT ORDER, and each sort
    # exposes a different window of the index: sweeping four sorts on an
    # Aston Villa run lifted matched items 17% over the default sort alone.
    # Each (query, sort) pair paginates to exhaustion and rows dedupe by ID.
    SORTS = ("", "1", "2", "3")
    plan = [(q, s) for q in queries for s in SORTS]
    for idx, (query, sort) in enumerate(plan):
        qlabel = f"{query}" + (f" [sort {sort}]" if sort else "")
        if deadline and time.monotonic() > deadline:
            truncated.append(f"the '{qlabel}' search never ran: the collection "
                             f"time budget ran out first")
            print(f"  WARNING: time budget spent, skipping query '{qlabel}'")
            continue
        # Fair share of what is left, so the sort sweeps and the "official"
        # query always get their turn instead of the first query eating the
        # whole budget. Time a query does not use rolls over to the next.
        q_deadline = None
        if deadline:
            remaining_q = len(plan) - idx
            q_deadline = time.monotonic() + (deadline - time.monotonic()) / remaining_q
        cursor, page, fetched = "", 0, 0
        while True:
            page += 1
            # Two calls per page: 120 ids from the search index, then their
            # details in one POST. The details-search endpoint only pages 30
            # at a time, which cost four times the requests for the same rows.
            params = {"Keyword": query, "Limit": PAGE_SIZE, "Cursor": cursor}
            if sort:
                params["SortType"] = sort
            q = urllib.parse.urlencode(params)
            try:
                data = http_json(f"https://catalog.roblox.com/v1/search/items?{q}", cookie)
                ids = [(d.get("id"), d.get("itemType") or "Asset")
                       for d in (data.get("data") or []) if d.get("id")]
                batch = item_details(ids, cookie)
            except Exception as e:
                print(f"  items '{qlabel}' page {page} failed ({e}); keeping {len(rows)} rows collected so far")
                truncated.append(f"the '{qlabel}' search stopped early on an API error")
                break
            added = sum(add(d) for d in batch)
            fetched += len(batch)
            cursor = data.get("nextPageCursor")
            print(f"  items '{qlabel}' page {page}: {len(batch)} rows ({added} new, {len(rows)} total)")
            if not cursor or not batch:
                break
            if pages and page >= pages:
                truncated.append(f"the '{query}' search stopped at the {pages}-page limit "
                                 f"with more results available")
                print(f"  WARNING: '{query}' stopped at the --pages limit ({pages}) with a "
                      f"live cursor. Counts are a truncated sample, not a total.")
                break
            if page >= PAGE_CEILING:
                truncated.append(f"the '{query}' search stopped at the {PAGE_CEILING}-page "
                                 f"safety ceiling with more results available")
                print(f"  WARNING: '{query}' hit the {PAGE_CEILING}-page ceiling with a live cursor.")
                break
            if q_deadline and time.monotonic() > q_deadline:
                truncated.append(f"the '{qlabel}' search stopped after {page} pages: its "
                                 f"share of the collection time budget ran out with more "
                                 f"results available")
                print(f"  WARNING: budget share spent mid-'{qlabel}' at page {page}. "
                      f"Counts are a floor.")
                break
            time.sleep(PAUSE_S)
        if fetched >= QUERY_CAP_HINT:
            truncated.append(f"the '{qlabel}' search reached Roblox's ~1,000-row limit for a "
                             f"single query, so more items exist than were collected")
            print(f"  NOTE: '{qlabel}' returned {fetched} rows, Roblox's ~1,000-row cap for one "
                  f"query and sort. Treat the item count as a floor.")
        time.sleep(PAUSE_S)

    # Official creators found in the results: pull their whole store so
    # official items do not depend on the keyword ranking.
    officials, seen_off = [], set()
    for r in rows:
        if _norm(r["Creator"]) in off_norms and r.get("Creator ID"):
            key = str(r["Creator ID"])
            if key not in seen_off:
                seen_off.add(key)
                officials.append({"id": key, "type": r["Creator Type"], "name": r["Creator"]})
    for off in officials[:3]:
        ct = 2 if str(off["type"]).lower() == "group" else 1
        cursor, got, page = "", 0, 0
        while page < PAGE_CEILING:
            page += 1
            q = urllib.parse.urlencode({"CreatorTargetId": off["id"], "CreatorType": ct,
                                        "Limit": 30, "Cursor": cursor})
            try:
                data = http_json(f"https://catalog.roblox.com/v1/search/items/details?{q}", cookie)
            except Exception as e:
                print(f"  store of {off['name']} page {page} failed ({e}); continuing")
                break
            batch = data.get("data") or []
            got += sum(add(d) for d in batch)
            cursor = data.get("nextPageCursor")
            if not cursor or not batch:
                break
            time.sleep(PAUSE_S)
        print(f"  official store {off['name']}: {got} additional rows")
        time.sleep(PAUSE_S)

    path = os.path.join(out_dir, "roblox_catalog_items.csv")
    write_csv(path, rows)
    return len(rows), officials, truncated


def game_row_from_search(g):
    up = g.get("totalUpVotes") or 0
    down = g.get("totalDownVotes") or 0
    like = round(100 * up / (up + down)) if (up + down) > 0 else "N/A"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", g.get("name", "")).strip("-") or "game"
    return {
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
    }


def grab_games(brand, cookie, pages, out_dir, officials=None):
    """Experiences via the omni-search API across brand-name variants, plus
    every experience owned by official groups found in the item scan (this is
    what catches activations whose names never mention the brand, like The
    Hut for Pizza Hut Official)."""
    _, queries = brand_queries(brand)
    rows, seen = [], set()

    def add(row):
        key = str(row.get("Universe ID") or row.get("ID"))
        if key and key != "None" and key not in seen:
            seen.add(key)
            rows.append(row)
            return 1
        return 0

    session = "geeiq-brand-check"
    for query in queries:
        token = ""
        for page in range(pages):
            q = urllib.parse.urlencode({
                "searchQuery": query, "pageType": "all",
                "sessionId": session, "pageToken": token,
            })
            try:
                data = http_json(f"https://apis.roblox.com/search-api/omni-search?{q}", cookie)
            except Exception as e:
                print(f"  games '{query}' page {page + 1} failed ({e}); keeping {len(rows)} rows collected so far")
                break
            batch = []
            for group in data.get("searchResults") or []:
                if group.get("contentGroupType") != "Game":
                    continue
                batch.extend(group.get("contents") or [])
            added = sum(add(game_row_from_search(g)) for g in batch)
            token = data.get("nextPageToken")
            print(f"  games '{query}' page {page + 1}: {len(batch)} rows ({added} new)")
            if not token or not batch:
                break
            time.sleep(PAUSE_S)
        time.sleep(PAUSE_S)

    # Official groups' own experiences, regardless of what they are called.
    for off in (officials or [])[:3]:
        if str(off.get("type", "")).lower() != "group":
            continue
        try:
            data = http_json(f"https://games.roblox.com/v2/groups/{off['id']}/games"
                             f"?accessFilter=2&limit=50", cookie)
        except Exception as e:
            print(f"  group games for {off['name']} failed ({e}); continuing")
            continue
        got = 0
        for g in data.get("data") or []:
            place = (g.get("rootPlace") or {}).get("id", "")
            slug = re.sub(r"[^A-Za-z0-9]+", "-", g.get("name", "")).strip("-") or "game"
            got += add({
                "Name": g.get("name", ""),
                "ID": place,
                "Universe ID": g.get("id", ""),
                "URL": f"https://www.roblox.com/games/{place}/{slug}",
                "Like %": "N/A",
                "Active Players": 0,
                "Creator": off["name"],
                "Up Votes": 0,
                "Down Votes": 0,
                "Sponsored": "",
            })
        print(f"  group games {off['name']}: {got} additional rows")
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
            row["Creator"] = creator.get("name", "") or row.get("Creator", "")
            row["Creator Type"] = creator.get("type", "")
            row["Verified Creator"] = "yes" if creator.get("hasVerifiedBadge") else ""
            # Brand-sanctioned activations often run under a partner studio's
            # account ("Formula E - Electric Lap"), so the creator name proves
            # nothing. The description is where the partnership is declared.
            # Stored raw; report/run.py decides what counts.
            row["Description"] = re.sub(r"\s+", " ", (g.get("description") or ""))[:2000]
            if not row.get("Active Players"):
                row["Active Players"] = g.get("playing", 0) or 0
        # Fill missing like ratios (group-sourced rows have none from search).
        try:
            vdata = http_json(f"https://games.roblox.com/v1/games/votes?universeIds={chunk}", cookie)
            for v in vdata.get("data") or []:
                row = by_universe.get(str(v.get("id")))
                if row and row.get("Like %") in ("N/A", "", None):
                    up = v.get("upVotes") or 0
                    down = v.get("downVotes") or 0
                    row["Like %"] = round(100 * up / (up + down)) if (up + down) > 0 else "N/A"
                    row["Up Votes"] = up
                    row["Down Votes"] = down
        except Exception as e:
            print(f"  votes enrichment batch failed ({e}); continuing")
        print(f"  games enrichment: {min(i + 50, len(ids))}/{len(ids)}")
        time.sleep(PAUSE_S)
    for r in rows:  # ensure consistent columns even if a batch failed
        for col in ("Visits", "Favorites", "Creator Type", "Verified Creator",
                    "Description"):
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
    # A two-hour crawl once died at this line because the out dir was missing.
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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
                    help="cap on marketplace pages per query (default 0: keep "
                         "paginating until Roblox stops returning a cursor)")
    ap.add_argument("--game-pages", type=int, default=10,
                    help="max experience-search pages per query")
    ap.add_argument("--budget-seconds", type=int, default=int(os.environ.get("GRAB_BUDGET_S", "0")),
                    help="wall-clock budget for the marketplace pull (0: no "
                         "limit). On timeout it stops cleanly and records the "
                         "counts as a floor instead of being killed.")
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
    n_items, officials, truncated = grab_items(args.brand, cookie, args.pages, out_dir,
                                               args.budget_seconds)
    if officials:
        print(f"  official creators found: {', '.join(o['name'] for o in officials)}")
    n_games = grab_games(args.brand, cookie, args.game_pages, out_dir, officials)

    yt_key = os.environ.get("YOUTUBE_API_KEY")
    n_videos = 0
    if yt_key:
        n_videos = grab_youtube(args.brand, yt_key, out_dir)
    else:
        print("NOTE: YOUTUBE_API_KEY not set, skipping YouTube CSVs.")

    # Hand the ceilings downstream. A truncated pull that reads as a finished
    # report is the failure this file exists to prevent, so the fact travels
    # with the data rather than living only in this log.
    with open(os.path.join(out_dir, "collection_notes.json"), "w") as f:
        json.dump({"items_truncated": bool(truncated), "reasons": truncated,
                   "items": n_items, "games": n_games, "videos": n_videos}, f, indent=2)

    print(f"Done. items={n_items} games={n_games} videos={n_videos}")
    if truncated:
        print("ITEM COUNT IS A FLOOR, not a total:")
        for reason in truncated:
            print(f"  - {reason}")
    if n_items == 0 and n_games == 0:
        print("Both Roblox sources came back empty. That usually means the "
              "cookie is missing or expired, so refresh it and rerun.")
        sys.exit(2)


if __name__ == "__main__":
    main()
