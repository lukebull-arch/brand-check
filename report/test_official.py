#!/usr/bin/env python3
"""Official-account classification tests.

The failure this guards against: on 10 Aug 2026 a Greggs report led with
"Greggs runs an official presence on Roblox" because the fan group "Gregg's TM"
normalised to "greggs". Telling a brand that an account imitating it is their
own is worse than reporting nothing, so exact names win and punctuation
variants need Roblox's own verified badge.

Run: python3 report/test_official.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("run", os.path.join(HERE, "run.py"))
run = importlib.util.module_from_spec(spec)
sys.modules["run"] = run
try:
    spec.loader.exec_module(run)
except SystemExit:
    pass


def classify(brand, creator, verified=False):
    """Mirror of analyse()'s is_official, over the module's own helpers."""
    off = run.official_creator_norms(brand)
    loose = run.loose_creator_norms(brand)
    if run._norm(creator) in off:
        return True
    return bool(verified) and run._loose(creator) in loose


# (brand, creator, verified, expected, why)
CASES = [
    # The live incident: every Greggs account on Roblox is fan-run, none verified.
    ("Greggs", "Gregg's™",          False, False, "the account that caused the bad report"),
    ("Greggs", "Gregg's",               False, False, "apostrophe variant, unverified"),
    ("Greggs", "Greggs Clothing Line",  False, False, "fan clothing group"),
    ("Greggs", "Greggs RBLX",           False, False, "fan group, self-declared unaffiliated"),
    ("Greggs", "Greggs RBLX",           True,  False, "even verified, the name is not the brand"),
    ("Greggs", "{UK} Greggs",           False, False, "decorated fan group"),
    ("Greggs", "Greg's (South West)",   False, False, "lookalike"),
    ("Greggs", "Greggs PLC | UK",       False, False, "fan group with corporate styling"),
    # Exact names still count, whatever the case.
    ("Greggs", "Greggs",                False, True,  "exact name"),
    ("Greggs", "greggs",                False, True,  "case only"),
    ("Greggs", "  GREGGS  ",            False, True,  "case and padding"),

    # Brands with a genuine official presence must survive the tightening.
    ("Walmart", "Walmart",              False, True,  "official, and carries no verified badge"),
    ("adidas",  "adidas",               False, True,  "official marketplace account"),
    ("Gucci",   "Gucci",                False, True,  "official"),
    ("adidas",  "adidas Originals",     False, False, "sub-brand variant, unverified"),

    # The 30 Jul undercounting fix must keep working.
    ("Pizza Hut", "Pizza Hut",          False, True,  "exact"),
    ("Pizza Hut", "PizzaHut",           False, True,  "spacing only"),
    ("Pizza Hut", "Pizza Hut Official", False, True,  "official suffix"),
    ("Pizza Hut Official", "Pizza Hut", False, True,  "submitted with suffix, account without"),

    # Fan groups that merely contain the brand name are not the brand. The old
    # substring-plus-badge rule let these through.
    ("KFC", "KFC | Roblox",             False, False, "fan group"),
    ("KFC", "KFC | Roblox",             True,  False, "substring plus badge is not enough"),
    ("KFC", "MSL Games",                True,  False, "verified fan studio"),
    ("KFC", "KFC",                      False, True,  "exact"),

    # Punctuation variants are recoverable, but only via the badge.
    ("McDonalds", "McDonald's",         True,  True,  "verified punctuation variant"),
    ("McDonalds", "McDonald's",         False, False, "same name, unverified, stays creator-made"),
]


def main():
    failures = []
    for brand, creator, verified, expected, why in CASES:
        got = classify(brand, creator, verified)
        ok = got == expected
        if not ok:
            failures.append((brand, creator, verified, expected, got, why))
        print(f"{'ok  ' if ok else 'FAIL'} {brand:20} {creator!r:24} "
              f"verified={str(verified):5} official={got!s:5} ({why})")

    print()
    if failures:
        print(f"{len(failures)} of {len(CASES)} FAILED")
        for f in failures:
            print("   ", f)
        return 1
    print(f"all {len(CASES)} cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
