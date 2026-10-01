#!/usr/bin/env python3
"""The GEEIQ platform check, run by the pipeline instead of by the reviewer.

Why this exists: the collector only sees marketplace listings and experience
names, and it decides "official" from strings. Licensed IP nearly always
reaches Roblox through a partner (Mr Bean through Cartoon Network Games, True
and the Rainbow Kingdom through cSapphire, Aston Martin inside Driving
Empire), so the string test says zero and the copy turned zero into "no
official presence". The platform already held the answer every time; nobody
asked it before the draft was written.

Two questions, both answered from the platform with the same bearer token the
MCP server uses:

1. Does the brand itself have partnership records? (resolve_entity over the
   MCP endpoint, then GET /partnerships?brand_id=.)
2. Do the Roblox-verified accounts issuing brand-named items resolve to a
   platform brand with partnerships? A verified group called "Cartoon Network
   Games" resolving to Cartoon Network, with item drops dated to the weeks the
   items were minted, is a licensed partner, not an imitator.

No token: the check is skipped and says so, and run.py falls closed (no
absence claim) on the verified-account signal alone. Token: GEEIQ_API_TOKEN,
or locally the geeiq MCP header in ~/.claude.json. It is a platform session
token and expires in about 30 days, so a 401/403 is "refresh the secret", not
a data finding.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request

MCP_URL = "https://game.api.geeiq.com/AI/mcp"
REST = "https://game.api.geeiq.com"
TIMEOUT = 30


def _loose(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def token():
    t = os.environ.get("GEEIQ_API_TOKEN")
    if t:
        return t.strip()
    # Local convenience only: the same token the geeiq MCP server is registered with.
    try:
        cfg = json.load(open(os.path.expanduser("~/.claude.json")))
        hdr = (((cfg.get("mcpServers") or {}).get("geeiq") or {}).get("headers") or {})
        auth = hdr.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth.split(None, 1)[1].strip()
        for proj in (cfg.get("projects") or {}).values():
            hdr = (((proj.get("mcpServers") or {}).get("geeiq") or {}).get("headers") or {})
            auth = hdr.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                return auth.split(None, 1)[1].strip()
    except Exception:
        pass
    return None


def _post_mcp(tok, method, params, rid=1):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(MCP_URL, data=body, headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode("utf-8", "replace")
    # Streamable HTTP answers as SSE ("event: message\ndata: {...}") or plain JSON.
    for line in raw.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(raw)


def _get_rest(tok, path):
    req = urllib.request.Request(REST + path, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def resolve_brand(tok, name):
    """Resolve a name to a platform brand. Exact title matches are accepted as
    they are. A fuzzy match is accepted only when one name contains the other
    once punctuation is stripped: "Cartoon Network Games" -> Cartoon Network
    and "Expedia" -> Expedia Group are right, "Tilted Tree Studios" -> whatever
    the index guesses is not."""
    out = _post_mcp(tok, "tools/call", {"name": "resolve_entity",
                                        "arguments": {"name": name, "type_hint": "brand"}})
    content = ((out.get("result") or {}).get("content") or [{}])[0].get("text") or "{}"
    j = json.loads(content)
    hit = j.get("resolved")
    if not hit or hit.get("type") != "brand":
        return None
    how = j.get("matched_by") or ""
    if how.startswith("title.exact"):
        return hit
    a, b = _loose(name), _loose(hit.get("title"))
    if a and b and (a in b or b in a):
        return hit
    return None


def partnerships(tok, brand_id):
    data = _get_rest(tok, f"/partnerships?brand_id={brand_id}&include=game&include=item_group&max_results=250")
    rows = []
    for r in data.get("data") or []:
        g = r.get("game") or {}
        sd = ((r.get("start_date") or {}).get("date") or "")[:10]
        ed = ((r.get("end_date") or {}).get("date") or "")[:10]
        rows.append({"id": r.get("id"), "game": g.get("name") or g.get("title") or "",
                     "type": r.get("sponsorship_type") or "", "start": sd, "end": ed})
    rows.sort(key=lambda x: x["start"], reverse=True)
    return rows


def _since(rows, days):
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return [r for r in rows if r["start"] and r["start"] >= cutoff]


def check(brand, creators=(), cache_path=None, aliases=()):
    """Return the platform view of the brand and of the verified accounts that
    issue its items. Never raises: the result carries `checked` and `error`."""
    if cache_path and os.path.exists(cache_path):
        try:
            cached = json.load(open(cache_path))
            if cached.get("brand") == brand and set(cached.get("creators_asked") or []) >= set(creators):
                return cached
        except Exception:
            pass
    res = {"brand": brand, "checked": False, "error": None, "brand_entity": None,
           "brand_partnerships": [], "brand_partnerships_2y": 0,
           "creators_asked": list(creators), "creator_matches": {},
           "checked_at": datetime.date.today().isoformat()}
    tok = token()
    if not tok:
        res["error"] = "no GEEIQ_API_TOKEN set; platform check skipped"
        return _save(res, cache_path)
    try:
        ent = resolve_brand(tok, brand)
        # A short or common name is ambiguous on the platform ("DC" returns
        # Events DC, DC Comics, D.C. United, AC/DC). The Wikidata label for the
        # same brand ("DC Comics") is the tie-break.
        for alias in aliases or ():
            if ent:
                break
            ent = resolve_brand(tok, alias)
            if ent:
                res["resolved_via"] = alias
        res["brand_entity"] = ent
        if ent:
            rows = partnerships(tok, ent["id"])
            res["brand_partnerships"] = rows[:40]
            res["brand_partnerships_2y"] = len(_since(rows, 730))
        for c in list(creators)[:8]:
            try:
                ent_c = resolve_brand(tok, c)
            except Exception as e:  # one bad name must not sink the check
                res["creator_matches"][c] = {"error": type(e).__name__}
                continue
            if not ent_c:
                res["creator_matches"][c] = None
                continue
            rows = partnerships(tok, ent_c["id"])
            drops = [r for r in rows if r["type"] == "item_owner"]
            res["creator_matches"][c] = {
                "brand": ent_c.get("title"), "brand_id": ent_c.get("id"),
                "partnerships_2y": len(_since(rows, 730)),
                "item_drops_2y": len(_since(drops, 730)),
                "latest": rows[0] if rows else None,
                "recent_drops": [r["start"] for r in _since(drops, 730)][:12],
            }
        res["checked"] = True
    except urllib.error.HTTPError as e:
        res["error"] = (f"platform returned HTTP {e.code}; "
                        + ("token expired or AI access denied, refresh GEEIQ_API_TOKEN"
                           if e.code in (401, 403) else "check skipped"))
    except Exception as e:
        res["error"] = f"platform check failed ({type(e).__name__}: {e})"
    return _save(res, cache_path)


def _save(res, path):
    if path:
        try:
            json.dump(res, open(path, "w"), indent=2)
        except Exception:
            pass
    return res


if __name__ == "__main__":
    import sys
    brand = sys.argv[1]
    creators = sys.argv[2:]
    print(json.dumps(check(brand, creators), indent=2))
