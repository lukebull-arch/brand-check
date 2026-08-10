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
`out/<brand>/` next to the report, so you can check). Roblox results are the
top ~100 by relevance, not a full census, which is why the report says "we
found N" rather than "there are N". Creator-made content is fan-made and
unofficial; the report never implies the brand endorsed it.

## Questions

luke.bull@geeiq.com
