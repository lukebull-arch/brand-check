#!/usr/bin/env python3
"""Regression tests for the keyword-soup guard.

A Lidl run put "xorowhair lidl tatsumaki narcissist monterrey ymir" (22,087
favourites) at the top of a report bound for Lidl's Head of Brand Engagement.
The listing genuinely names the brand, so Brand Match passed it; 99% of Lidl's
whole favourite volume came from listings shaped like that.

Two ways to get this wrong, so both are tested: missing real spam, and
condemning real fan items. Long names are NOT the signal, because football kit
names are long and legitimate.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("run", os.path.join(HERE, "run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

CASES = [
    # keyword-stuffing spam: bare proper nouns chained around the brand word
    ("xorowhair lidl tatsumaki narcissist monterrey ymir", ["Lidl"], True),
    ("sigmund nbayoungboy lidl beyonce yoosung eggphone", ["Lidl"], True),
    ("dax tenjiku chrollo yasuo lidl housemaid redhood", ["Lidl"], True),
    ("yanfei partygoer lidl cutlass ymir tiko artificial", ["Lidl"], True),
    ("tiko doma beyonce cornrows sigmund nekomancer lidl", ["Lidl"], True),
    # genuine fan items, short
    ("Lidl Pants", ["Lidl"], False),
    ("Ant - Lidl Shirt", ["Lidl"], False),
    ("Aston Villa", ["Aston Villa"], False),
    ("Tesco Top w/ Vest", ["Tesco"], False),
    # genuine and long: kit names carry season, keeper and player detail
    ("Brighton & Hove Albion Home Shorts 20 - 21", ["Brighton & Hove Albion"], False),
    ("Brighton & Hove Albion GK Kit 2024/25 SS", ["Brighton & Hove Albion"], False),
    ("Mitoma Brighton & Hove Albion Kit", ["Brighton & Hove Albion"], False),
    ("Brighton Hove Albion 2025 Ferdi Kadioglu LS", ["Brighton & Hove Albion"], False),
    ("Aldi Shirt Worker Retail Uniform", ["Aldi"], False),
    # genuine and long: meme phrasing, rescued by function words
    ("i lost my mum at tesco (pls help)", ["Tesco"], False),
    ("pull up outside tesco [MEME T-SHIRT]", ["Tesco"], False),
    ("Primark Set - Chav Tesco", ["Tesco"], False),
    ("Aston Villa's Champions League", ["Aston Villa"], False),
]


def main():
    failed = 0
    for name, terms, want in CASES:
        got = run.is_keyword_soup(name, terms)
        if got != want:
            failed += 1
            print(f"FAIL soup={got} want={want}: {name!r}")
    print(f"{len(CASES) - failed}/{len(CASES)} keyword-soup cases correct")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
