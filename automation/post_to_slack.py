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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--email", default="")
    ap.add_argument("--first-name", default="")
    ap.add_argument("--hubspot-url", default="")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--email-draft", required=True)
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
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*Email that will be sent on approval:*\n```{draft[:2500]}```"}},
        {"type": "actions", "elements": [
            {"type": "button", "style": "primary", "action_id": "brand_check_approve",
             "text": {"type": "plain_text", "text": "Approve and send"}, "value": meta},
            {"type": "button", "style": "danger", "action_id": "brand_check_decline",
             "text": {"type": "plain_text", "text": "Decline: not from brand"}, "value": meta},
            {"type": "button", "action_id": "brand_check_discard",
             "text": {"type": "plain_text", "text": "Discard (spam)"}, "value": meta},
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
