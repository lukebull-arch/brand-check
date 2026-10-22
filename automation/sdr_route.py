#!/usr/bin/env python3
"""Pick the SDR to copy in on a brand check delivery email, by the brand's sector.

Every report that goes out should put the lead in touch with the SDR who
covers their category, so the email carries one extra paragraph introducing
them and the approve handler (n8n) copies them in. The split is Luke's, 22 Oct
2026: Rachel takes fashion, retail, personal care, sports, financial services
and public services or internet apps; Cody takes food and drink, automotive,
toys, consumer electronics, media and entertainment, and leisure and travel.

The sector comes from one short Claude call on the brand name and the lead's
email domain (the domain separates Yale the lock maker from Yale the
university). A brand outside all twelve sectors gets the closest one and the
Slack draft says so, so the reviewer sees a stretch before approving. No API
key or a failed call means no CC at all, and the draft flags that loudly
rather than guessing.

Env: ANTHROPIC_API_KEY, BRAND_CHECK_MODEL (optional, same as run.py)
"""
import json
import os
import re
import urllib.request

SDRS = {
    "rachel": {"name": "Rachel", "full_name": "Rachel Ozsanlav-Harris",
               "email": "rachel@geeiq.com"},
    "cody": {"name": "Cody", "full_name": "Cody Gray",
             "email": "cody@geeiq.com"},
}

SECTORS = {
    "Fashion & Apparel": "rachel",
    "Retail": "rachel",
    "Personal Care & Cosmetics": "rachel",
    "Sports": "rachel",
    "Financial Services": "rachel",
    "Public Services / Internet apps": "rachel",
    "Food & Drink": "cody",
    "Automotive": "cody",
    "Toys & Collectables": "cody",
    "Consumer Electronics": "cody",
    "Media & Entertainment": "cody",
    "Leisure, Travel & Tourism": "cody",
}

SYSTEM = (
    "You route inbound leads to a sales rep by the sector of the brand they "
    "asked about. Pick exactly one sector from the list you are given. Sports "
    "covers clubs, leagues, governing bodies, athletes and sporting goods. "
    "Media & Entertainment covers film, TV, music, publishing, comics, licensed "
    "IP and video games. Retail covers shops, supermarkets and department "
    "stores; a brand that sells mainly its own products belongs to that "
    "product's sector. Public Services / Internet apps covers government "
    "bodies, charities, social media, ecommerce sites and consumer apps. If "
    "the brand fits one sector plainly, set fit to \"direct\". If it fits none "
    "of them (a pharma company, a telecoms network, an energy supplier), pick "
    "the closest and set fit to \"closest\". Respond with ONLY a JSON object: "
    "{\"sector\": str, \"fit\": \"direct\" | \"closest\", \"why\": str}, where "
    "why is at most twelve words.")


def classify(brand, email="", api_key=None):
    """Return {"sector", "fit", "why"} or raise. The sector is always a key of SECTORS."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    domain = email.split("@")[-1].lower() if "@" in email else ""
    prompt = (f"Brand: {brand}\n"
              f"Requester's email domain: {domain or 'unknown'}\n"
              f"Sectors: {json.dumps(list(SECTORS))}")
    # The model may think before answering, and a 200-token budget was spent
    # entirely on thinking for TodayTix (empty reply), so leave real headroom.
    body = {
        "model": os.environ.get("BRAND_CHECK_MODEL", "claude-sonnet-5"),
        "max_tokens": 2000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    err = None
    for _ in (1, 2):
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.load(r)
        text = "".join(b.get("text", "") for b in resp.get("content", []))
        try:
            return parse(text)
        except ValueError as e:
            err = e
    raise err


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError(f"no JSON in reply: {text[:120]!r}")
    out = json.loads(m.group(0))
    sector = out.get("sector")
    if sector not in SECTORS:
        # Tolerate case and spacing drift, never a sector outside the list.
        loose = {re.sub(r"[^a-z]", "", s.lower()): s for s in SECTORS}
        sector = loose.get(re.sub(r"[^a-z]", "", str(sector).lower()))
        if not sector:
            raise ValueError(f"sector not in the list: {out.get('sector')!r}")
    fit = out.get("fit") if out.get("fit") in ("direct", "closest") else "closest"
    return {"sector": sector, "fit": fit, "why": str(out.get("why") or "").strip()}


def route(brand, email="", api_key=None):
    """Who to copy in, and why. Never raises: on failure `sdr` is None and
    `error` says what went wrong, so the Slack draft can flag it."""
    try:
        c = classify(brand, email, api_key)
    except Exception as e:
        return {"sdr": None, "sector": None, "fit": None, "why": "",
                "error": f"{type(e).__name__}: {e}"}
    key = SECTORS[c["sector"]]
    return {"sdr": {"key": key, **SDRS[key]}, **c, "error": None}


def cc_paragraph(sdr_name):
    return (f"For even more detail, I've copied in my colleague {sdr_name}, who "
            "can take you through the entire brands and gaming landscape and "
            "what others in your category are doing.")


def add_cc_line(draft, sdr_name):
    """Insert the introduction as its own paragraph just above the sign-off.

    The sign-off is the last line holding the [analyst name] placeholder (both
    the Claude copy and the template fallback end that way). A draft without
    one gets the paragraph at the end, so the introduction is never lost."""
    para = cc_paragraph(sdr_name)
    lines = draft.rstrip("\n").split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if "[analyst name]" in lines[i]:
            head = "\n".join(lines[:i]).rstrip("\n")
            tail = "\n".join(lines[i:])
            return f"{head}\n\n{para}\n\n{tail}"
    return f"{draft.rstrip()}\n\n{para}"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Show which SDR a brand routes to.")
    ap.add_argument("brand")
    ap.add_argument("--email", default="")
    args = ap.parse_args()
    print(json.dumps(route(args.brand, args.email), indent=2))
