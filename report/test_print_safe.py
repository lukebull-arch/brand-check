#!/usr/bin/env python3
"""Regression tests for print-safe display text.

The report embeds Figtree and Plus Jakarta Sans, which cover Latin only. Every
case here reached a rendered PDF at some point: Apple Color Emoji as a Type 3
bitmap font, "KAPPO[]" from an invisible U+115F Hangul filler, and creator
names in scripts the fonts cannot draw at all.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("run", os.path.join(HERE, "run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

CASES = [
    # emoji and decoration removed, the name survives
    ("⭐Aston Villa Flag⭐", "Aston Villa Flag"),
    ("⚽ Brighton & Hove Albion Bucket Hat ⚽",
     "Brighton & Hove Albion Bucket Hat"),
    ("We love shopping in Lidl ☁️✨\U0001f602",
     "We love shopping in Lidl"),
    ("aston villa grealish top! ✰ ° . °",
     "aston villa grealish top!"),
    # invisible padding characters that render as a hollow box
    ("KAPPOᅟ", "KAPPO"),
    ("Tesco Expressㅤ", "Tesco Express"),
    # trademark glyphs stay: an imitator must not be shown as the brand
    ("Tesco™", "Tesco™"),
    ("Gregg's™", "Gregg's™"),
    # Latin Extended is renderable and must be preserved
    ("thé rõsèmárý lânés",
     "thé rõsèmárý lânés"),
    ("Louis’s world!", "Louis’s world!"),
    ("b o l d customs", "b o l d customs"),
    # nothing renderable: must return empty so the caller drops the row,
    # never the original, which is how a box reaches the page
    ("АЛЕКСЕЙ", ""),
    ("ทนอัี", ""),
    ("\U0001f602\U0001f602\U0001f602", ""),
    ("₣ⱠɎł₦₲ ₵₳Ɱ", ""),
]


def main():
    failed = 0
    for raw, want in CASES:
        got = run.strip_emoji(raw)
        if got != want:
            failed += 1
            print(f"FAIL {raw!r}\n     got  {got!r}\n     want {want!r}")
    rows = [{"name": "АЛЕКСЕЙ", "items": 5},
            {"name": "vox box", "items": 29}]
    kept = run.print_safe(rows, "name")
    if [r["name"] for r in kept] != ["vox box"]:
        failed += 1
        print(f"FAIL print_safe kept {kept}")
    print(f"{len(CASES) + 1 - failed}/{len(CASES) + 1} print-safety cases correct")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
