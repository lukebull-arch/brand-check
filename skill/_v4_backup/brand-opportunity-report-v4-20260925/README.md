# Brand opportunity report skill

A Claude skill for the sales team. Give Claude a brand name and it pulls the
brand's Roblox marketplace and experience data plus YouTube gaming content,
then builds a one-page GEEIQ-styled opportunity report you can print to PDF
and use in account-based marketing.

## Install

1. Copy the `brand-opportunity-report` folder into your skills directory:

   - Claude Code (CLI or desktop app): `~/.claude/skills/`
   - So you end up with `~/.claude/skills/brand-opportunity-report/SKILL.md`

2. Set the YouTube API key so the YouTube data is included (ask Luke for the
   key). Add to your `~/.zshrc`:

   ```bash
   export YOUTUBE_API_KEY="paste-key-here"
   ```

   Without it the report still works, Roblox only.

3. Requires Python 3 (preinstalled on every Mac). No packages to install.

## Use

Start a Claude session anywhere and ask, for example:

- "Build a brand opportunity report for Casio"
- "What does Nike look like on Roblox?"
- "Run a brand check on LVMH for tomorrow's pitch"

Claude collects the data (takes a few minutes, the script is deliberately
polite to the platform APIs), filters out unrelated search results, and
writes `GEEIQ_Opportunity_[Brand]_[YYYY-MM].html`. Open it in a browser and
print to PDF for sharing.

## What to trust

Every number in the report traces to a row in the collected CSVs (saved in
`out/<brand>/` next to the report, so you can check). The collector now pulls
the marketplace until Roblox stops returning results, so a big brand takes a
few minutes and the counts are real. Where a platform limit is reached the run
prints a warning and the report has to say "at least N". Creator-made content
is fan-made and unofficial; the report never implies the brand endorsed it.

## Questions

luke.bull@geeiq.com

## v4 (13 August 2026)

Replace your installed copy again. This one fixes an undercount, not a
wording problem:

- The collector paginates the marketplace to exhaustion by default. It used
  to stop after 5 pages with more results waiting and say nothing, which
  reported 54 fan-made Chelsea items when there were 1,047. Thanks Sam for
  catching it.
- `--pages` is now an opt-in sample and prints a truncation warning whenever
  it stops early. So does the Roblox 1,000-row-per-query ceiling, which turns
  a count into "at least N".
- Bracketed names and org suffixes are searched both ways: "Chelsea (FC)"
  also pulls and matches plain "Chelsea", which is how fans actually name
  their items.
- Experience and YouTube searches run the same variants, dedupe across them,
  and label YouTube as a top sample rather than a census.
- Runs take longer now. That is the fix working.

## v3 (11 August 2026)

Significant update, replace your installed copy entirely:

- New report layout, the approved GEEIQ template (bundled as
  report-template.html) with brand-correct typography.
- Official-presence classification hardened: imitator accounts
  ("Gregg's™") no longer count, partner-run activations declared in
  experience descriptions do.
- New mandatory step: verify against the GEEIQ platform before claiming
  anything about official presence. You need your app.geeiq.com login.
- YouTube figures are now deduplicated and dropped entirely when the view
  volume is mostly non-gaming content (physical-product brands, take note).
- Presence claims are always scoped: "on Roblox", never "anywhere".
