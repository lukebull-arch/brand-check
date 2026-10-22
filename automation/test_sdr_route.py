#!/usr/bin/env python3
"""Regression tests for the SDR copy-in on delivery emails.

Offline: these cover the sector table, reply parsing and where the
introduction lands in the draft. The live sector call is exercised with
`python3 automation/sdr_route.py "<brand>" --email <lead email>`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdr_route  # noqa: E402

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")


# Luke's split, 22 Oct 2026: six sectors each
rachel = sorted(s for s, k in sdr_route.SECTORS.items() if k == "rachel")
cody = sorted(s for s, k in sdr_route.SECTORS.items() if k == "cody")
check("rachel sectors", rachel, sorted([
    "Fashion & Apparel", "Retail", "Personal Care & Cosmetics", "Sports",
    "Financial Services", "Public Services / Internet apps"]))
check("cody sectors", cody, sorted([
    "Food & Drink", "Automotive", "Toys & Collectables", "Consumer Electronics",
    "Media & Entertainment", "Leisure, Travel & Tourism"]))
check("rachel email", sdr_route.SDRS["rachel"]["email"], "rachel@geeiq.com")
check("cody email", sdr_route.SDRS["cody"]["email"], "cody@geeiq.com")

# Reply parsing: exact, drifted case and spacing, prose around the JSON
check("parse exact", sdr_route.parse('{"sector": "Food & Drink", "fit": "direct", "why": "pizza chain"}'),
      {"sector": "Food & Drink", "fit": "direct", "why": "pizza chain"})
check("parse drift", sdr_route.parse('Here: {"sector": "toys & collectables", "fit": "direct", "why": ""}')["sector"],
      "Toys & Collectables")
check("parse unknown fit", sdr_route.parse('{"sector": "Sports", "fit": "maybe"}')["fit"], "closest")
for bad in ('{"sector": "Pharma", "fit": "direct"}', "no json here", ""):
    try:
        sdr_route.parse(bad)
        check(f"parse rejects {bad!r}", "accepted", "ValueError")
    except ValueError:
        pass

# route() never raises: no key means no SDR and a reason
saved = os.environ.pop("ANTHROPIC_API_KEY", None)
r = sdr_route.route("KFC", "a@kfc.com")
check("no key, no sdr", r["sdr"], None)
check("no key, says why", "ANTHROPIC_API_KEY" in (r["error"] or ""), True)
if saved:
    os.environ["ANTHROPIC_API_KEY"] = saved

# The introduction sits in its own paragraph directly above the sign-off
draft = ("Subject: Your GEEIQ brand check: KFC\n\n"
         "Hi [first name],\n\n"
         "Thanks for asking us to look at KFC.\n\n"
         "If you would like a walkthrough, reply to this email and I will set up 20 minutes.\n\n"
         "[analyst name], GEEIQ")
out = sdr_route.add_cc_line(draft, "Cody")
para = sdr_route.cc_paragraph("Cody")
check("cc above sign-off", out.endswith(f"I will set up 20 minutes.\n\n{para}\n\n[analyst name], GEEIQ"), True)
check("cc once", out.count(para), 1)
check("subject kept", out.startswith("Subject: Your GEEIQ brand check: KFC\n\n"), True)
check("names the sdr", "my colleague Cody," in para, True)
check("no em dash", "—" in para or "–" in para, False)

# Sign-off with trailing blank lines, and a draft with no sign-off at all
check("trailing newlines", sdr_route.add_cc_line(draft + "\n\n", "Rachel").endswith(
    f"{sdr_route.cc_paragraph('Rachel')}\n\n[analyst name], GEEIQ"), True)
check("no sign-off appends", sdr_route.add_cc_line("Hi there,\n\nBody.", "Rachel"),
      f"Hi there,\n\nBody.\n\n{sdr_route.cc_paragraph('Rachel')}")

print(f"{'FAILED' if fails else 'ok'}: test_sdr_route ({fails} failure{'s' if fails != 1 else ''})")
sys.exit(1 if fails else 0)
