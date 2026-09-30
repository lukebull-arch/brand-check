#!/usr/bin/env python3
"""Partner-run presence and the fail-closed copy rule.

The failure this guards against: on 29 Sep 2026 a Mr Bean draft told the IP
owner's Global Head of Brand that Mr Bean had "no official brand presence on
Roblox's marketplace" while the same page listed eight Mr Bean items by
Cartoon Network Games, Cartoon Network's verified Roblox group, issued for two
licensed activations. The string test (creator name == brand name) cannot see
a partner, and the copy turned its zero into an absence claim. Same shape as
True and the Rainbow Kingdom (cSapphire capsule), Aston Martin and KTM
(Driving Empire).

Three rules, all here:
1. A verified account that a known licensee entry or a platform partnership
   record places for the brand is official via partner. Its items leave the
   creator-made bucket and the copy credits the partner by name.
2. A verified account nobody can place stays creator-made, but blocks every
   absence claim ("no official", "none are official", "built entirely by
   players") in template and model copy alike.
3. An unverified account merely named like a licensee is an imitator: not a
   partner, and not a reason to block.

Run: BRAND_CHECK_NO_PLATFORM=1 python3 report/test_partner.py
"""
import csv
import importlib.util
import os
import sys
import tempfile

os.environ["BRAND_CHECK_NO_PLATFORM"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("run", os.path.join(HERE, "run.py"))
run = importlib.util.module_from_spec(spec)
sys.modules["run"] = run
try:
    spec.loader.exec_module(run)
except SystemExit:
    pass

ITEM_COLS = ["Name", "ID", "URL", "Creator", "Creator Type", "Creator ID",
             "Creator Verified", "Price", "Favorites", "Item Type", "Created"]
GAME_COLS = ["Name", "ID", "Universe ID", "URL", "Like %", "Active Players", "Creator",
             "Up Votes", "Down Votes", "Sponsored", "Visits", "Favorites", "Creator Type",
             "Verified Creator", "Description"]


def write(dirpath, items, games=()):
    with open(os.path.join(dirpath, "roblox_catalog_items.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ITEM_COLS)
        w.writeheader()
        for i, r in enumerate(items):
            row = {c: "" for c in ITEM_COLS}
            row.update({"ID": str(1000 + i), "Item Type": "Asset", "Created": "2025-06-01",
                        "Price": "0", "Favorites": "10"})
            row.update(r)
            w.writerow(row)
    with open(os.path.join(dirpath, "roblox_games.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=GAME_COLS)
        w.writeheader()
        for i, r in enumerate(games):
            row = {c: "" for c in GAME_COLS}
            row.update({"ID": str(5000 + i), "Universe ID": str(6000 + i), "Like %": "90",
                        "Active Players": "5", "Visits": "1000", "Favorites": "10"})
            row.update(r)
            w.writerow(row)


def item(name, creator, ctype="Group", cid="", verified="", favs="10"):
    return {"Name": name, "Creator": creator, "Creator Type": ctype, "Creator ID": cid,
            "Creator Verified": verified, "Favorites": favs}


FAN = [item("Mr Bean Head", "Meme UGC", cid="1"),
       item("Mr Bean Suit", "Beetro", cid="2"),
       item("mr bean teddy", "rwila", cid="3"),
       item("Brookhaven", "Wolfpaq", cid="4")]          # noise
CN = [item(f"Mr Bean - Teddy {k}", "Cartoon Network Games", cid="5544719", verified="yes",
           favs=str(3000 + k)) for k in range(8)]


def analyse(items, games=(), brand="Mr Bean"):
    with tempfile.TemporaryDirectory() as d:
        write(d, items, games)
        return run.analyse(d, brand)


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


# 1. known licensee by group id -> official via partner
a = analyse(FAN + CN)
check("known licensee items leave the fan bucket", a["items_partner"] == 8 and a["items_fan"] == 3,
      f"partner={a['items_partner']} fan={a['items_fan']}")
check("partner issuer named", a["partner_issuers"] and a["partner_issuers"][0]["brand"] == "Cartoon Network")
check("presence claim blocked when a partner exists", a["presence_claim_blocked"])
check("top item is the partner's, labelled",
      a["top_items_named"][0]["partner"] == "Cartoon Network" and a["top_items_named"][0]["official"])
cands = run.demote_youtube(run.candidates(a))
copy = run.template_copy(a, cands)
check("template headline credits the partner", "through Cartoon Network" in copy["headline"], copy["headline"])
check("template headline makes no absence claim", not run.ABSENCE_RE.search(copy["headline"] + " " + copy["reading"]),
      copy["headline"] + " | " + copy["reading"])
check("a partner stat is offered to the model",
      any("issued through Cartoon Network" in c["label"] for c in cands))

# 2. verified account nobody can place: creator-made, but blocks absence
V = [item("Mr Bean Face", "Tilted Tree Studios", cid="77", verified="yes", favs="500")]
a = analyse(FAN + V)
check("unplaced verified account stays creator-made", a["items_partner"] == 0 and a["items_fan"] == 4,
      f"partner={a['items_partner']} fan={a['items_fan']}")
check("unplaced verified account is listed", a["verified_unplaced"] and a["verified_unplaced"][0]["creator"] == "Tilted Tree Studios")
check("presence claim blocked by a verified issuer", a["presence_claim_blocked"])
copy = run.template_copy(a, run.demote_youtube(run.candidates(a)))
check("blocked template names the verified account", "Tilted Tree Studios" in copy["headline"], copy["headline"])
check("blocked template makes no absence claim",
      not run.ABSENCE_RE.search(copy["headline"] + " " + copy["reading"]), copy["headline"] + " | " + copy["reading"])

# 3. unverified imitator named like a licensee: neither partner nor block
I = [item("Mr Bean Jacket", "Cartoon Network Games", cid="999", verified="")]
a = analyse(FAN + I)
check("unverified lookalike of a licensee is not a partner", a["items_partner"] == 0)
check("unverified lookalike does not block", not a["presence_claim_blocked"])

# 4. plain whitespace: absence may be stated
a = analyse(FAN)
check("nothing verified: not blocked", not a["presence_claim_blocked"])
copy = run.template_copy(a, run.demote_youtube(run.candidates(a)))
check("plain whitespace template may say none are official", "None are official" in copy["headline"], copy["headline"])

# 5. partner-run experience counts as official
G = [{"Name": "Cartoon Network Game On", "Creator": "Cartoon Network Games", "Creator Type": "Group",
      "Verified Creator": "yes", "Visits": "71341808", "Description": "Theme park tycoon"}]
a = analyse(FAN + CN, G)
check("partner-run experience is official", a["games_official"] == 1 and a["official_visits"] == 71341808,
      f"games_official={a['games_official']} visits={a['official_visits']}")

# 6. the copy guardrails
for text in ["Mr Bean has no official brand presence on Roblox's marketplace",
             "Everything here was built entirely by players",
             "None are official.",
             "a well-loved character with no official studio in the space",
             "with no involvement from the brand"]:
    check(f"ABSENCE_RE catches: {text[:40]}", run.ABSENCE_RE.search(text))
for text in ["The official items come through Cartoon Network.",
             "8 official Mr Bean items on the marketplace, issued through Cartoon Network"]:
    check(f"ABSENCE_RE leaves alone: {text[:40]}", not run.ABSENCE_RE.search(text))
check("WIDENED_RE catches marketplace-or-experiences",
      run.WIDENED_RE.search("no official presence on Roblox's marketplace or in its experiences"))
check("WIDENED_RE catches anywhere", run.WIDENED_RE.search("no official presence anywhere"))
check("WIDENED_RE leaves scoped claim alone", not run.WIDENED_RE.search("no official presence on Roblox's marketplace."))

# 7. known_licensee matching rules
check("known licensee by id", run.known_licensee("Cartoon Network Games", "5544719", False) == "Cartoon Network")
check("known licensee by name needs the badge", run.known_licensee("Cartoon Network Games", "1", False) is None)
check("known licensee by name with badge", run.known_licensee("cartoon network games", "1", True) == "Cartoon Network")

passed = sum(1 for _, ok in results if ok)
print(f"\n{passed}/{len(results)} partner cases correct")
sys.exit(0 if passed == len(results) else 1)
