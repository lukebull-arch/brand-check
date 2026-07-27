# Brand check — n8n workflow (build 3)

Importable workflow for the brand check page. Follows the same conventions as
the existing "Framer Demo Form" and MQL workflows on geeiq.app.n8n.cloud:
silent 200 discard for anything blocked, HubSpot batch upsert by email,
Slack alert via chat.postMessage with the stored Slack credential.

## What it does

```
Webhook (POST /webhook/brand-check)
  -> Validate submission   honeypot, speed, origin, fields, business email,
                           rate limit (30/hour), repeat flag (same email in 24h)
  -> Passed?
       no  -> Respond 200 "OK"        (silent discard, bots learn nothing)
       yes -> Upsert HubSpot contact  (firstname, lastname, email, jobtitle,
                                       lead status NEW, legal basis consent)
           -> Prepare alert           (builds the HubSpot record link)
           -> Slack #brand-check-leads (brand, name, role, email, repeat flag,
                                        page URL, View in HubSpot button)
           -> Respond 200 "OK"
```

If HubSpot or Slack errors, the webhook returns a 5xx and the front end shows
its failure message with the button re-enabled, so the lead can retry.

## Setup

1. **Import**: n8n > Workflows > Import from file > `brand-check-workflow.json`.
2. **HubSpot token**: open "Upsert HubSpot Contact" and replace
   `REPLACE_WITH_HUBSPOT_PRIVATE_APP_TOKEN` with the same private app token the
   Framer Demo Form workflow uses. (Better: move that token into an n8n
   credential; today it sits in plain text inside the workflows.)
3. **Slack**: open "Notify team in Slack" and pick the existing Slack API
   credential (same one the MQL workflows use). Create the `#brand-check-leads`
   channel, or change the channel in the node's JSON body. Invite the n8n bot
   to the channel.
4. **Activate** the workflow. The production URL is:
   `https://geeiq.app.n8n.cloud/webhook/brand-check`
5. **Point the front end at it** (two places):
   - `src/main.js` — set `WEBHOOK_URL` to the production URL
   - Framer — set the "Webhook URL" property on the BrandCheckHero component

## Testing

While the workflow is open in the editor, "Listen for test event" uses
`https://geeiq.app.n8n.cloud/webhook-test/brand-check` instead. Note the rate
limiter and repeat flag only persist between production executions, so test
runs never trip them.

Valid submission (expect 200 OK, a HubSpot contact, and a Slack alert):

```bash
curl -X POST https://geeiq.app.n8n.cloud/webhook/brand-check \
  -H 'Content-Type: application/json' \
  -d '{"brand":"Test brand","firstName":"Test","lastName":"Person","jobTitle":"Brand manager","email":"test@acme-example.co","submittedAt":"2026-07-07T12:00:00Z","pageUrl":"https://check.geeiq.com","elapsedMs":20000,"hp":""}'
```

Honeypot (expect 200 OK but nothing in HubSpot or Slack):

```bash
curl -X POST https://geeiq.app.n8n.cloud/webhook/brand-check \
  -H 'Content-Type: application/json' \
  -d '{"brand":"Bot brand","firstName":"B","lastName":"O","jobTitle":"T","email":"bot@bot-example.co","elapsedMs":900,"hp":"http://spam.example"}'
```

Free email domain (expect 200 OK, silently discarded):

```bash
curl -X POST https://geeiq.app.n8n.cloud/webhook/brand-check \
  -H 'Content-Type: application/json' \
  -d '{"brand":"Test","firstName":"A","lastName":"B","jobTitle":"C","email":"a@gmail.com","elapsedMs":20000,"hp":""}'
```

Check the workflow's execution list to see the `_blockReason` on discarded runs.

## Tuning

All knobs live at the top of the "Validate submission" code node:

- `ENFORCE` — set to `false` to tag without blocking while you trial it
  (everything passes through, `_blockReason` still recorded per execution).
- `MIN_ELAPSED_MS` (8000) — the discovery animation alone takes ~4.2s, and a
  human also types a brand and four fields, so under 8s is a bot.
- `MAX_PER_HOUR` (30) — global cap; excess submissions are silently dropped.
- `ALLOWED_ORIGINS` — remove the localhost entries once live.
- `BLOCKED_EMAIL_DOMAINS` — same list as the Framer Demo Form workflow.

Also tighten CORS once the page's final home is known: on the Webhook node,
change "Allowed Origins (CORS)" from `*` to the page's origin(s), e.g.
`https://check.geeiq.com,https://www.geeiq.com`.

## Later, if wanted

- **Brand name into HubSpot**: the brand only appears in the Slack alert. To
  store it on the contact, create a custom contact property (e.g.
  `brand_checked`) in HubSpot first, then add it to the upsert body. Adding an
  undefined property makes the whole upsert fail, which is why it is not in
  there now.
- **Form analytics**: the demo form also logs to the HubSpot Forms API. To
  mirror that, create a "Brand check" form in HubSpot and copy the demo
  workflow's "Log Form Submission" node with the new form GUID.
- **Owner routing / SLA nudges**: the MQL workflows already do claim buttons
  and follow-up threads; the Slack alert here is deliberately simpler and can
  grow into that pattern.
