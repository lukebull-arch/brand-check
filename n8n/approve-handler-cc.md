# Approve handler: copy in the SDR (22 Oct 2026)

APPLIED LIVE 22 Oct 2026: all three edits below are in the active version
(`1e52b407-4ab2-4eac-9e7d-d3ed030d1e01`). Kept as the record of what changed.

CI now picks the SDR for the brand's sector (`automation/sdr_route.py`), adds an
introduction paragraph to the email draft, and puts their address in the Slack
button value as `cc`. The live n8n workflow "Brand check — approve handler"
(`JgmHo1XnjmhZEZeO`) needs three edits to send that CC.

Apply these BEFORE pushing the CI change. If CI goes first, emails say "I've
copied in my colleague Rachel" while nobody is copied in. Applying n8n first
is safe: drafts without `cc` send exactly as today.

## 1. Parse action (Code node)

In the returned object, add one line after `fileId`:

```js
  fileId: meta.fileId || '',
  // SDR copied in on the delivery email, chosen by sector in CI (automation/sdr_route.py)
  cc: meta.cc || '',
```

## 2. Send report email (Gmail node)

Options > Add option > CC, expression:

```
{{ $('Parse action').first().json.cc }}
```

An empty value sends with no CC (the Gmail node only sets CC when the option
is non-empty), so drafts posted before this change still send cleanly.

## 3. Confirm sent in Slack (HTTP Request node, optional)

So the channel shows who was copied in. Replace the JSON body with:

```
{{ JSON.stringify({replace_original: true, text: ':white_check_mark: ' + $('Parse action').first().json.brand + ' report approved by ' + $('Parse action').first().json.approver + ' and sent to ' + $('Parse action').first().json.email + ($('Parse action').first().json.cc ? ', CC ' + $('Parse action').first().json.cc : '')}) }}
```

Save, then publish (the workflow is live, so the saved draft does nothing
until it is published).

The decline email is unchanged: it never copies anyone in.
