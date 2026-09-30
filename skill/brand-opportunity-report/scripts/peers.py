#!/usr/bin/env python3
"""Verify peer and category figures straight from the Roblox games API so a
report never quotes a number from memory or a press release.

    python3 scripts/peers.py --game "Spurs Adventure Arena" --game "Man City Blue Moon"
    python3 scripts/peers.py --place 9616411936 --group 2788849 --group-name "Bloxton Hotels"

--game        experience name; the first search result whose name contains it is used
--place       a place id from a roblox.com/games/<id>/... URL
--group       a group id; lists the group's public experiences and their visits
--group-name  searches groups by name, takes the closest match

Prints lifetime visits, players now, creator, verified badge and creation date,
and writes peers.json next to you. Group memberships are community sizes, not
players. Stdlib only, patient on 429.
"""
import argparse, json, re, time, urllib.parse, urllib.request

UA = {"User-Agent": "GEEIQ brand check (internal tool; luke.bull@geeiq.com)", "Accept": "application/json"}
PAUSE = 2.5


def get(url):
    delay = 12
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                time.sleep(delay); delay = min(delay * 2, 60); continue
            return {}
        except Exception:
            return {}
    return {}


def game_info(universe_ids):
    d = get("https://games.roblox.com/v1/games?universeIds=" + ",".join(str(u) for u in universe_ids))
    out = []
    for g in d.get("data") or []:
        c = g.get("creator") or {}
        out.append({"name": g.get("name"), "universe": g.get("id"), "place": g.get("rootPlaceId"),
                    "url": f"https://www.roblox.com/games/{g.get('rootPlaceId')}",
                    "visits": g.get("visits", 0), "playing": g.get("playing", 0),
                    "creator": c.get("name"), "creator_type": c.get("type"),
                    "verified": bool(c.get("hasVerifiedBadge")), "created": (g.get("created") or "")[:10]})
    return out


def show(r, label=""):
    print(f"  {r['visits']:>13,} visits | {r['playing']:>5,} playing | {r['name'][:46]:46} | {r['creator']} ({r['creator_type']}{', verified' if r['verified'] else ''}) | since {r['created']} | {r['url']}{'  <- ' + label if label else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", action="append", default=[])
    ap.add_argument("--place", action="append", default=[], type=int)
    ap.add_argument("--group", action="append", default=[], type=int)
    ap.add_argument("--group-name", action="append", default=[])
    ap.add_argument("--out", default="peers.json")
    a = ap.parse_args()
    results = {"games": [], "groups": []}

    for name in a.game:
        d = get("https://apis.roblox.com/search-api/omni-search?" + urllib.parse.urlencode(
            {"searchQuery": name, "pageType": "all", "sessionId": "geeiq-peers"}))
        hits = [c for grp in d.get("searchResults") or [] if grp.get("contentGroupType") == "Game"
                for c in grp.get("contents") or [] if name.lower() in (c.get("name") or "").lower()]
        if not hits:
            print(f"  no experience found whose name contains '{name}' (search pads with unrelated games; try --place with the URL)")
            time.sleep(PAUSE); continue
        time.sleep(PAUSE)
        for r in game_info([hits[0]["universeId"]]):
            show(r, f"searched '{name}'"); results["games"].append(r)
        time.sleep(PAUSE)

    for place in a.place:
        u = get(f"https://apis.roblox.com/universes/v1/places/{place}/universe")
        if not u.get("universeId"):
            print(f"  place {place}: no universe found"); continue
        time.sleep(PAUSE)
        for r in game_info([u["universeId"]]):
            show(r, f"place {place}"); results["games"].append(r)
        time.sleep(PAUSE)

    group_ids = list(a.group)
    for gname in a.group_name:
        d = get("https://groups.roblox.com/v1/groups/search?keyword=" + urllib.parse.quote(gname) + "&limit=10")
        cands = d.get("data") or []
        best = next((g for g in cands if g["name"].strip().lower().startswith(gname.lower()[:8])), cands[0] if cands else None)
        if not best:
            print(f"  no group found for '{gname}'"); continue
        print(f"  group '{gname}' -> {best['name']} (id {best['id']}, {best.get('memberCount', 0):,} members, verified {best.get('hasVerifiedBadge')})")
        group_ids.append(best["id"]); time.sleep(PAUSE)

    for gid in group_ids:
        g = get(f"https://groups.roblox.com/v1/groups/{gid}")
        d = get(f"https://games.roblox.com/v2/groups/{gid}/games?accessFilter=2&limit=50")
        ids = [x["id"] for x in d.get("data") or []]
        time.sleep(PAUSE)
        games = game_info(ids[:50]) if ids else []
        entry = {"id": gid, "name": g.get("name"), "members": g.get("memberCount", 0),
                 "verified": bool(g.get("hasVerifiedBadge")), "games": games,
                 "visits_total": sum(x["visits"] for x in games)}
        print(f"  group {entry['name']} | {entry['members']:,} members{' | verified' if entry['verified'] else ''} | {len(games)} public experiences | {entry['visits_total']:,} visits")
        for r in sorted(games, key=lambda x: -x["visits"])[:6]:
            show(r)
        results["groups"].append(entry); time.sleep(PAUSE)

    json.dump(results, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {a.out}. Lifetime visits are host-experience totals: attribute them to the brand only when the brand owns the experience.")


if __name__ == "__main__":
    main()
