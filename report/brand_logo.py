#!/usr/bin/env python3
"""Fetch a brand's logo for the report header.

Wikidata first: the P154 "logo image" claim points at a Commons file, which
Commons will render to PNG at whatever width we ask for. That gives a real
wordmark with transparency rather than a square favicon.

Falls back to Google's favicon service, which always answers but often with a
low-resolution icon. Returns None rather than guessing if neither works: a
report with no logo looks fine, a report with the wrong brand's logo does not.

Every lookup reports what it matched (entity id, label, description) so the
analyst can sanity-check it in the summary before approving.
"""
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "GEEIQ brand check (internal tool; luke.bull@geeiq.com)"}
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".logo_cache")
RENDER_WIDTH = 700
MAX_BYTES = 4_000_000


def _get(url, timeout=20, retries=2):
    """GET with a polite retry: Wikimedia rate limits bursts with a 429."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    return None


def _json(url):
    raw = _get(url)
    return json.loads(raw.decode()) if raw else None


def _wikidata_entity(brand):
    q = urllib.parse.urlencode({
        "action": "wbsearchentities", "search": brand, "language": "en",
        "format": "json", "limit": 5, "type": "item"})
    data = _json(f"https://www.wikidata.org/w/api.php?{q}")
    for hit in (data or {}).get("search", []):
        # Prefer a hit whose label matches the brand closely; the first result
        # is usually right but "Apple" style collisions are worth guarding.
        label = (hit.get("label") or "").lower()
        if label == brand.lower() or brand.lower() in label:
            return hit
    return ((data or {}).get("search") or [None])[0]


def _logo_filename(qid):
    q = urllib.parse.urlencode({
        "action": "wbgetclaims", "entity": qid, "property": "P154", "format": "json"})
    data = _json(f"https://www.wikidata.org/w/api.php?{q}")
    claims = (data or {}).get("claims", {}).get("P154") or []
    for claim in claims:
        try:
            return claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
    return None


def _commons_render(filename, width=RENDER_WIDTH):
    safe = urllib.parse.quote(filename.replace(" ", "_"))
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width={width}"
    return _get(url, timeout=30)


def _looks_like_image(raw):
    return bool(raw) and len(raw) < MAX_BYTES and raw[:8] in (
        b"\x89PNG\r\n\x1a\n",) or (raw or b"")[:3] == b"\xff\xd8\xff"


def fetch(brand, out_dir=None):
    """Return {"path", "source", "matched", "is_light"} or None."""
    out_dir = out_dir or CACHE
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-") or "brand"
    path = os.path.join(out_dir, f"{slug}.png")
    meta_path = os.path.join(out_dir, f"{slug}.json")

    if os.path.exists(path) and os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path))
            meta["path"] = path
            return meta
        except Exception:
            pass

    raw, source, matched = None, None, None

    # 1. Wikidata -> Commons: a real logo
    try:
        hit = _wikidata_entity(brand)
        if hit:
            qid = hit["id"]
            matched = f"{hit.get('label', qid)} ({hit.get('description', 'no description')}) [{qid}]"
            fname = _logo_filename(qid)
            if fname:
                candidate = _commons_render(fname)
                if _looks_like_image(candidate):
                    raw, source = candidate, f"Wikidata P154: {fname}"
    except Exception as e:
        print(f"   logo: wikidata lookup failed ({type(e).__name__})")

    # 2. Favicon fallback: always answers, quality varies
    if not raw:
        domain = f"{slug.replace('-', '')}.com"
        try:
            candidate = _get(
                f"https://www.google.com/s2/favicons?domain={domain}&sz=256")
            if _looks_like_image(candidate):
                raw, source = candidate, f"favicon: {domain}"
        except Exception as e:
            print(f"   logo: favicon lookup failed ({type(e).__name__})")

    if not raw:
        return None

    # Normalise and work out whether it needs a dark backing plate: a
    # white-on-transparent logo is invisible on our off-white page.
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        if im.width < 32 or im.height < 32:
            return None  # too small to look like anything but a smudge
        px = im.getdata()
        lum, count = 0.0, 0
        for r, g, b, a in px:
            if a > 40:
                lum += (0.299 * r + 0.587 * g + 0.114 * b) / 255
                count += 1
        is_light = count > 0 and (lum / count) > 0.72
        if im.width > 1200:
            im = im.resize((1200, round(1200 * im.height / im.width)), Image.LANCZOS)
        im.save(path)
        w, h = im.size
    except Exception as e:
        print(f"   logo: could not process image ({type(e).__name__})")
        return None

    meta = {"source": source, "matched": matched, "is_light": is_light,
            "width": w, "height": h}
    json.dump(meta, open(meta_path, "w"))
    meta["path"] = path
    return meta


if __name__ == "__main__":
    import sys
    for b in sys.argv[1:]:
        r = fetch(b)
        print(f"{b}: {r}")
