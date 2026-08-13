#!/usr/bin/env python3
"""Raise the MQL re-engagement alert when a brand check comes from an owned contact.

A brand check is a strong buying signal, and until now it was invisible to
sales: our form is not a HubSpot form, and the intake writes properties
straight through the API, so no HubSpot workflow enrols and nothing reaches
#mql-leads. An Aston Martin MQL requested a check, the run failed, and the
owner heard nothing.

This looks the contact up, and if it already has an owner, posts to the
existing "MQL — Re-engagement alert" workflow, which owns everything after
that: the Slack alert to the owner, the two hour SLA, the HubSpot task and
the chase if no activity is logged.

Deliberately quiet. No token, no contact, or no owner means it prints why and
exits 0, because a missing alert must never fail the report build.

Env: HUBSPOT_TOKEN (private app token, crm.objects.contacts.read + owners.read)
     REENGAGEMENT_WEBHOOK_URL (defaults to the live workflow)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

WEBHOOK = os.environ.get(
    "REENGAGEMENT_WEBHOOK_URL",
    "https://geeiq.app.n8n.cloud/webhook/32fe9b10-f95c-4519-88f5-e51a28482eae")

# What "Extract contact data" reads off the contact, so fetch exactly these.
CONTACT_PROPS = [
    "firstname", "lastname", "email", "jobtitle", "company", "lifecyclestage",
    "hubspot_owner_id", "recent_conversion_event_name", "hs_analytics_last_url",
    "hs_last_sales_activity_timestamp", "lead_score", "mql_health_bucket",
]
COMPANY_PROPS = ["name", "industry", "city", "country"]


def hs(path, token, method="GET", body=None):
    req = urllib.request.Request(
        f"https://api.hubapi.com{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def find_contact(email, token):
    res = hs("/crm/v3/objects/contacts/search", token, "POST", {
        "filterGroups": [{"filters": [
            {"propertyName": "email", "operator": "EQ", "value": email}]}],
        "properties": CONTACT_PROPS,
        "limit": 1,
    })
    results = res.get("results") or []
    return results[0] if results else None


def company_of(contact_id, token):
    try:
        assoc = hs(f"/crm/v4/objects/contacts/{contact_id}/associations/companies",
                   token).get("results") or []
        if not assoc:
            return {}
        cid = assoc[0]["toObjectId"]
        props = ",".join(COMPANY_PROPS)
        return hs(f"/crm/v3/objects/companies/{cid}?properties={props}",
                  token).get("properties") or {}
    except Exception as e:
        print(f"  company lookup skipped ({type(e).__name__})")
        return {}


def owner(owner_id, token):
    try:
        return hs(f"/crm/v3/owners/{owner_id}", token)
    except Exception as e:
        print(f"  owner lookup failed ({type(e).__name__})")
        return {}


def legacy_payload(contact, company, own):
    """The re-engagement workflow reads HubSpot's legacy webhook shape
    (properties.<field>.value), because a HubSpot workflow normally calls it.
    Build the same shape so that workflow needs no changes at all."""
    p = contact.get("properties") or {}
    return {
        "vid": int(contact["id"]),
        "properties": {k: {"value": v or ""} for k, v in p.items()},
        "associated-company": {
            "properties": {k: {"value": company.get(k) or ""} for k in COMPANY_PROPS}
        },
        "associated-owner": {
            "email": own.get("email", ""),
            "first-name": own.get("firstName", ""),
            "last-name": own.get("lastName", ""),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--brand", default="")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print the payload, post nothing")
    args = ap.parse_args()

    token = os.environ.get("HUBSPOT_TOKEN")
    if not token:
        print("HUBSPOT_TOKEN not set, skipping the owner alert.")
        return

    contact = find_contact(args.email, token)
    if not contact:
        print(f"No HubSpot contact for {args.email}, nothing to alert on.")
        return

    p = contact.get("properties") or {}
    owner_id = p.get("hubspot_owner_id")
    if not owner_id:
        print(f"{args.email} has no owner, so there is nobody to alert. "
              f"Lifecycle stage: {p.get('lifecyclestage') or 'unset'}.")
        return

    own = owner(owner_id, token)
    payload = legacy_payload(contact, company_of(contact["id"], token), own)
    who = own.get("email") or owner_id
    print(f"{args.email} is owned by {who} "
          f"(lifecycle: {p.get('lifecyclestage') or 'unset'}), alerting them.")

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return

    try:
        req = urllib.request.Request(
            WEBHOOK, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  re-engagement alert fired ({r.status}) for "
                  f"{args.brand or 'brand check'}")
    except urllib.error.HTTPError as e:
        print(f"  re-engagement webhook returned {e.code}; the report is "
              f"unaffected, but {who} was not alerted")
    except Exception as e:
        print(f"  re-engagement webhook unreachable ({type(e).__name__}); "
              f"{who} was not alerted")


if __name__ == "__main__":
    main()
    sys.exit(0)
