# Brand opportunity report skill, v7

A Claude skill for the sales team. Give Claude a brand name and it runs the
same pipeline as the automated GEEIQ brand checker: pulls the brand's Roblox
marketplace and experience data plus YouTube gaming content, classifies it,
fetches the logo, writes the copy and renders the approved two-page GEEIQ
report as a PDF. Claude then does the checks the code cannot, and edits the
copy before anything goes out.

## Install

1. Replace any earlier copy. Delete `~/.claude/skills/brand-opportunity-report`
   if it exists, then copy this folder there, so you end up with
   `~/.claude/skills/brand-opportunity-report/SKILL.md`.
2. Google Chrome installed (the renderer prints through it). Python 3 is on
   every Mac already.
3. Optional, recommended: `pip3 install pillow segno` for the QR code and
   cleaner logo handling. Without them the report still renders, minus the QR.
4. YouTube: add `export YOUTUBE_API_KEY="..."` to `~/.zshrc` (ask Luke).
   Without it the report is Roblox only and says so.
5. Nothing else. The first run creates a small `.venv` inside `scripts/` for
   the fallback renderer; let it.

## Use

In a Claude Code session anywhere:

- "Run a brand check on Casio"
- "What does Nike look like on Roblox?"
- "Build me a brand opportunity report for the LVMH pitch"

Claude runs `scripts/run.py`, which takes twenty to sixty minutes for a real
brand because it collects to exhaustion and backs off when Roblox rate-limits
it. It then reads `analyst_summary.txt`, checks the GEEIQ platform and the web
for anything the public data cannot see, rewrites the copy to house style and
hands you `GEEIQ_Brand_check_<Brand>_<YYYY-MM>.pdf` with the CSVs beside it.

## What to trust

Every number traces to a row in `out/<brand>/data/`, a platform screen, or
`peers.json`. Where Roblox's search limit was hit the figure is written as
"at least N" and the method strip says why. Creator-made content is
player-made and never implied to be endorsed. Presence claims are always
scoped to the platform searched.

## Questions

luke.bull@geeiq.com

## v7 (2 November 2026)

- Collector: the output folder is created before the CSV is written (a two-hour crawl once died on a missing directory).
- Renderer: one-page mode (`BRAND_CHECK_ONE_PAGE=1`) caps creators at three and tags the page `page one`; the hero label strips emoji and live-ops tags from experience names.
- `verify_print.py` is bundled: run it on every PDF before sending (fonts embedded, QR decodes, no overflow).
- New section in SKILL.md: sending a brand check by hand, with the SDR CC rule (Rachel or Cody by sector, HubSpot BCC) that the automation applies since 22 October 2026.

## v6 (30 September 2026)

The pipeline now runs the GEEIQ platform check itself (`scripts/platform_check.py`,
needs `GEEIQ_API_TOKEN`), places Roblox-verified issuers as "official via partner"
when the platform or the licensee list vouches for them, and refuses to write any
absence claim while a verified issuer or a partnership record exists. The favicon
fallback no longer guesses a domain or trusts a site builder's default mark. Mr Bean
(Cartoon Network Games, eight licensed items) was the case that forced it.

## v5 (25 September 2026)

Replace your installed copy entirely. The old bundled collector was a fork
from August and it was 559 lines behind the live one. v5 ships the live
pipeline itself, so every fix below is in the code you run, not in prose you
have to remember:

- Sort-order sweep: Roblox's 1,000-row cap is per query and per sort order,
  and each sort exposes a different slice, so the collector now sweeps all
  four. On Aston Villa that found 17% more matching items.
- Whole-word matching. "Aldi" no longer matches "Maldivian Hotel" (17.5m
  visits) and "Target" no longer matches every shooting game.
- Keyword-soup spam is excluded from favourite figures and flagged; if spam
  holds most of a brand's favourites the summary tells you to quote none.
- Long club names: "Brighton Home Kit 22-23" now counts for Brighton & Hove
  Albion, which had been undercounted 8.5 times.
- Impersonator accounts ("Gregg's(tm)", "Greggs RBLX") never count as
  official. Punctuation is significant; only Roblox's verified badge can
  rescue a variant.
- "Officially licensed" in a description must name the brand. A dungeon game
  licensed by a studio no longer becomes a confectioner's own experience.
- Context screens for ordinary-word brands (Kinder, Domino's, Snickers):
  a listing counts only when it also names the product.
- YouTube: deduplicated by video id across platform searches, dropped
  entirely when under 30% of the named view volume is gaming content.
- Logos: people, wrong-market marks, retired marks and sponsor lockups are
  guarded against, and the summary tells you which entity the logo came from
  so you check it.
- Print-safe names: emoji and non-Latin scripts stripped from the page, tm
  and (r) kept so imitators are not displayed as the brand.
- The approved layout with the embedded fonts, the QR code to the walkthrough
  page, and the standing page 2.
- New `scripts/grab_hidden.py` for marks Roblox search returns nothing for
  (Nike, Aston Martin, Rolls Royce, BMW): slang, model codes, creator stores
  and fan groups, every count a floor.
- New `scripts/peers.py` to verify peer and category figures from the games
  API before they go on a page.
- SKILL.md rewritten around the three failures that mattered most: reports
  that told a brand it was absent from a platform it had launched on. The
  platform check and the web check are mandatory, limited drops are called
  out, and the framing rule (missed opportunity, never infringement) is
  binding.

## v4 (13 August 2026)

- Collector paginated the marketplace to exhaustion instead of stopping at
  five pages (54 Chelsea items became 1,047). `--pages` became an opt-in sample
  with a warning. Bracketed names and org suffixes searched both ways.

## v3 (11 August 2026)

- Approved GEEIQ layout, hardened official-presence classification, mandatory
  platform check, YouTube dedupe and contamination drop, scoped claims.
