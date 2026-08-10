# Add the GEEIQ signature to brand check emails

Two edits in n8n, both in **"Brand check — approve handler"**.

## 1. Replace the "Parse action" node's code with this

The only change from the current code is the HTML block at the end (and
`bodyHtml` in the return). Your LinkedIn URL is already in place.

```javascript
// Slack interactivity sends a form-encoded `payload` field of JSON.
const body = $input.first().json.body || {};
const payload = JSON.parse(body.payload);
const action = (payload.actions && payload.actions[0]) || {};
const meta = JSON.parse(action.value || '{}');

// Recover the email draft from the original message blocks
let draft = '';
for (const b of (payload.message && payload.message.blocks) || []) {
  const t = (b.text && b.text.text) || '';
  if (t.includes('Email that will be sent')) {
    const m = t.match(/```([\s\S]*?)```/);
    if (m) draft = m[1].trim();
  }
}
const ANALYST_NAME = 'Luke';
draft = draft
  .replace(/\[first name\]/g, meta.firstName || 'there')
  .replace(/\[analyst name\]/g, ANALYST_NAME);

let subject = 'Your GEEIQ brand check: ' + (meta.brand || '');
const sm = draft.match(/^Subject:\s*(.+)\s*\n+/);
let bodyText = draft;
if (sm) { subject = sm[1].trim(); bodyText = draft.slice(sm[0].length).trim(); }

// HTML version with the GEEIQ signature appended. The plain-text draft in
// Slack stays the source of truth; this only formats it for sending.
const LINKEDIN_URL = 'https://www.linkedin.com/in/luke-bull-843359a7/';
const SIGNATURE_HTML = [
  '<table cellpadding="0" cellspacing="0" border="0" style="margin-top:24px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.5;color:#2E204D;">',
  '<tr><td style="padding-bottom:10px;"><img src="https://framerusercontent.com/images/b1UWCewbWf7HLdUHUslJ4KG54sU.png" width="96" alt="GEEIQ" style="display:block;border:0;"></td></tr>',
  '<tr><td style="padding-bottom:4px;"><strong>Luke Bull</strong> &nbsp;Content Lead&nbsp; <a href="' + LINKEDIN_URL + '" style="color:#7C68FB;text-decoration:none;">LinkedIn</a></td></tr>',
  '<tr><td style="color:#584D71;">E: <a href="mailto:luke.bull@geeiq.com" style="color:#584D71;text-decoration:none;">luke.bull@geeiq.com</a> &nbsp;W: <a href="https://geeiq.com" style="color:#7C68FB;text-decoration:none;">geeiq.com</a></td></tr>',
  '</table>',
].join('');
const esc = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const bodyHtml = esc(bodyText)
  .split(/\n{2,}/)
  .map((p) => '<p style="margin:0 0 14px 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#101010;">' + p.replace(/\n/g, '<br>') + '</p>')
  .join('') + SIGNATURE_HTML;

return [{ json: {
  actionId: action.action_id || '',
  brand: meta.brand || '',
  email: meta.email || '',
  firstName: meta.firstName || 'there',
  fileId: meta.fileId || '',
  approver: (payload.user && (payload.user.name || payload.user.username)) || 'someone',
  responseUrl: payload.response_url || '',
  subject: subject,
  bodyText: bodyText,
  bodyHtml: bodyHtml,
}}];
```

## 2. Update the "Send report email" (Gmail) node

- **Email Type**: change `Text` to `HTML`
- **Message**: change to
  `{{ $('Parse action').first().json.bodyHtml }}`
- Leave the attachment settings untouched.

The decline email stays deliberately plain text — no change there.

## Notes

- The logo is the wordmark from your own report PDFs, hosted at
  framerusercontent.com (same CDN as the website), white background,
  displayed at 96px wide.
- The Slack draft preview stays plain text; the signature is added only at
  send time, so approvers see clean copy in Slack.
- To verify: once saved, approve the next test draft and the email arrives
  with the new copy format AND the signature.
