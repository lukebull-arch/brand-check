#!/usr/bin/env python3
"""Reach a brand's Roblox footprint when Roblox search returns nothing for the
brand name itself.

Some marks come back empty from every catalog and experience search that
contains them (seen on Nike, Aston Martin, Rolls Royce and BMW), while the fan
items plainly exist. This script goes round that: it searches the slang and
model names fans use instead, sweeps the stores of the creators it finds, and
lists the groups that carry the name and their public experiences.

    python3 scripts/grab_hidden.py --brand BMW --alias bimmer --alias beamer \
        --query "e30 m3" --query "m3 gtr" --out out/bmw-hidden

Everything it prints is a floor. Write it up as "reachable through slang and
model codes", say that the brand name itself returns nothing from search, and
do not claim to know why: the cause is not established.

Outputs: items.csv, groups.csv, group_games.csv, collection_notes.json.
Stdlib only, one request at a time, backs off on 429.
"""
import argparse, csv, json, os, re, time, urllib.parse, urllib.request
from collections import Counter

UA = {"User-Agent": "GEEIQ brand check (internal tool; luke.bull@geeiq.com)", "Accept": "application/json"}
PAUSE = 3.0


def get(url):
    delay = 12
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 5:
                print(f"   {e.code}, waiting {delay}s", flush=True)
                time.sleep(delay); delay = min(delay * 2, 90); continue
            print(f"   HTTP {e.code} on {url[:80]}", flush=True); return {}
        except Exception as e:
            print(f"   error {e}", flush=True); return {}
    return {}


def catalog(params, pages):
    out, cur, capped = [], "", False
    for _ in range(pages):
        q = dict(params); q["Limit"] = 30
        if cur: q["Cursor"] = cur
        d = get("https://catalog.roblox.com/v1/search/items/details?" + urllib.parse.urlencode(q))
        rows = d.get("data") or []
        out += rows; cur = d.get("nextPageCursor")
        if not cur or not rows: break
        time.sleep(PAUSE)
    else:
        capped = bool(cur)
    return out, capped


def token_re(words):
    alts = [re.escape(w.strip()).replace(r"\ ", r"\s*") for w in words if w.strip()]
    return re.compile(r"(?i)(?<![a-z0-9])(" + "|".join(alts) + r")(?![a-z0-9])")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True, help="the brand name as it should appear in item titles")
    ap.add_argument("--alias", action="append", default=[], help="slang or nickname fans use (repeatable)")
    ap.add_argument("--query", action="append", default=[], help="extra search phrase, e.g. a model code (repeatable)")
    ap.add_argument("--pages", type=int, default=10, help="pages of 30 per query (default 10, a floor)")
    ap.add_argument("--stores", type=int, default=10, help="how many creators' stores to sweep")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join("out", re.sub(r"[^a-z0-9]+", "-", a.brand.lower()).strip("-") + "-hidden")
    os.makedirs(out, exist_ok=True)

    strict = token_re([a.brand])
    keepers = token_re([a.brand] + a.alias + a.query)
    queries = list(dict.fromkeys(a.alias + a.query + [a.brand]))
    items, notes = {}, {"brand": a.brand, "queries": queries, "pages_cap": a.pages, "capped_queries": [], "empty_queries": []}

    def add(r, src):
        if r["id"] in items:
            items[r["id"]]["sources"].add(src); return
        items[r["id"]] = {"Name": r.get("name", ""), "ID": r["id"],
                          "URL": f"https://www.roblox.com/catalog/{r['id']}",
                          "Creator": r.get("creatorName", ""), "Creator Type": r.get("creatorType", ""),
                          "Creator ID": r.get("creatorTargetId", ""), "Price": r.get("price", ""),
                          "Favorites": r.get("favoriteCount") or 0, "sources": {src}}

    def save_items():
        with open(os.path.join(out, "items.csv"), "w", newline="") as f:
            cols = ["Name", "ID", "URL", "Creator", "Creator Type", "Creator ID", "Price", "Favorites", "Sources", "Named"]
            w = csv.writer(f); w.writerow(cols)
            for it in sorted(items.values(), key=lambda x: -int(x["Favorites"])):
                w.writerow([it[c] for c in cols[:8]] + ["|".join(sorted(it["sources"])), "yes" if strict.search(it["Name"]) else ""])

    print("== keyword sweep", flush=True)
    for q in queries:
        rows, capped = catalog({"Keyword": q}, a.pages)
        kept = [r for r in rows if keepers.search(r.get("name", ""))]
        for r in kept: add(r, f"kw:{q}")
        if capped: notes["capped_queries"].append(q)
        if not rows: notes["empty_queries"].append(q)
        print(f"  '{q}': {len(rows)} rows, {len(kept)} kept{' (more available, capped)' if capped else ''}{' (EMPTY: search returns nothing for this phrase)' if not rows else ''}", flush=True)
        save_items(); time.sleep(PAUSE)

    print("== creator store sweep", flush=True)
    cnt = Counter((it["Creator Type"], it["Creator ID"], it["Creator"]) for it in items.values() if it["Creator ID"])
    hidden = 0
    for (ctype, cid, cname), n in cnt.most_common(a.stores):
        rows, capped = catalog({"CreatorTargetId": cid, "CreatorType": ctype}, a.pages)
        kept = [r for r in rows if keepers.search(r.get("name", ""))]
        named = [r for r in kept if strict.search(r.get("name", ""))]
        hidden += len(named)
        for r in kept: add(r, f"store:{cname}")
        print(f"  {cname[:28]:28} {len(rows):>4} items, {len(kept):>3} kept, {len(named):>3} carry the brand name{' (capped)' if capped else ''}", flush=True)
        save_items(); time.sleep(PAUSE)
    named_total = sum(1 for it in items.values() if strict.search(it["Name"]))
    notes.update({"items_total": len(items), "items_named": named_total,
                  "favourites": sum(int(i["Favorites"]) for i in items.values()),
                  "creators": len({i["Creator"] for i in items.values()})})
    print(f"== ITEMS: {len(items)} kept, {named_total} carry the brand name, favourites {notes['favourites']:,}, creators {notes['creators']}", flush=True)

    print("== groups", flush=True)
    groups = {}
    for q in list(dict.fromkeys([a.brand] + a.alias)):
        d = get("https://groups.roblox.com/v1/groups/search?keyword=" + urllib.parse.quote(q) + "&limit=25")
        for g in d.get("data") or []:
            if keepers.search(g.get("name", "")):
                groups[g["id"]] = {"id": g["id"], "name": g["name"], "members": g.get("memberCount", 0),
                                   "verified": g.get("hasVerifiedBadge", False)}
        time.sleep(PAUSE)
    with open(os.path.join(out, "groups.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["id", "name", "members", "verified"])
        for g in sorted(groups.values(), key=lambda x: -x["members"]): w.writerow([g["id"], g["name"], g["members"], g["verified"]])
    print(f"== GROUPS: {len(groups)} named, {sum(g['members'] for g in groups.values()):,} memberships (community sizes, not players)", flush=True)

    print("== group games", flush=True)
    gg = []
    for g in sorted(groups.values(), key=lambda x: -x["members"])[:12]:
        d = get(f"https://games.roblox.com/v2/groups/{g['id']}/games?accessFilter=2&limit=50")
        ids = [str(x["id"]) for x in d.get("data") or []]
        time.sleep(PAUSE)
        if ids:
            info = get("https://games.roblox.com/v1/games?universeIds=" + ",".join(ids[:50]))
            for x in info.get("data") or []:
                gg.append({"group": g["name"], "group_members": g["members"], "name": x["name"], "visits": x.get("visits", 0),
                           "playing": x.get("playing", 0), "created": (x.get("created") or "")[:10], "universe": x["id"],
                           "url": f"https://www.roblox.com/games/{x.get('rootPlaceId')}"})
            time.sleep(PAUSE)
        print(f"  {g['name'][:30]:30} {g['members']:>9,} members, {len(ids)} games, {sum(x['visits'] for x in gg if x['group'] == g['name']):,} visits", flush=True)
    with open(os.path.join(out, "group_games.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group", "group_members", "name", "visits", "playing", "created", "universe", "url"]); w.writeheader()
        for r in sorted(gg, key=lambda x: -x["visits"]): w.writerow(r)
    json.dump(notes, open(os.path.join(out, "collection_notes.json"), "w"), indent=1)
    print(f"== DONE. Wrote {out}/items.csv, groups.csv, group_games.csv, collection_notes.json", flush=True)
    print("   Every count is a floor. Quote as reachable through slang and model codes, not as a total.")


if __name__ == "__main__":
    main()
