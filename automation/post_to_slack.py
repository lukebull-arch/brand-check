#!/usr/bin/env python3
"""Post a finished brand check draft to Slack for approval.

Uploads the PDF to the review channel, then posts the summary message with
Approve / Reject buttons. The button values carry everything the approval
handler (n8n) needs to send the email without further lookups.

Env: SLACK_BOT_TOKEN (xoxb-, scopes chat:write + files:write),
     SLACK_CHANNEL_ID (the channel's ID, e.g. C0XXXXXXX)
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

TOKEN = os.environ["SLACK_BOT_TOKEN"]
CHANNEL = os.environ["SLACK_CHANNEL_ID"]


def slack(method, payload=None, form=None):
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        ctype = "application/json; charset=utf-8"
    req = urllib.request.Request(
        f"https://slack.com/api/{method}", data=data,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if not out.get("ok"):
        sys.exit(f"Slack {method} failed: {out.get('error')}")
    return out


def upload_pdf(path, title):
    """files.upload is deprecated; use the external upload flow."""
    size = os.path.getsize(path)
    got = slack("files.getUploadURLExternal",
                form={"filename": os.path.basename(path), "length": size})
    with open(path, "rb") as f:
        req = urllib.request.Request(got["upload_url"], data=f.read(), method="POST")
        urllib.request.urlopen(req, timeout=120)
    slack("files.completeUploadExternal", payload={
        "files": [{"id": got["file_id"], "title": title}],
        "channel_id": CHANNEL,
    })
    return got["file_id"]


def confirm_dialog(title, text, yes):
    return {"title": {"type": "plain_text", "text": title},
            "text": {"type": "mrkdwn", "text": text},
            "confirm": {"type": "plain_text", "text": yes},
            "deny": {"type": "plain_text", "text": "Cancel"}}


def review_flags(summary_path, brand):
    """The warnings a reviewer needs at decision time, from the analyst summary.

    A KTM draft claimed no official presence while the GEEIQ platform tracked
    two partnerships, and its 98m YouTube figure was real-world motorbike
    videos. Both warnings existed in the artifact; neither reached Slack. This
    puts them next to the Approve button.
    """
    lines = []
    data = {}
    try:
        import re as _re
        text = open(summary_path).read()
        m = _re.search(r"\{.*\}", text, _re.S)
        if m:
            data = json.loads(m.group(0))
    except Exception as e:
        lines.append(f":warning: could not read analyst summary ({e}); "
                     "review the artifact before approving.")

    if data.get("items_truncated"):
        why = "; ".join((data.get("truncation_reasons") or [])[:2])
        lines.append(f":scissors: *Marketplace counts are a floor:* the pull hit a "
                     f"platform limit, so more items exist than were collected. "
                     f"{why}. The report words these as \"at least N\".")

    if data.get("items_short_name_only"):
        lines.append(f":grey_question: *{data['items_short_name_only']} matches name "
                     f"only `{data.get('short_name')}`,* not the full brand. Worth a "
                     "skim: the short name can belong to something else.")

    near = data.get("near_official_creators") or []
    if near:
        shown = ", ".join(f"`{n}`" for n in near[:6])
        more = f" (+{len(near) - 6} more)" if len(near) > 6 else ""
        lines.append(f":mag: *Accounts naming the brand, counted as fan-made:* "
                     f"{shown}{more}. Imitators mostly, but a partner running a "
                     "sponsored activation looks identical in the data.")

    partner = data.get("official_via_partner") or []
    if partner:
        lines.append(":handshake: *Counted as official from the experience "
                     "description, not the account name:* "
                     + "; ".join(partner[:4]))

    if data.get("youtube_suspect"):
        share = data.get("youtube_gaming_share")
        pct = f"{int(share * 100)}%" if isinstance(share, (int, float)) else "few"
        lines.append(f":no_entry: *YouTube figures dropped from the report:* only "
                     f"{pct} of the named view volume looks like gaming content. "
                     "The rest is real-world videos naming the brand.")
    elif data.get("youtube_thin"):
        lines.append(":warning: *YouTube signal is thin:* most scanned videos "
                     "were keyword collisions; the figure is demoted, not led with.")

    q = urllib.parse.quote(brand)
    lines.append(f":globe_with_meridians: *Before approving:* check "
                 f"<https://app.geeiq.com/search?q={q}|the GEEIQ platform> for "
                 "partnerships and owned experiences the public data cannot see. "
                 "The report must not contradict the platform.")

    # The runner has no web access, and platform APIs cannot see inside an
    # experience. An Aston Martin check reported nothing while Voldex had
    # publicly announced ten licensed Aston Martin cars in Driving Empire. Ten
    # seconds of searching here is the only guard against repeating that.
    g = urllib.parse.quote(f"{brand} Roblox partnership")
    g2 = urllib.parse.quote(f"{brand} Fortnite OR Minecraft game partnership")
    lines.append(f":mag_right: *And search the web:* "
                 f"<https://www.google.com/search?q={g}|{brand} Roblox partnership> "
                 f"| <https://www.google.com/search?q={g2}|other platforms>. "
                 "Licensed cars, wearables and in-game events never appear in "
                 "the collected data. Announcements usually sit on the partner "
                 "studio's site, not the brand's.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--email", default="")
    ap.add_argument("--first-name", default="")
    ap.add_argument("--hubspot-url", default="")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--email-draft", required=True)
    ap.add_argument("--summary", default="", help="analyst_summary.txt path")
    args = ap.parse_args()

    draft = open(args.email_draft).read().strip()

    file_id = upload_pdf(args.pdf, f"Brand check draft: {args.brand}")

    # Vetting signal: does the lead's email domain plausibly belong to the brand?
    brand_slug = "".join(c for c in args.brand.lower() if c.isalnum())
    domain = args.email.split("@")[-1].lower() if "@" in args.email else ""
    domain_slug = "".join(c for c in domain.split(".")[0] if c.isalnum()) if domain else ""
    if brand_slug and domain_slug and (brand_slug in domain_slug or domain_slug in brand_slug):
        domain_check = ":white_check_mark: email domain matches the brand"
    else:
        domain_check = (":warning: email domain does not obviously match the brand. "
                        "Could be an agency or parent company, your call.")

    meta = json.dumps({
        "brand": args.brand, "email": args.email,
        "firstName": args.first_name, "fileId": file_id,
    })
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"Draft ready: {args.brand}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Lead*\n{args.first_name or 'n/a'} · {args.email or 'n/a'}"},
            {"type": "mrkdwn", "text": f"*Brand*\n{args.brand}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Identity check*\n{domain_check}"}},
        {"type": "section", "text": {"type": "mrkdwn",
            "text": "*Review flags*\n" + review_flags(args.summary, args.brand)}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*Email that will be sent on approval:*\n```{draft[:2500]}```"}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "action_id": "brand_check_approve",
             "text": {"type": "plain_text", "text": "Approve and send"}, "value": meta,
             "confirm": confirm_dialog(
                 "Send the report?",
                 f"This emails the {args.brand} PDF to {args.email}.", "Send it")},
            {"type": "button", "style": "danger", "action_id": "brand_check_decline",
             "text": {"type": "plain_text", "text": "Decline: not from brand"}, "value": meta,
             "confirm": confirm_dialog(
                 "Decline this request?",
                 f"This tells {args.email} we could not connect them to {args.brand}.", "Decline")},
            {"type": "button", "action_id": "brand_check_discard",
             "text": {"type": "plain_text", "text": "Discard (spam)"}, "value": meta,
             "confirm": confirm_dialog(
                 "Discard this request?",
                 "Nothing is sent to the requester.", "Discard")},
        ]},
    ]
    if args.hubspot_url:
        blocks.insert(2, {"type": "section", "text": {
            "type": "mrkdwn", "text": f"<{args.hubspot_url}|View contact in HubSpot>"}})

    slack("chat.postMessage", payload={
        "channel": CHANNEL,
        "text": f"Brand check draft ready: {args.brand}",
        "blocks": blocks,
    })
    print("posted to Slack")


if __name__ == "__main__":
    main()
