#!/usr/bin/env python3
"""Regression tests for whole-word brand matching.

A plain substring match put a false 20m-visit headline on an Aldi report:
"aldi" sits inside "Maldivian Hotel and Resort" (17.5m visits), "SubterBaldi"
and "Raldi's CrackHouse". Short brand names are inside ordinary words often
enough that the word boundary is not optional.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("run", os.path.join(HERE, "run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

CASES = [
    # the three rows that produced the false Aldi headline
    ({"aldi"}, "[UPD] Maldivian Hotel and Resort", False),
    ({"aldi"}, "SubterBaldi: Legacy", False),
    ({"aldi"}, "(Pizza Mode) Raldi's CrackHouse Roblox Recreation", False),
    ({"aldi"}, "Garaldi jacket", False),
    ({"aldi"}, "Waldi", False),
    # genuine mentions still match, including possessives and casing
    ({"aldi"}, "Aldi Uniform", True),
    ({"aldi"}, "aldi", True),
    ({"aldi"}, "ALDI Shirt Worker Retail Uniform", True),
    ({"aldi"}, "Aldi's Trolley", True),
    # other brands that share the failure mode
    ({"kfc"}, "KFC Bucket Hat", True),
    ({"kfc"}, "MKFCS clothing", False),
    ({"lidl"}, "Lidl Pants", True),
    ({"lidl"}, "unlidled fury", False),
    ({"tesco"}, "tesco uniform", True),
    ({"tesco"}, "intescopable", False),
    # the despaced variant still works as a whole token
    ({"aston villa", "astonvilla"}, "AstonVilla Kit", True),
    ({"brighton & hove albion"}, "Brighton & Hove Albion GK Kit 2024/25 SS", True),
    ({"brighton & hove albion"}, "Brighton Home Kit 22-23", False),
]


def main():
    failed = 0
    for terms, name, want in CASES:
        got = run.matches(name, terms)
        if got != want:
            failed += 1
            print(f"FAIL match={got} want={want}: {name!r} vs {sorted(terms)}")
    print(f"{len(CASES) - failed}/{len(CASES)} matching cases correct")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
