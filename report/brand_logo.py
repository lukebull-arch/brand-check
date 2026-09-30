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


def _is_human(qid):
    """Wikidata P31 = Q5. A brand search can land on a person of the same name.

    "John Lewis" resolves to the American congressman and civil rights leader
    ahead of the retailer, and his entity even carries an official website, so
    without this check a report to John Lewis & Partners could have carried a
    politician's picture.
    """
    q = urllib.parse.urlencode({
        "action": "wbgetclaims", "entity": qid, "property": "P31",
        "format": "json"})
    data = _json(f"https://www.wikidata.org/w/api.php?{q}")
    for claim in (data or {}).get("claims", {}).get("P31") or []:
        try:
            if claim["mainsnak"]["datavalue"]["value"]["id"] == "Q5":
                return True
        except (KeyError, TypeError):
            continue
    return False


def _wikidata_entity(brand):
    q = urllib.parse.urlencode({
        "action": "wbsearchentities", "search": brand, "language": "en",
        "format": "json", "limit": 5, "type": "item"})
    data = _json(f"https://www.wikidata.org/w/api.php?{q}")
    hits = [h for h in (data or {}).get("search", []) if h.get("id")]
    # Drop people before anything else: a person sharing the brand's name is
    # never the right answer for a brand logo.
    org_hits = []
    for h in hits:
        try:
            if _is_human(h["id"]):
                print(f"   logo: skipping {h['id']} "
                      f"({h.get('label')!r}: a person, not an organisation)")
                continue
        except Exception:
            pass
        org_hits.append(h)
    for hit in org_hits:
        # Prefer a hit whose label matches the brand closely; the first result
        # is usually right but "Apple" style collisions are worth guarding.
        label = (hit.get("label") or "").lower()
        if label == brand.lower() or brand.lower() in label:
            return hit
    return (org_hits or [None])[0]


# Some brands resolve to an umbrella entity holding several groups' logos.
# Aldi is the live example: Q125054 "Aldi" carries BOTH AldiNord-WorldwideLogo
# and the Aldi Sued mark, and taking the first put the Nord logo on a report
# bound for Aldi UK, which is Aldi Sued. Pin the entity where the right answer
# is known and market-specific.
ENTITY_OVERRIDES = {
    "aldi": "Q41171672",          # Aldi Sued: the group that runs Aldi UK & Ireland
    "john lewis": "Q6244784",     # the retailer, not the US congressman
    "england rugby": "Q1347463",  # the RFU, not an England touring side
    "dp world tour": "Q121571",   # the tour itself, not its Dubai finale
    "kinder": "Q15410057",        # Ferrero's chocolate brand, not the German word or a surname
}

# Where the brand's own site is the better source than Wikidata. Checked FIRST
# when set. Aldi UK trades as plain "ALDI": Wikidata's correct corporate entity
# (Aldi Sued) carries the "ALDI SUED" wordmark, which is the right company and
# the wrong mark to put in front of a UK recipient.
DOMAIN_OVERRIDES = {}

# Pinned Commons files, where the automatic pick is the wrong market's mark.
# Aldi: the UK business is Aldi Sued, but its shopfront mark is plain "ALDI".
# Wikidata's Sued entity offers only "Aldi Sued ... logo.svg" (reads ALDI SUED,
# wrong for a UK recipient) and the umbrella entity leads with Aldi Nord's.
# aldi.co.uk itself serves only the bare "A" arc, no wordmark, so the site
# fallback cannot help either. "Aldi Logo 2017" is the current UK logo.
FILE_OVERRIDES = {
    "lg": "LG logo (2023).svg",
    "nothing": "Nothing.svg",
    "aldi": "Aldi Süd 2017 logo.svg",   # Luke, 24 Sep 2026: use the Aldi Süd mark (the Nord worldwide logo had been cached)
    # Wikidata resolves "Cadbury" to a Devon village, and both the company
    # (Q6677525) and brand (Q125544610) entities trip the umbrella-logo guard,
    # so the search falls through to a 256px favicon blob. Commons holds the
    # real gold-on-purple script; .logo_cache/cadbury.png is that file cropped
    # to the wordmark as a rounded tile (15 Sep 2026).
    "cadbury": "Cadbury logo new.jpg",
}

# Direct asset URLs, for marks that are neither on Commons nor the first thing
# a site advertises. Premier Padel's header logo and og:image are the sponsor
# lockup ("QATAR AIRWAYS PREMIER PADEL TOUR", in white type that disappears on
# our cream page); the footer carries the clean wordmark on transparency.
ASSET_OVERRIDES = {
    "premier padel": "https://premierpadel.com/images/footernewlogo.svg",
    # The tour rebranded from European Tour in 2022, but europeantour.com still
    # serves ET-branded icons and dpworldtour.com times out to a server-side
    # fetch. This is the current mark, off their own CDN.
    "dp world tour": ("https://www.europeantour.com/api/images/image/upload/"
                      "t_q_good/v1746603967/PRD/assets/logos/"
                      "dp-world-tour-verticle-logo_lklewt_n9s3uj.svg"),
}


def _official_domain(qid):
    """The brand's own site, from Wikidata P856, for logo fallbacks.

    Guessing "<brand>.com" fails on exactly the brands that need the fallback:
    Aston Villa is avfc.co.uk and Brighton is brightonandhovealbion.com.
    """
    q = urllib.parse.urlencode({
        "action": "wbgetclaims", "entity": qid, "property": "P856",
        "format": "json"})
    data = _json(f"https://www.wikidata.org/w/api.php?{q}")
    for claim in (data or {}).get("claims", {}).get("P856") or []:
        try:
            url = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        host = urllib.parse.urlparse(url).netloc
        if host:
            return host
    return None


def _site_logo(domain):
    """Best mark the brand's own homepage offers.

    Prefers an apple-touch-icon or og:image over a favicon: both are usually
    a few hundred pixels, where a favicon is 32px and prints as mush.
    """
    for scheme in ("https://",):
        try:
            html = _get(f"{scheme}{domain}/", timeout=20)
        except Exception:
            continue
        if not html:
            continue
        text = html.decode("utf-8", "ignore")[:200000]
        cands = []
        # An <img> whose src, alt or class says "logo" is usually the real
        # wordmark, and often the only working copy: Premier Padel's og:image
        # points at a CDN path that returns AccessDenied, while the header
        # <img> on the main domain serves a 20KB SVG.
        for tag in re.findall(r'<img[^>]+>', text, re.I):
            if not re.search(r'logo|brand|wordmark|crest', tag, re.I):
                continue
            m = re.search(r'src=["\']([^"\']+)["\']', tag, re.I)
            if m and not m.group(1).startswith("data:"):
                cands.append(m.group(1))
        for pat in (r'<link[^>]+rel=["\'][^"\']*apple-touch-icon[^"\']*["\'][^>]*>',
                    r'<meta[^>]+property=["\']og:image["\'][^>]*>',
                    r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*>'):
            for tag in re.findall(pat, text, re.I):
                m = re.search(r'(?:href|content)=["\']([^"\']+)["\']', tag, re.I)
                if m:
                    cands.append(m.group(1))
        for href in cands:
            url = urllib.parse.urljoin(f"{scheme}{domain}/", href)
            try:
                raw = _get(url, timeout=20)
            except Exception:
                continue
            if not raw:
                continue
            # An SVG is the best possible outcome for print, and sites often
            # expose the real wordmark that way while Commons has nothing:
            # Premier Padel publishes header-logo.svg as its og:image.
            if b"<svg" in raw[:4000] and len(raw) < MAX_BYTES:
                return raw, url
            # a favicon-sized raster is not worth printing
            if len(raw) > 3000 and _looks_like_image(raw):
                return raw, url
    return None, None


def _logo_filenames(qid):
    """Every P154 filename, so an ambiguous entity can be reported, not guessed."""
    q = urllib.parse.urlencode({
        "action": "wbgetclaims", "entity": qid, "property": "P154", "format": "json"})
    data = _json(f"https://www.wikidata.org/w/api.php?{q}")
    out = []
    for claim in ((data or {}).get("claims", {}).get("P154") or []):
        try:
            out.append(claim["mainsnak"]["datavalue"]["value"])
        except (KeyError, TypeError):
            continue
    return out


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
    """PNG render of a Commons file at a given width."""
    safe = urllib.parse.quote(filename.replace(" ", "_"))
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width={width}"
    return _get(url, timeout=30)


def _commons_original(filename):
    """The file as uploaded. For an SVG this keeps the logo vector, which
    renders as crisply as the surrounding text instead of looking soft."""
    safe = urllib.parse.quote(filename.replace(" ", "_"))
    return _get(f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}", timeout=30)


def _svg_renders(path):
    """An SVG that parses but draws nothing (or substitutes fonts for text) is
    worse than a raster fallback, so confirm it produces real geometry."""
    try:
        from svglib.svglib import svg2rlg
        d = svg2rlg(path)
        return bool(d) and d.width > 4 and d.height > 4 and len(d.contents) > 0
    except Exception:
        return False



def _dewhite(im):
    """Drop a solid white backdrop so the mark sits on the report's cream.

    Only white that touches the border is removed, by flood fill, never every
    white pixel: Aldi's wordmark is white lettering inside a blue box, and a
    blanket key would punch holes straight through it. A JPEG cannot carry
    transparency, so a Commons JPEG (World Tennis) otherwise prints as a white
    rectangle on an off-white page.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return im
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    # only act when the border really is white; a logo bled to its own edge
    # must be left alone
    border, white = 0, 0
    for x in range(w):
        for y in (0, h - 1):
            r, g, b, a = px[x, y]
            border += 1
            if a > 40 and r > 238 and g > 238 and b > 238:
                white += 1
    for y in range(h):
        for x in (0, w - 1):
            r, g, b, a = px[x, y]
            border += 1
            if a > 40 and r > 238 and g > 238 and b > 238:
                white += 1
    if not border or white / border < 0.9:
        return im

    seen = bytearray(w * h)
    stack = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    stack += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        i = y * w + x
        if seen[i]:
            continue
        r, g, b, a = px[x, y]
        if a == 0:
            seen[i] = 1
            continue
        if not (r > 234 and g > 234 and b > 234):
            continue
        seen[i] = 1
        px[x, y] = (r, g, b, 0)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return im


def _looks_like_image(raw):
    return bool(raw) and len(raw) < MAX_BYTES and raw[:8] in (
        b"\x89PNG\r\n\x1a\n",) or (raw or b"")[:3] == b"\xff\xd8\xff"


# Site builders serve their own favicon for every customer site that never set
# one. Wix's default is a known file; and a builder-hosted site announces
# itself in response headers, which is the cheaper and surer test.
PLATFORM_DEFAULT_FAVICONS = ("https://static.parastorage.com/client/pfavico.ico",)
_platform_favicon_cache = {}
BUILDER_HEADER_MARKS = ("x-wix-request-id", "x-shopify-stage", "x-shopid",
                        "x-squarespace", "x-served-by: cache-", "server: squarespace",
                        "server: pepyaka", "x-wf-", "x-godaddy")


def _pixel_key(raw):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGBA").resize((16, 16))
        return bytes(v // 32 for px in im.getdata() for v in px)
    except Exception:
        return None


def _is_platform_favicon(raw):
    key = _pixel_key(raw)
    if key is None:
        return False
    for u in PLATFORM_DEFAULT_FAVICONS:
        if u not in _platform_favicon_cache:
            try:
                ref = _get(u)
                _platform_favicon_cache[u] = _pixel_key(ref) if ref else None
            except Exception:
                _platform_favicon_cache[u] = None
        if _platform_favicon_cache[u] and _platform_favicon_cache[u] == key:
            return True
    return False


def _hosted_by_builder(domain):
    """True when the site's response headers name a site builder (Wix,
    Shopify, Squarespace, Webflow, GoDaddy). Their favicons are the builder's
    unless the owner set one, so a favicon from such a site is not trusted."""
    for scheme in ("https://www.", "https://"):
        try:
            req = urllib.request.Request(scheme + domain, method="HEAD",
                                         headers={"User-Agent": "Mozilla/5.0 (GEEIQ brand check)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                headers = r.headers
        except urllib.error.HTTPError as e:
            # A 403 or 404 still comes with the host's headers, which is all
            # this needs (Wix answers HEAD with 404 and x-wix-request-id).
            headers = e.headers
        except Exception:
            continue
        hdrs = "\n".join(f"{k.lower()}: {v.lower()}" for k, v in headers.items())
        if any(m in hdrs for m in BUILDER_HEADER_MARKS):
            return True
    return False


def fetch(brand, out_dir=None):
    """Return {"path", "source", "matched", "is_light"} or None."""
    out_dir = out_dir or CACHE
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-") or "brand"
    path = os.path.join(out_dir, f"{slug}.png")
    meta_path = os.path.join(out_dir, f"{slug}.json")

    svg_cached = os.path.join(out_dir, f"{slug}.svg")
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path))
            cached = svg_cached if meta.get("vector") else path
            if os.path.exists(cached):
                meta["path"] = cached
                return meta
        except Exception:
            pass

    raw, source, matched = None, None, None

    # 0a. Pinned asset: the exact file, when nothing else finds the right one
    asset = ASSET_OVERRIDES.get(brand.strip().lower())
    if asset:
        try:
            candidate = _get(asset, timeout=20)
            if candidate and b"<svg" in candidate[:4000]:
                svg_path = os.path.join(out_dir, f"{slug}.svg")
                open(svg_path, "wb").write(candidate)
                if _svg_renders(svg_path):
                    meta = {"source": f"pinned asset (vector): {asset}",
                            "matched": f"{brand} [asset pinned]",
                            "is_light": False, "vector": True}
                    json.dump(meta, open(meta_path, "w"))
                    meta["path"] = svg_path
                    return meta
                os.remove(svg_path)
            elif candidate and _looks_like_image(candidate):
                raw = candidate
                source = f"pinned asset: {asset}"
                matched = f"{brand} [asset pinned]"
        except Exception as e:
            print(f"   logo: pinned asset failed ({type(e).__name__})")

    # 0. Pinned site: authoritative for market-specific marks
    pinned = DOMAIN_OVERRIDES.get(brand.strip().lower())
    if pinned:
        try:
            candidate, url = _site_logo(pinned)
            if candidate:
                raw = candidate
                source = f"official site (pinned): {url}"
                matched = f"{brand} [pinned to {pinned} for the local mark]"
        except Exception as e:
            print(f"   logo: pinned site failed ({type(e).__name__})")

    hit = None
    # 1. Wikidata -> Commons: a real logo
    try:
        if raw:
            raise StopIteration
        hit = _wikidata_entity(brand)
        names = []
        override = ENTITY_OVERRIDES.get(brand.strip().lower())
        if override:
            qid = override
            matched = f"{brand} [pinned to {qid}: the umbrella entity holds another group's logo]"
        elif hit:
            qid = hit["id"]
            matched = f"{hit.get('label', qid)} ({hit.get('description', 'no description')}) [{qid}]"
        else:
            qid = None
        forced = FILE_OVERRIDES.get(brand.strip().lower())
        if forced:
            names = [forced]
            matched = (f"{brand} [logo pinned to Commons '{forced}': the "
                       f"automatic pick is another market's mark]")
            qid = qid or "pinned"
        if qid and not forced:
            names = _logo_filenames(qid)
            if len(names) > 1:
                print(f"   logo: {qid} lists {len(names)} logos {names}; using the "
                      f"first. Confirm it is the right market's mark.")
        fname = names[0] if names else None
        if fname:
            if fname and fname.lower().endswith(".svg"):
                svg = _commons_original(fname)
                if svg and b"<svg" in svg[:4000] and len(svg) < MAX_BYTES:
                    svg_path = os.path.join(out_dir, f"{slug}.svg")
                    open(svg_path, "wb").write(svg)
                    if _svg_renders(svg_path):
                        meta = {"source": f"Wikidata P154 (vector): {fname}",
                                "matched": matched, "is_light": False,
                                "vector": True}
                        json.dump(meta, open(meta_path, "w"))
                        meta["path"] = svg_path
                        return meta
                    os.remove(svg_path)
            if fname:
                candidate = _commons_render(fname)
                if _looks_like_image(candidate):
                    raw, source = candidate, f"Wikidata P154: {fname}"
    except StopIteration:
        pass
    except Exception as e:
        print(f"   logo: wikidata lookup failed ({type(e).__name__})")

    # 2. The brand's own site. Needed for trademarked marks Commons cannot
    # host: no football club has a P154 claim.
    domain = DOMAIN_OVERRIDES.get(brand.strip().lower())
    if not raw:
        if not domain:
            try:
                qid_for_site = (ENTITY_OVERRIDES.get(brand.strip().lower())
                                or (hit or {}).get("id"))
                if qid_for_site:
                    domain = _official_domain(qid_for_site)
            except Exception as e:
                print(f"   logo: official-site lookup failed ({type(e).__name__})")
        if domain:
            try:
                candidate, url = _site_logo(domain)
                if candidate and b"<svg" in candidate[:4000]:
                    svg_path = os.path.join(out_dir, f"{slug}.svg")
                    open(svg_path, "wb").write(candidate)
                    if _svg_renders(svg_path):
                        meta = {"source": f"official site (vector): {url}",
                                "matched": matched or brand, "is_light": False,
                                "vector": True}
                        json.dump(meta, open(meta_path, "w"))
                        meta["path"] = svg_path
                        return meta
                    os.remove(svg_path)
                elif candidate:
                    raw, source = candidate, f"official site: {url}"
            except Exception as e:
                print(f"   logo: site logo failed ({type(e).__name__})")

    # 3. Favicon last: always answers, but only ever 32-256px, and only for a
    # domain the entity lookup confirmed. A guessed "<brand>.com" is how a Mr
    # Bean report went out under a Wix logo: mrbean.com is a Wix site and its
    # favicon is Wix's. No logo beats the wrong logo.
    if not raw and domain:
        try:
            if _hosted_by_builder(domain):
                print(f"   logo: {domain} is hosted on a site builder; its favicon is not trusted, skipped")
            else:
                candidate = _get(
                    f"https://www.google.com/s2/favicons?domain={domain}&sz=256")
                if _looks_like_image(candidate) and not _is_platform_favicon(candidate):
                    raw, source = candidate, f"favicon: {domain}"
                elif candidate:
                    print(f"   logo: favicon for {domain} is a site builder's default; skipped")
        except Exception as e:
            print(f"   logo: favicon lookup failed ({type(e).__name__})")
    elif not raw:
        print(f"   logo: no confirmed domain for {brand}; favicon guess skipped")

    if not raw:
        return None

    # Normalise and work out whether it needs a dark backing plate: a
    # white-on-transparent logo is invisible on our off-white page.
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        if im.width < 32 or im.height < 32:
            return None  # too small to look like anything but a smudge
        im = _dewhite(im)
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
