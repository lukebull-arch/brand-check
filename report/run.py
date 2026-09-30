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
import time
import urllib.error
import urllib.request

import brand_logo
import platform_check

# If fewer than this share of scanned videos actually name the brand, YouTube is
# mostly keyword collision: keep the figure for context but never let it lead.
YT_SIGNAL_FLOOR = 0.5

# Physical-product brands attract real-world videos that name the brand inside
# gaming keyword searches (a KTM report led with 98m views of motorbike Shorts).
# When less than this share of named view volume carries any gaming term in the
# title, the YouTube figures are treated as contaminated and dropped from the
# report entirely. Calibrated on real pulls: KFC 0.39, adidas 0.34 (kept);
# Casio 0.06, KTM ~0.01 (dropped).
YT_GAMING_FLOOR = 0.30
_GAMING_TERMS = re.compile(
    r"roblox|fortnite|minecraft|gaming|gameplay|\bgame\b|obby|tycoon|simulator"
    r"|\bugc\b|creative|uefn|\bmods?\b|server|speedrun", re.I)

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

# Creators decorate marketplace names with emoji ("⭐Aston Villa Flag⭐",
# "We love shopping in Lidl ☁️✨😂"). Chrome renders those through Apple Color
# Emoji as a Type 3 bitmap font, which a commercial printer will either reject
# or reproduce badly, so they are stripped from anything the report displays.
# Only the printed string changes; the collected data keeps the original name.
_EMOJI = re.compile(
    "[" 
    "\U0001F000-\U0001FAFF"   # pictographs, emoticons, symbols, supplements
    "\U00002600-\U000027BF"   # misc symbols and dingbats
    "\U0001F1E6-\U0001F1FF"   # regional indicators
    "\U00002190-\U000021FF"   # arrows
    "\U00002B00-\U00002BFF"   # misc symbols and arrows
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0001F3FB-\U0001F3FF"   # skin tone modifiers
    "\U000020E3\U000020E0"    # combining enclosing marks
    "\U0000200D"               # zero-width joiner, invisible
    "\U000000B0"               # degree sign, used decoratively in item names
    "\U00002700-\U000027BF"   # dingbats, decorative stars
    "\U00002460-\U000024FF"   # enclosed alphanumerics
    "\U00003000-\U0000303F"   # CJK punctuation used as decoration
    "\U0000FF00-\U0000FFEF"   # fullwidth forms
    "]+")
# NOTE: tm and (r) are deliberately NOT stripped. They print fine in Figtree,
# and an imitator account called "Tesco(tm)" must not be displayed as "Tesco":
# that is the impersonator-as-official trap, in the copy rather than the data.


# The report embeds Figtree and Plus Jakarta Sans, which cover Latin only. Any
# other script has no glyph and prints as a hollow box: creator names carry
# Thai, Cyrillic, CJK and invisible padding like U+115F HANGUL CHOSEONG FILLER,
# which is what put "KAPPO[]" in a draft. Whitelisting what the fonts can
# actually draw is the only reliable guard, since a blocklist never ends.
_PRINTABLE = re.compile(
    r"[^"
    r"\u0020-\u007E"          # ASCII
    r"\u00A0-\u024F"          # Latin-1 Supplement, Latin Extended-A and B
    r"\u0300-\u036F"          # combining diacriticals, they sit over Latin
    r"\u2018\u2019\u201C\u201D"  # curly quotes
    r"\u2013\u2014\u2026\u00B7"  # en/em dash, ellipsis, middot
    r"\u2122\u00AE\u00A9"        # tm, (r), (c)
    r"\u00A3\u20AC\u0024"        # currency
    r"]")


def strip_emoji(text):
    """The name as it should appear in print: only glyphs the fonts can draw.

    Emoji and decoration go first, then anything outside the embedded Latin
    coverage. If a name is nothing but unrenderable characters the original is
    returned, so a row never silently becomes blank.
    """
    if not text:
        return ""
    cleaned = _PRINTABLE.sub(" ", _EMOJI.sub(" ", str(text)))
    # Leading and trailing bracketed tags are live-ops banners, not the name:
    # "[SNUFFY] Blue Lock: Rivals" is Blue Lock: Rivals, "NHL Blast [BETA]" is
    # NHL Blast. Same rule as hybrid_letter.clean_name.
    cleaned = re.sub(r"^(\s*[\[(][^\])]*[\])]\s*)+", "", cleaned)
    cleaned = re.sub(r"(\s*[\[(][^\])]*[\])]\s*)+$", "", cleaned)
    out = " ".join(cleaned.split()).strip(" -|\u00b7,.:;~*")
    # Never fall back to the raw string. A name written entirely in Cyrillic,
    # Thai or emoji has nothing the fonts can draw, and returning the original
    # is how a hollow box reaches the page. A couple of surviving letters is
    # also not a name ("(F)(L)(Y)(I)(N)(G) (C)(A)(T)" reduces to two), so such
    # rows are dropped by the callers instead of printed as a fragment.
    if sum(c.isascii() and c.isalnum() for c in out) < 2:
        return ""
    return out


def print_safe(rows, *keys):
    """Rows with display fields cleaned for print, dropping the unprintable.

    A row whose first named field cannot be rendered is omitted rather than
    shown as a box or a two-letter fragment. Omitting is safe here: these
    panels are illustrative, and the counts they sit under come from the full
    data, not from the rows displayed.
    """
    out = []
    for r in rows or []:
        c = dict(r)
        for k in keys:
            if c.get(k):
                c[k] = strip_emoji(c[k])
        if keys and not c.get(keys[0]):
            continue
        out.append(c)
    return out


def base_brand(brand):
    """The brand with a trailing 'official' stripped: submissions and account
    names use it interchangeably ('Pizza Hut' vs 'Pizza Hut Official')."""
    b = brand.strip()
    return re.sub(r"\s*official\s*$", "", b, flags=re.I).strip() or b


_ORG_SUFFIXES = {"fc", "afc", "cf", "sc", "plc", "ag", "inc", "ltd", "llc",
                 "gmbh", "sa", "co", "group"}


def core_brand(brand):
    """The brand without brackets or a company suffix: 'Chelsea (FC)' and
    'Chelsea FC' both become 'Chelsea'. Creators name their work the way
    people speak, so a kit is a 'Chelsea 25/26 Home Kit'. Matching only the
    submitted string once counted 54 items where 1,047 existed."""
    b = " ".join(re.sub(r"\s*\([^)]*\)", "", brand or "").split())
    words = b.split()
    if len(words) > 1 and words[-1].lower().strip(".") in _ORG_SUFFIXES:
        b = " ".join(words[:-1])
    return b or (brand or "").strip()


# Brands whose own wordmark is lower case. Extend as they come up.
LOWERCASE_BRANDS = {"adidas", "lululemon", "asics", "innocent", "boohoo"}


def display_brand(brand):
    """The brand as it should be printed. People type "shopkins" and "aston
    martin" into the form, and a report that calls the brand "shopkins" in
    front of its own brand team reads as carelessness. Anything the sender
    capitalised themselves is left alone, so KFC, e.l.f. and Pizza Hut survive
    untouched; only an all-lower-case submission gets title-cased."""
    b = " ".join((brand or "").split())
    if not b or any(c.isupper() for c in b):
        return b
    if b.lower() in LOWERCASE_BRANDS:
        return b
    def cap(w):
        # Company suffixes are initialisms, not words: "chelsea fc" is
        # "Chelsea FC", never "Chelsea Fc".
        if w.lower() in _ORG_SUFFIXES:
            return w.upper()
        # Leave anything with punctuation alone: "e.l.f." is not "E.l.f.".
        return w[0].upper() + w[1:] if w and w.isalpha() else w
    return " ".join(cap(w) for w in b.split(" "))


def brand_terms(brand):
    terms = set()
    for t in (brand.lower().strip(), base_brand(brand).lower(),
              core_brand(brand).lower()):
        if t:
            terms.add(t)
            if " " in t:
                terms.add(t.replace(" ", ""))
    # Fans drop the apostrophe: "McDonalds" and "Dominos" outnumber the
    # punctuated forms, and a McDonald's probe matched 0 of 30 rows until this
    # variant existed. Possessive-only strip, so imitator punctuation like
    # "Gregg's TM" in CREATOR names stays significant (that guard is _norm,
    # not this).
    for t in list(terms):
        bare = t.replace("'", "")
        if bare != t:
            terms.add(bare)
    # Accents go the same way: fans write "Nestle", the sheet says "Nestlé".
    import unicodedata
    for t in list(terms):
        flat = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
        if flat and flat != t:
            terms.add(flat)
    return terms



# Vocabulary that makes an ambiguous lead word unmistakably the brand. Fans
# write "Brighton Home Kit 22-23, #22 Kaoru Mitoma", never the registered name,
# so a club whose full name never appears is undercounted: a 3-token rule found
# 79 Brighton items where roughly 180 exist. The lead word alone is not enough
# ("brighton beach", "MTA NYC Subway : Brighton Line" are not the club), so it
# only counts alongside a word from the brand's own domain.
_KIT_WORDS = set("""kit kits shirt jersey strip shorts sock socks home away third
gk goalkeeper keeper training prematch anthem retro replica badge crest scarf
fc afc cfc utd united city town albion rovers wanderers hotspur
premier league championship efl ucl uefa fa cup""".split())

_SEASON = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{2}\s*[/-]\s*\d{2}\b")


def lead_word_match(name, lead, domain_words):
    """True when an ambiguous lead word is qualified by domain vocabulary.

    Counted separately from full-name matches and reported as such, because
    the qualifier makes it probable, not certain.
    """
    if not lead:
        return False
    n = (name or "").lower()
    if lead not in n:
        return False
    toks = {t for t in re.split(r"[^a-z0-9]+", n) if t}
    if toks & domain_words:
        return True
    return bool(_SEASON.search(n))


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
        # "officially licensed" must name the brand: a Kinder run classified a
        # 66.8m-visit dungeon RPG as Kinder's own because its description read
        # "officially licensed by Voldex" - a studio licence, no brand at all.
        rf"\bofficially\s+licensed\s+(?:by\s+)?{b}\b",
        rf"\b{b}\s+officially\s+licensed\b",
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


_TERM_RE_CACHE = {}


def matches(text, terms):
    """Whole-word brand match.

    A plain substring test reads "aldi" inside "Maldivian Hotel and Resort"
    (17.5m visits), "SubterBaldi" and "Raldi's CrackHouse", which together put
    a false 20m-visit headline on an Aldi report. Short brand names are inside
    ordinary words often enough that the boundary is not optional. Matching is
    deliberately conservative: the report already words counts as "at least".
    """
    t = (text or "").lower()
    if not t:
        return False
    for term in terms:
        if not term:
            continue
        rx = _TERM_RE_CACHE.get(term)
        if rx is None:
            rx = re.compile(r"(?<![a-z0-9])" + re.escape(term)
                            + r"(?![a-z0-9])")
            _TERM_RE_CACHE[term] = rx
        if rx.search(t):
            return True
    return False


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



# Marketplace listings that stuff trending keywords around the brand word.
# A Lidl run put "xorowhair lidl tatsumaki narcissist monterrey ymir" (22,087
# favourites) at the top of the report: the row genuinely names the brand, so
# Brand Match passes, but the item is UGC clothing spam and 99% of Lidl's
# entire favourite volume came from listings like it. Counts survive this
# (each spam row is still a real listing by a real creator); anything ranked
# by favourites does not, so the guard only screens the ranked figures.
_FUNCTION_WORDS = set("""a an the and or but if of in on at to for from with by
is are was were be been am do does did my your our their his her its i you he she
it we they me him us them this that these those not no nor so as than then there
here what which who whom whose when where why how all any both each few more most
other some such only own same too very can will just dont don't im i'm pls please
help lost found got get gonna wanna about after again against because before
being below between during into out over under up down off once
""".split())

_PRODUCT_WORDS = set("""shirt tshirt tee top bottom bottoms pants trouser trousers
jeans uniform hoodie jacket coat vest scarf hat cap beanie bag apron kit jersey
shorts socks polo sweater sweatshirt crop skirt dress suit tie glove gloves boot
boots shoe shoes trainers logo flag badge banner sign store shop worker retail
employee staff cashier till trolley basket bucket clan gang card clubcard
merch set outfit costume mask helmet backpack home away third gk goalkeeper
ls ss alt replica training prematch anthem""".split())


def is_keyword_soup(name, terms, extra_product_words=frozenset()):
    """True when the brand word sits in a run of unrelated tokens.

    Genuine fan items name the brand and what the thing is ("Tesco Top w/
    Vest", "Brighton & Hove Albion Home Shorts 20 - 21"). Spam listings chain
    unrelated fandom and celebrity tokens to catch every search at once, and
    the brand word is just one of them. Word count alone is not the signal:
    real kit names are long too, which is why a product word rescues a row.
    """
    toks = [t for t in re.split(r"[^A-Za-z0-9']+", name or "") if t]
    if len(toks) <= 3:
        return False
    brand_toks = set()
    for t in terms:
        brand_toks.update(x.lower() for x in re.split(r"[^A-Za-z0-9']+", t) if x)
    others = [t.lower() for t in toks if t.lower() not in brand_toks]
    # seasons and years describe a kit, they are not stuffed keywords:
    # "Brighton Hove Albion 2025 Ferdi Kadioglu LS" is a real shirt
    others = [o for o in others if not o.isdigit()]
    if not others:
        return False
    # any word describing an actual product means the listing is about something
    if any(o in _PRODUCT_WORDS or o in extra_product_words for o in others):
        return False
    # a function word means the name reads as a phrase, not a keyword chain:
    # "i lost my mum at tesco (pls help)" is a real meme tee, while spam is a
    # run of bare proper nouns ("dax tenjiku chrollo yasuo lidl housemaid")
    if any(o in _FUNCTION_WORDS for o in others):
        return False
    # four or more unrelated tokens, no product word, no phrasing
    return len(others) >= 4


# Brands whose name is also an ordinary word or a bigger fandom collide on
# the marketplace: "kinder" is German for children and a kawaii fashion word,
# "dominos" is a tile game and a wings accessory, "Snickers" is a streamer's
# merch line. A fan row for these brands counts only when the listing also
# names the product. Audited 9 Sep 2026 against the raw matches (Kinder 107
# of 487, Domino's 45 of 342, Snickers 79 of 743); the screens below
# reproduce those audits to within a handful of rows.
# Roblox groups known to issue licensed items for other companies' IP. A
# verified badge alone cannot classify an account (verified UGC studios make
# fan items too), so a name here, or a platform partnership record, is what
# upgrades a verified issuer from "check this" to "official via partner".
KNOWN_LICENSEE_GROUPS = {
    # lower-case group name -> (brand it issues for, Roblox group id)
    "cartoon network games": ("Cartoon Network", "5544719"),
}


def known_licensee(name, creator_id, verified):
    """A known licensee matches on group id, or on name when Roblox has
    verified the account. An unverified account merely named like one is an
    imitator until the platform says otherwise."""
    hit = KNOWN_LICENSEE_GROUPS.get((name or "").lower().strip())
    if not hit:
        return None
    brand, gid = hit
    if str(creator_id or "") == gid or verified:
        return brand
    return None


def backfill_verified(creators, cache_path):
    """Older CSVs carry no Creator Verified column. Ask Roblox for the badge
    of each creator of a brand-named row, bounded and cached, so a rerun on
    archived data gets the same gate as a fresh pull."""
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path))
        except Exception:
            cache = {}
    asked = 0
    # Biggest issuers first: the partner with eight items matters more than
    # eighty one-item accounts, and the request budget is finite.
    for name, d in sorted(creators.items(), key=lambda kv: -kv[1].get("items", 0)):
        key = f"{d.get('type')}:{d.get('id')}"
        if not d.get("id") or d.get("verified") is not None:
            continue
        if key in cache:
            d["verified"] = cache[key]
            continue
        if asked >= 120:
            break
        url = (f"https://groups.roblox.com/v1/groups/{d['id']}" if str(d.get("type")).lower() == "group"
               else f"https://users.roblox.com/v1/users/{d['id']}")
        d["verified"] = None
        for attempt in (1, 2, 3):
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0 (GEEIQ brand check)"}),
                        timeout=15) as r:
                    j = json.load(r)
                d["verified"] = bool(j.get("hasVerifiedBadge"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(5 * attempt)   # Roblox rate limit; wait it out
                    continue
                break
            except Exception:
                break
        # Only a real answer is cached. A failed lookup cached as "unknown"
        # would silence the gate on every rerun of that data.
        if d["verified"] is not None:
            cache[key] = d["verified"]
        asked += 1
        time.sleep(0.6)
    try:
        json.dump(cache, open(cache_path, "w"))
    except Exception:
        pass


CONTEXT_SCREENS = {
    "kinder": ("chocolate", ["bueno", "surprise", "egg", "eggs", "chocolate", "choco", "joy",
                             "schoko", "ferrero", "happy hippo", "hippo", "maxi", "country",
                             "delice", "pingui", "cards", "uberraschung", "\u00fcberraschung"]),
    "domino's": ("pizza", ["pizza", "pizzas", "delivery", "driver", "uniform", "employee",
                           "worker", "staff", "slice", "garlic", "dominos pizza"]),
    "dominos": ("pizza", ["pizza", "pizzas", "delivery", "driver", "uniform", "employee",
                          "worker", "staff", "slice", "garlic", "dominos pizza"]),
    "snickers": ("chocolate", ["bar", "chocolate", "choc", "candy", "peanut", "caramel",
                               "nougat", "mars", "wrapper", "hungry", "satisfies", "sweet", "snack"]),
}


def analyse(csv_dir, brand):
    terms = brand_terms(brand)
    off_norms = official_creator_norms(brand)
    loose_norms = loose_creator_norms(brand)
    items = read_csv(os.path.join(csv_dir, "roblox_catalog_items.csv"))
    games = read_csv(os.path.join(csv_dir, "roblox_games.csv"))

    # The collector records any ceiling it hit. A capped pull must never be
    # written up as a census, so the fact rides through to the report.
    notes = {}
    notes_path = os.path.join(csv_dir, "collection_notes.json")
    if os.path.exists(notes_path):
        try:
            with open(notes_path) as f:
                notes = json.load(f)
        except Exception as e:
            print(f"  collection notes unreadable ({e})")

    # Items that only match the short name ("Chelsea" for a "Chelsea FC"
    # submission) are counted, because that is how fans title their work, but
    # the ambiguity is reported rather than buried.
    full_terms = {t for t in (brand.lower().strip(),
                              brand.lower().strip().replace(" ", "")) if t}
    short_only = core_brand(brand).lower() != brand.lower().strip()

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

    # Long names get shortened by the people making the items. Only brands of
    # three or more significant words qualify: a two-word brand is short enough
    # that fans write it in full, and rescuing on its first word would drag in
    # other brands entirely ("Aston" would collect Aston Martin).
    _sig = [w for w in re.split(r"[^A-Za-z0-9]+", core_brand(brand) or "") if len(w) > 2]
    lead = _sig[0].lower() if len(_sig) >= 3 else ""
    lead_matched = []
    if lead:
        seen_fan = {id(r) for r in fan} | {id(r) for r in official}
        lead_matched = [r for r in items
                        if id(r) not in seen_fan
                        and not is_official(r["Creator"])
                        and lead_word_match(r.get("Name"), lead, _KIT_WORDS)]
        fan = fan + lead_matched
    fan_named_raw = len(fan)
    context_label = ""
    screen = CONTEXT_SCREENS.get(brand.lower().strip())
    if screen:
        context_label, ctx_terms = screen
        fan = [r for r in fan if matches(r.get("Name"), ctx_terms)]
        print(f"  context screen ({context_label}): {fan_named_raw} rows name {brand}, "
              f"{len(fan)} are {context_label} products; the rest are excluded")
    # --- Partner-run presence: the signal the string test cannot see. ---
    # Licensed IP reaches Roblox through partners (Mr Bean through Cartoon
    # Network Games, True through cSapphire). Their items sit in `fan` above
    # because the creator name is not the brand. Roblox's verified badge marks
    # the accounts worth asking about; the GEEIQ platform (or a known licensee
    # name) decides. Anything verified that the platform cannot place stays
    # creator-made in the figures but blocks every "no official" sentence.
    has_verified_col = bool(items) and "Creator Verified" in items[0]
    named_creators = {}
    for r in fan:
        c = (r.get("Creator") or "").strip()
        if not c:
            continue
        d = named_creators.setdefault(c, {"type": r.get("Creator Type", ""),
                                          "id": str(r.get("Creator ID") or ""),
                                          "items": 0, "verified": None})
        d["items"] += 1
        if r.get("Creator Verified") == "yes":
            d["verified"] = True
        elif has_verified_col:
            d["verified"] = False
    if not has_verified_col and named_creators:
        backfill_verified(named_creators, os.path.join(csv_dir, "creator_verified.json"))
    verified_names = sorted((c for c, d in named_creators.items() if d.get("verified")),
                            key=lambda c: -named_creators[c]["items"])
    platform = {"checked": False, "error": "skipped (BRAND_CHECK_NO_PLATFORM)"}
    if os.environ.get("BRAND_CHECK_NO_PLATFORM") != "1":
        platform = platform_check.check(brand, verified_names[:8],
                                        os.path.join(csv_dir, "platform_check.json"))
        if platform.get("error"):
            print(f"  platform check: {platform['error']}")
    partner_of = {}   # creator -> platform brand it issues for
    for c, d in named_creators.items():
        known = known_licensee(c, d.get("id"), d.get("verified"))
        if known:
            partner_of[c] = known
    for c in verified_names:
        m = (platform.get("creator_matches") or {}).get(c) or {}
        if c not in partner_of and isinstance(m, dict) and (m.get("partnerships_2y") or 0) > 0:
            partner_of[c] = m.get("brand") or c
    partner_items = [r for r in fan if (r.get("Creator") or "").strip() in partner_of]
    fan = [r for r in fan if (r.get("Creator") or "").strip() not in partner_of]
    partner_issuers = [{"creator": c, "brand": b, "items": named_creators[c]["items"],
                        "drops_2y": ((platform.get("creator_matches") or {}).get(c) or {}).get("item_drops_2y")
                        if isinstance((platform.get("creator_matches") or {}).get(c), dict) else None}
                       for c, b in partner_of.items()]
    partner_issuers.sort(key=lambda x: -x["items"])
    verified_unplaced = [{"creator": c, "items": named_creators[c]["items"]}
                         for c in verified_names if c not in partner_of]
    if partner_issuers:
        print("  official via partner: " + "; ".join(
            f"{x['creator']} -> {x['brand']} ({x['items']} items)" for x in partner_issuers))
    if verified_unplaced:
        print("  verified accounts issuing brand-named items, not placed by the platform: "
              + ", ".join(x["creator"] for x in verified_unplaced[:6]))

    noise_items = [r for r in items if r not in official and r not in fan and r not in partner_items]
    creators = sorted({r["Creator"] for r in fan if r.get("Creator")})
    _tally = {}
    for r in fan:
        c = (r.get("Creator") or "").strip()
        if c:
            _tally[c] = _tally.get(c, 0) + 1
    top_creators = [{"name": c, "items": n} for c, n in
                    sorted(_tally.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
                    if n > 1]
    fav_key = lambda r: to_int(r.get("Favorites"))
    # Ranked-by-favourite figures must not be led by keyword-stuffing spam.
    # For screened brands the product vocabulary is the screen itself: "Kinder
    # Egg Surprise [Headless] - bros8000" (90 favourites) is a real item, not soup.
    soup = [r for r in fan if is_keyword_soup(r.get("Name"), terms,
                                              frozenset(ctx_terms) if screen else frozenset())]
    soup_ids = {id(r) for r in soup}
    fan_ranked = [r for r in fan if id(r) not in soup_ids]
    soup_favs = sum(fav_key(r) for r in soup)
    fan_favs = sum(fav_key(r) for r in fan)
    top_item = max(official + partner_items + fan_ranked, key=fav_key, default=None)

    # An experience is the brand's own when its creator is the brand's
    # account, whatever the experience is called (The Hut never says Pizza
    # Hut).
    def is_official_game(r):
        if is_official(r.get("Creator"),
                       verified=r.get("Verified Creator") == "yes"):
            return True
        # Run by a partner the platform or the licensee list vouches for.
        if (r.get("Creator") or "").strip() in partner_of:
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
                                       verified=r.get("Verified Creator") == "yes")
                   and r.get("Creator") not in partner_of})
    g_match = [r for r in games if matches(r["Name"], terms) or r in g_official]
    # Same product-context screen for experiences: "Push Dominos" (2.9m visits)
    # is a tile game, and would otherwise head a Domino's Pizza report.
    if screen:
        g_match = [r for r in g_match if r in g_official
                   or matches((r.get("Name") or "") + " " + (r.get("Description") or ""), ctx_terms)]
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
    seen_vids, seen_gaming = {}, {}
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
            # The same video surfaces in several platform searches; totals the
            # report quotes must count it once.
            for r in named:
                vid = r.get("Video ID") or r.get("URL") or r.get("Title")
                views = to_int(r.get("Views"))
                seen_vids[vid] = views
                if _GAMING_TERMS.search(r.get("Title", "") or ""):
                    seen_gaming[vid] = views

    short_name_items = 0
    if short_only:
        short_name_items = sum(
            1 for r in fan if not matches(r.get("Name", ""), full_terms))

    return {
        "brand": brand,
        "items_truncated": bool(notes.get("items_truncated")),
        "truncation_reasons": notes.get("reasons") or [],
        "items_short_name_only": short_name_items,
        "short_name": core_brand(brand) if short_only else "",
        "items_total": len(items),
        "items_official": len(official),
        "items_partner": len(partner_items),
        "partner_issuers": partner_issuers,
        "verified_unplaced": verified_unplaced,
        "platform": {k: platform.get(k) for k in ("checked", "error", "brand_entity",
                                                   "brand_partnerships_2y", "checked_at")}
        | {"brand_latest": (platform.get("brand_partnerships") or [None])[0]},
        # When any of these is true the copy may not assert absence: a verified
        # account is issuing the brand's items, a partner is placed, or the
        # platform holds partnership records for the brand itself.
        "presence_claim_blocked": bool(partner_items or verified_unplaced
                                       or (platform.get("brand_partnerships_2y") or 0)),
        "items_fan": len(fan),
        "items_named_raw": fan_named_raw,
        "context_label": context_label,
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
        "youtube_views_dedup": sum(seen_vids.values()),
        "youtube_videos_dedup": len(seen_vids),
        "youtube_gaming_share": (round(sum(seen_gaming.values()) / sum(seen_vids.values()), 2)
                                 if sum(seen_vids.values()) else None),
        # Suspect on either of two signals. The share floor catches a feed that
        # is mostly real-world footage. The top-video test catches a feed that
        # clears the floor on a long tail while its single biggest video is
        # real-world: Lidl passed at 0.39 with a 7.8m-view supermarket POV as
        # its most watched, which would have led the report.
        "youtube_suspect": bool(seen_vids) and (
            ((sum(seen_gaming.values()) / sum(seen_vids.values())) < YT_GAMING_FLOOR)
            or (max(seen_vids, key=seen_vids.get) not in seen_gaming)),
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
             "official": bool(is_official(r.get("Creator"))) or (r.get("Creator") or "").strip() in partner_of,
             "partner": partner_of.get((r.get("Creator") or "").strip())}
            for r in sorted(official + partner_items + fan_ranked, key=fav_key, reverse=True)[:3]
            if to_int(r.get("Favorites"))
        ],
        "top_creators": top_creators,
        "items_lead_word": len(lead_matched),
        "lead_word": lead,
        "items_keyword_soup": len(soup),
        "keyword_soup_fav_share": (round(soup_favs / fan_favs, 2)
                                   if fan_favs else 0.0),
        "keyword_soup_examples": [
            r["Name"] for r in sorted(soup, key=fav_key, reverse=True)[:3]],
        "platform_views": [
            {"platform": p.capitalize(), "views": v["views"], "videos": v["videos"],
             "top_video": v["top"].get("Title", "")}
            for p, v in yt.items() if v["views"]
        ],
        "near_official_creators": near,
        "official_via_partner": [f"{r['Name']} (run by {r.get('Creator')})"
                                 for r in g_by_partner],
        "sample_official": [r["Name"] for r in official[:8]],
        "sample_partner": [f"{r['Name']} (by {r.get('Creator')})" for r in partner_items[:8]],
        "sample_official_games": [f"{r['Name']} (by {r.get('Creator')})" for r in g_official[:8]],
        "sample_fan": [f"{r['Name']} (by {r['Creator']})" for r in fan[:8]],
        "sample_noise": [r["Name"] for r in noise_items[:8]],
    }


def candidates(a):
    """Candidate stats with exact formatted values. The model may only use these."""
    out = []
    # Marketplace counts collected up to a platform ceiling are floors, so they
    # carry a "+" everywhere they appear. The method strip says why.
    floor = "+" if a.get("items_truncated") else ""
    if a["combined_visits"]:
        # One matching experience is not "experiences". Name it instead: a
        # Shopkins report led with 95.4k visits "across shopkins experiences"
        # when exactly one fan game existed.
        top = a.get("top_game") or {}
        if a["games_matching"] == 1 and top.get("name"):
            visits_label = (f"lifetime visits to {top['name']}, the only "
                            f"{a['brand']} experience we found on Roblox")
        else:
            visits_label = f"lifetime visits across {a['brand']} experiences on Roblox"
        out.append({"num": fmt(a["combined_visits"]), "label": visits_label,
                    "_small_reach": a["combined_visits"] < 1_000_000})
    # Deduped: the per-platform sums count a video once per search it surfaced in.
    yt_views = a.get("youtube_views_dedup", 0)
    yt_videos = a.get("youtube_videos_dedup", 0)
    if yt_views and not a.get("youtube_suspect"):
        out.append({"num": fmt(yt_views),
                    "label": f"YouTube views on videos naming {a['brand']} "
                             f"surfaced by gaming searches"})
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
        out.append({"num": fmt(a["items_official"]) + floor,
                    "label": f"official {a['brand']} items on the marketplace"})
    if a.get("items_partner"):
        who = ", ".join(sorted({x["brand"] for x in a.get("partner_issuers") or []}))
        out.append({"num": fmt(a["items_partner"]),
                    "label": f"official {a['brand']} items on the marketplace, issued through {who}"})
    plat = a.get("platform") or {}
    if plat.get("brand_partnerships_2y"):
        n = plat["brand_partnerships_2y"]
        out.append({"num": str(n),
                    "label": f"{a['brand']} partnership{'s' if n != 1 else ''} in virtual worlds "
                             f"in the last two years, on the GEEIQ platform"})
    if a["items_fan"]:
        out.append({"num": fmt(a["items_fan"]) + floor,
                    "label": f"creator-made {a['brand']} items on the marketplace"})
    if a["distinct_creators"]:
        out.append({"num": fmt(a["distinct_creators"]) + floor,
                    "label": f"different creators making {a['brand']} content"})
    if a["top_game"] and a["top_game"]["visits"]:
        out.append({"num": fmt(a["top_game"]["visits"]),
                    "label": f"visits to the most popular {a['brand']} experience"})
    favs_usable = (a.get("keyword_soup_fav_share") or 0) < 0.5
    if a["top_item"] and a["top_item"]["favorites"] and favs_usable:
        out.append({"num": fmt(a["top_item"]["favorites"]),
                    "label": f"favourites on the most loved {a['brand']} item"})
    if a["avg_like_pct"]:
        out.append({"num": f"{a['avg_like_pct']}%",
                    "label": f"average rating across rated {a['brand']} experiences"})
    if yt_videos and not a.get("youtube_suspect"):
        out.append({"num": str(yt_videos),
                    "label": f"videos naming {a['brand']} across Roblox, "
                             f"Fortnite and Minecraft searches"})
    if a["live_players"]:
        out.append({"num": fmt(a["live_players"]),
                    "label": f"players inside {a['brand']} experiences at this snapshot"})

    # A visit count below a million cannot carry a page that also quotes 380m
    # monthly Roblox players: it makes the brand look small. When the creator
    # scene is the bigger story, that leads and the visits become context.
    small = [c for c in out if c.pop("_small_reach", False)]
    if small and (a["items_fan"] + a["items_official"]) >= 50:
        out = [c for c in out if c not in small] + small

    # A hero figure that needs apologising for is not a hero figure. When most
    # scanned videos were keyword collisions, push YouTube down to context so a
    # Roblox figure leads instead.
    if a.get("youtube_suspect"):
        # Contaminated by real-world videos naming the brand: no YouTube figure
        # is defensible, so none may appear anywhere in the report.
        out = [c for c in out if "YouTube" not in c["label"]
               and not c["label"].startswith("videos naming")]
    elif a.get("youtube_thin"):
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


def is_youtube_stat(stat):
    """YouTube never leads a report.

    It is the figure most easily inflated by real-world footage that merely
    names the brand, so it can support a report but never headline one. Lidl
    cleared the contamination floor at 0.39 and would otherwise have led with
    29m views whose top video was a supermarket POV.
    """
    label = (stat.get("label") or "").lower()
    return "video" in label or "youtube" in label


def demote_youtube(stats):
    """Move the first non-YouTube stat into the lead, if there is one."""
    if len(stats) > 1 and is_youtube_stat(stats[0]):
        i = next((n for n, st in enumerate(stats) if not is_youtube_stat(st)), None)
        if i is not None:
            stats.insert(0, stats.pop(i))
    return stats


def template_copy(a, cands):
    stats = cands[:6]
    if stats:
        demote_youtube(stats)
        stats[0] = {**stats[0], "coral": True}
    has_official = a["items_official"] or a["games_official"] or a.get("items_partner")
    partners = ", ".join(sorted({x["brand"] for x in a.get("partner_issuers") or []}))
    blocked = a.get("presence_claim_blocked")
    if has_official:
        angle = "official"
        if a.get("items_partner") and not a["items_official"] and not a["games_official"]:
            at_least = "at least " if a.get("items_truncated") else ""
            n = a['items_partner']
            headline = (f"{a['brand']} is on Roblox through {partners}, with {fmt(n)} official "
                        f"item{'s' if n != 1 else ''} on the marketplace")
            # Short on purpose: the hero card carries the visits figure, and a
            # three-line headline pushes the method strip off the page.
            headline += (", plus what players have built around it."
                         if a["combined_visits"] else
                         f", alongside {at_least}{fmt(a['items_fan'])} creator-made items.")
        elif a["games_official"] and a["official_visits"]:
            headline = (f"{a['brand']} runs an official presence on Roblox: "
                        f"{a['games_official']} live experience"
                        f"{'s' if a['games_official'] != 1 else ''} with "
                        f"{fmt(a['official_visits'])} lifetime visits, plus what "
                        "players have built around the brand.")
        elif a["combined_visits"]:
            headline = (f"{a['brand']} runs an official presence on Roblox, and players "
                        f"have built around it: {fmt(a['combined_visits'])} lifetime visits "
                        "across matching experiences.")
        elif (a["top_item"] and a["top_item"]["favorites"]
              and (a.get("keyword_soup_fav_share") or 0) < 0.5):
            at_least = "at least " if a.get("items_truncated") else ""
            headline = (f"{a['brand']} runs an official presence on Roblox: "
                        f"{at_least}{fmt(a['items_official'])} marketplace items, and "
                        f"the most loved has {fmt(a['top_item']['favorites'])} "
                        "favourites.")
        else:
            at_least = "at least " if a.get("items_truncated") else ""
            headline = (f"{a['brand']} runs an official presence on Roblox with "
                        f"{at_least}{fmt(a['items_official'])} items on the marketplace.")
    else:
        angle = "whitespace"
        at_least = "at least " if a.get("items_truncated") else ""
        # Fail closed. A verified account issuing the brand's items, or a
        # platform record, means absence cannot be asserted from this data.
        # Name what was found and stop there.
        ver = a.get("verified_unplaced") or []
        if blocked and ver:
            who = ver[0]["creator"]
            tail = (f", and {fmt(ver[0]['items'])} {a['brand']} item"
                    f"{'s' if ver[0]['items'] != 1 else ''} from {who}, a Roblox-verified account.")
        elif blocked:
            tail = ". The GEEIQ platform holds partnership records for the brand, see page notes."
        else:
            tail = ". None are official."
        if a["combined_visits"]:
            headline = (f"We found {fmt(a['combined_visits'])} lifetime visits across "
                        f"player-made {a['brand']} experiences on Roblox{tail}")
        else:
            headline = (f"We found {at_least}{fmt(a['items_fan'])} creator-made "
                        f"{a['brand']} items on the Roblox marketplace{tail}")
    tg = a["top_game"]
    reading_bits = []
    if angle == "whitespace" and blocked:
        reading_bits.append("Most of this presence is player-made; the accounts flagged "
                            "on the page need confirming before anything is called official or not.")
    elif angle == "whitespace":
        reading_bits.append("Players built this presence with no involvement from the brand.")
    elif a.get("items_partner") and not a["items_official"]:
        reading_bits.append(f"The official items come through {partners}, and a larger "
                            "creator-made footprint sits alongside them.")
    elif a["items_fan"] > a["items_official"]:
        reading_bits.append("The official catalogue sits alongside a larger creator-made footprint.")
    elif a["items_fan"]:
        reading_bits.append("A small creator-made footprint sits alongside the official catalogue.")
    else:
        reading_bits.append("The presence is almost entirely first party so far.")
    if tg:
        reading_bits.append(
            f"Attention concentrates in the standouts: {strip_emoji(tg['name'])} alone has "
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
        "Page two is a short primer on how virtual worlds work and how brands "
        "tend to enter them.\n\n"
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

Partners, absolute rule: figures.items_partner counts items issued for the brand
by a licensee or partner account named in figures.partner_issuers (for example
Cartoon Network Games issuing Mr Bean items). These ARE official presence:
credit them by partner name in the headline or reading, and never write that
the brand has no official presence when items_partner is above zero.

Fail closed, absolute rule: when figures.presence_claim_blocked is true you
may not assert absence in any form. Banned while blocked: "no official
presence", "none are official", "not official", "no brand presence", "built
entirely by players", "no involvement from the brand", "nothing official".
Describe what was found, name the verified accounts in figures.verified_unplaced
as "a Roblox-verified account", and leave the judgement to the analyst.

Scope, absolute rule: presence claims are always scoped to what was searched.
Write "no official presence on Roblox" or "on Roblox's marketplace", never "no
official presence anywhere" or "on any platform". Brands run activations
through partner studios and licensed games this data cannot see, and the
reader often knows about them.

If figures.youtube_suspect is true, the YouTube data is contaminated by
real-world videos that name the brand (product shorts, reviews): the report
and email must not mention YouTube at all. Do not lead with it, do not cite
it, do not allude to view counts.

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
- One line on what else the report covers: page two is a short primer on how
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


ABSENCE_RE = re.compile(
    r"\b(?:no|zero|without|not an?|lacks?|nothing)\s+(?:any\s+)?official"
    r"|\bnone\s+(?:are|is|of\s+\w+\s+(?:are|is))\s+official"
    r"|\bnot\s+official\b|\bno\s+brand\s+presence|\bbuilt\s+entirely\s+by\s+players"
    r"|\bno\s+involvement\s+from\s+the\s+brand|\bnothing\s+official"
    r"|\bno\s+official\s+studio", re.I)
WIDENED_RE = re.compile(
    r"official\s+presence\s+(?:anywhere|on\s+any\s+platform|in\s+(?:gaming|virtual\s+worlds))"
    r"|marketplace\s+or\s+in\s+its\s+experiences", re.I)


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
        # guardrail 3: no absence claims when the data cannot support one
        if a.get("presence_claim_blocked") or a.get("items_partner"):
            hit = ABSENCE_RE.search(prose)
            if hit:
                problems.append(f"absence claim not allowed for this brand: '{hit.group(0)}'")
        widened = WIDENED_RE.search(prose)
        if widened:
            problems.append(f"presence claim must stay scoped to the marketplace: '{widened.group(0)}'")
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
    from build_report import render as render_legacy
    try:
        from render_html import render
    except Exception:
        render = render_legacy

    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--csv-dir", help="skip collection, use CSVs from this dir")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-llm", action="store_true", help="force template copy")
    args = ap.parse_args()

    # Everything downstream prints this string, and all matching is
    # case-insensitive, so fix the casing once here rather than per label.
    args.brand = display_brand(args.brand)

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
    cands = demote_youtube(candidates(a))
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
                   "items_truncated": a.get("items_truncated", False),
                   "items_named_raw": a.get("items_named_raw", 0),
                   "context_label": a.get("context_label", ""),
               },
               "youtube_suspect": a.get("youtube_suspect", False),
               "top_games_named": print_safe(a["top_games_named"],
                                             "name", "creator"),
               "top_items_named": print_safe(a["top_items_named"],
                                             "name", "creator"),
               "name_users": [x for x in
                              (strip_emoji(n) for n
                               in (a.get("near_official_creators") or [])) if x],
               "top_creators": print_safe(a.get("top_creators"), "name"),
               "partner_issuers": a.get("partner_issuers") or [],
               "platform_check": a.get("platform") or {},
               "platform_views": a["platform_views"]}

    print("== rendering ==")
    stamp = datetime.date.today().strftime("%Y-%m")
    pdf_path = os.path.join(out_dir, f"GEEIQ_Brand_check_{args.brand.replace(' ', '_')}_{stamp}.pdf")
    try:
        render(payload, pdf_path)
        print("  renderer: html template")
    except Exception as e:
        print(f"  html renderer unavailable ({e}); using legacy layout")
        render_legacy(payload, pdf_path)

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
        plat = a.get("platform") or {}
        f.write("\n\nPLATFORM CHECK: " + (
            f"done {plat.get('checked_at')}. Brand entity: "
            f"{(plat.get('brand_entity') or {}).get('title') or 'not on the platform under this name'}; "
            f"{plat.get('brand_partnerships_2y') or 0} partnership records in two years"
            + (f", latest {plat['brand_latest']['game']} {plat['brand_latest']['start']} ({plat['brand_latest']['type']})"
               if plat.get("brand_latest") else "")
            if plat.get("checked") else f"NOT DONE: {plat.get('error')}. Do it by hand before approving."))
        if a.get("partner_issuers"):
            f.write("\n\nOFFICIAL VIA PARTNER: items issued by verified accounts the platform "
                    "or the licensee list places as the brand's partners: "
                    + "; ".join(f"{x['creator']} -> {x['brand']} ({x['items']} items"
                                + (f", {x['drops_2y']} item drops on the platform in two years" if x.get("drops_2y") else "")
                                + ")" for x in a["partner_issuers"]))
        if a.get("verified_unplaced"):
            f.write("\n\nVERIFIED, NOT PLACED: Roblox-verified accounts issuing brand-named "
                    "items that the platform does not place as partners. The report does "
                    "not call the presence absent while these exist; confirm each: "
                    + "; ".join(f"{x['creator']} ({x['items']} items)" for x in a["verified_unplaced"][:8]))
        if a.get("presence_claim_blocked"):
            f.write("\n\nPRESENCE CLAIM BLOCKED: the copy was not allowed to say the brand "
                    "has no official presence. Confirm the accounts above, then edit if absence is true.")
        if a.get("official_via_partner"):
            f.write("\n\nCounted as official on the strength of the experience "
                    "description, not the account name (a partner studio runs "
                    "these for the brand): "
                    + json.dumps(a["official_via_partner"]))
        if a.get("items_truncated"):
            f.write("\n\nCOUNTS ARE A FLOOR: the collection hit a platform limit, "
                    "so more marketplace items exist than were collected. "
                    "Reasons: " + "; ".join(a.get("truncation_reasons") or [])
                    + "\nThe report words these figures as 'at least N'.")
        if a.get("items_short_name_only"):
            f.write(f"\n\nSHORT-NAME MATCHES: {a['items_short_name_only']} matched "
                    f"items name only \"{a.get('short_name')}\", not the full "
                    f"submitted brand. Skim them: the short name can belong to "
                    f"something else entirely.")
        if a.get("items_lead_word"):
            f.write(f"\n\nSHORTENED-NAME MATCHES: {a['items_lead_word']} items do "
                    f"not carry the full brand name but lead with "
                    f"\"{a.get('lead_word')}\" alongside kit or season wording, so "
                    f"they are counted. Skim them: the lead word can belong to a "
                    f"place or another brand.")
        soup_share = a.get("keyword_soup_fav_share") or 0
        if a.get("items_keyword_soup"):
            f.write(f"\n\nKEYWORD-SOUP SPAM: {a['items_keyword_soup']} matched "
                    f"listings chain unrelated trending tokens around the brand "
                    f"word and are excluded from the top-item and highlight "
                    f"figures. They carry {soup_share:.0%} of all creator-made "
                    f"favourite volume. Examples: "
                    + json.dumps(a.get("keyword_soup_examples") or []))
            if soup_share >= 0.5:
                f.write(f"\n  WARNING: spam holds {soup_share:.0%} of favourite "
                        f"volume, so DO NOT quote any favourites figure for this "
                        f"brand. Lead on item and creator counts, which spam "
                        f"does not distort.")
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
        f.write("\nSample partner-issued rows: " + json.dumps(a.get("sample_partner") or []))
        f.write("\nSample official experiences: " + json.dumps(a["sample_official_games"]))
        f.write("\nSample creator-made rows: " + json.dumps(a["sample_fan"]))
        f.write("\nSample excluded rows: " + json.dumps(a["sample_noise"]))
        if copy.get("notes_for_analyst"):
            f.write("\n\nModel notes: " + copy["notes_for_analyst"])

    print(f"\nDone.\n  PDF: {pdf_path}\n  Email: {email_path}\n  Summary: {summary_path}")


if __name__ == "__main__":
    main()
