---
name: brand-opportunity-report
description: Generate a GEEIQ brand opportunity report for account-based marketing. Pulls a brand's Roblox marketplace and experience data plus YouTube gaming content with the bundled collector, classifies it, and builds a client-ready HTML report showing the brand's footprint and the opportunity in gaming and virtual worlds. Use whenever someone asks for an opportunity report, ABM report, brand check, brand visibility check, or prospect report for a brand, or asks what a brand looks like on Roblox or YouTube. Trigger even for casual phrasings like "what does Nike look like on Roblox", "run a brand check on Casio", or "build me a report for the LVMH pitch".
---

# Brand opportunity report

Turn a brand name into a one-page opportunity report for a sales
conversation. Three steps, always in this order: collect the data with the
bundled script, classify every row, then build the report. The reader is a
marketer at the target brand, so every number must survive them checking it.

## Step 1: Collect

```bash
python3 scripts/grab.py --brand "BRAND NAME"
```

Outputs land in `out/<brand>/` in the current directory (override with
`--out DIR`; `--pages N` raises the Roblox page count, default 5):

| File | Contents |
|---|---|
| `roblox_catalog_items.csv` | Marketplace items: Name, ID, URL, Creator, Creator Type, Price (Robux), Favorites, Item Type, Created, Brand Match |
| `roblox_games.csv` | Experiences: Name, ID, Universe ID, URL, Like %, Active Players, Creator, Up/Down Votes, Sponsored, Visits (lifetime), Favorites, Creator Type, Verified Creator, Brand Match |
| `youtube_<platform>.csv` | One per platform (roblox, fortnite, minecraft): Title, URL, Video ID, Creator, Creator URL, Views (numeric), Posted, Platform |

Environment:

- `YOUTUBE_API_KEY` — needed for the YouTube CSVs. Without it they are
  skipped with a note; say so in the report footnote and in chat rather
  than silently omitting YouTube.
- Roblox currently needs no auth. If both Roblox CSVs come back empty, the
  script prints cookie instructions; relay them to the user.

The script paces itself deliberately (one request per ~1.2s). Run one brand
at a time. If asked for several brands, warn that each takes a few minutes
and run them sequentially.

## Step 2: Classify before you count

Roblox search pads weak queries with popular and semantically similar
content. For a brand with little real presence, every returned experience
can be filler: blockbuster games with billions of visits that have nothing
to do with the brand. The `Brand Match` column makes the first cut
mechanical:

- **Rows with an empty `Brand Match` are noise. They never enter any
  figure, under any framing.** No brand term in the name or creator means
  it is not the brand's content, however large its numbers.
- If zero experience rows have a brand match, the finding is "no matching
  Roblox experiences found". Report that plainly and never use the CSV's
  visit or player totals. The collector prints a warning when this happens;
  echo it in chat.

Then put every brand-matched row in exactly one bucket before computing
anything:

- **Official**: `Creator` equals the brand name, case-insensitive. Brands
  with a real presence run verified creator accounts under their own name
  (adidas does; most brands do not).
- **Creator-made**: brand name appears in the item or experience `Name` but
  the creator is someone else. Fan-made, unofficial content.
- **Lookalike**: carries the brand's product-line names without the brand
  word ("Samba Sneakers", "NK Dunk Low"). Usually knockoffs dodging the
  trademark. Flag them in chat as a finding; never count them in headline
  figures.
- **Noise**: no brand term in name or creator (`Brand Match` empty).
  Exclude from all figures and say in chat how many rows you dropped.

A creator named after the brand plus extra words ("Greggs RBLX", "{UK}
Greggs") is a fan group, never official. Official means the creator name
equals the brand name exactly, and the Verified Creator column supports it.

## Step 3: Pick the figures

Compute only what the data supports. Candidates, in priority order:

- Combined lifetime visits across matching experiences (usually the
  strongest number on the page)
- Official item count, and the official/creator-made split
- The most visited matching experience, named, with its visit count
- Count of distinct creators making content around the brand
- Most favourited item, named
- YouTube video count per platform, and combined views

Pick the four to six strongest. A small number that is real beats a large
number that needs a caveat.

The data picks one of two stories, and the headline follows it:

- **Commitment story**: a meaningful official catalogue means the brand has
  already invested. The opportunity framing is scale and measurement: they
  are in, the question is whether it is working and what peers do better.
- **Whitespace story**: zero official rows with creator-made content and
  visits means players built the brand's presence for them. The opportunity
  framing is unmet demand: the audience is already there, unsupervised.
- If the data shows almost nothing at all, that is still a finding: say what
  the whitespace means and lean on the market context band.

Data integrity rules, non-negotiable:

- Never invent, extrapolate or estimate a number. Every figure traces to a
  CSV row or arithmetic on CSV rows.
- Only rows with a non-empty `Brand Match` may enter a figure. Zero matched
  experiences means the story is whitespace, whatever else the CSV
  contains.
- Roblox results are the top ~100 by relevance, not a census. Write "we
  found N" or "the top results include N", never "there are N".
- Date the snapshot. Visits are lifetime; player counts are that moment.
- Creator-made content is player-made and unofficial. Never imply the brand
  made it, endorsed it, or is affiliated with it. "Creator-made",
  "fan-made" and "unofficial" are the right words.
- Round for readability (2.4m, 118k) but never round up past the data.

## Step 4: Build the report

Produce one self-contained HTML file, `GEEIQ_Opportunity_[Brand]_[YYYY-MM].html`,
styled to print as a single A4 portrait page (use `@page` and
`@media print` rules; the rep prints to PDF from the browser). No external
scripts; a Google Fonts import for the two typefaces is fine, with system
fallbacks.

Structure, top to bottom:

1. **Header**: GEEIQ wordmark as text, title "Brand opportunity: [Brand]",
   snapshot date ("Snapshot: [month year]").
2. **Headline finding**: one sentence, specific to this brand, led by the
   strongest number.
3. **Stat grid**: the four to six figures from step 3, each with a one-line
   label.
4. **Analyst reading**: two or three sentences on what the numbers say about
   where this brand already lives in gaming and virtual worlds.
5. **The opportunity**: two or three sentences drawing the sales conclusion
   the data supports. Whitespace story: the audience got there first and
   nobody official is meeting them. Commitment story: presence exists, the
   next questions are performance and what category peers are doing.
   Ground every claim in the figures above; no promises about outcomes.
6. **Market context band** (standing content, dark background, use these
   figures verbatim, never edit them):
   - "$188.8bn" / "spent on gaming globally, more than music and film combined"
   - "500m" / "monthly players on Roblox alone"
   - "1,011" / "brand activations we tracked in virtual worlds last year"
   - "8 years" / "tracking this market, since 2018"
7. **Footer**: "Built by GEEIQ. Data: GEEIQ platform and public sources,
   [month year]." Add a note if YouTube was skipped.

Design system:

- Headings: Plus Jakarta Sans 600. Body: Figtree 400. Sentence case
  everywhere, no all caps.
- Purple #7C68FB is the default accent. Dark amethyst #2E204D for headings
  and the market context band background (white numbers, #C9C0E6 labels).
  Warm off-white #FAF7F2 page background. White cards.
- Coral #FC4F3F on exactly one number on the page: the single takeaway
  figure. Nowhere else.
- Clean grid, generous margins. Restrained and confident.

## Writing rules (hard rules, every sentence)

- UK English. No em dashes anywhere: use full stops, commas or colons. No
  exclamation marks.
- Never use: ecosystem, intelligence platform, seamless, leverage, unlock,
  branded activations, benchmark performance, drive ROI.
- No "not X, it's Y", "not X, but Y", or "X aren't just A, they're B"
  constructions in any form.
- Say "gaming and virtual worlds". Plain language over jargon.
- Numbers carry the argument. Adjectives do not.

## Deliver

In chat, after the report file:

1. A three-bullet summary of the findings, including rows excluded as
   lookalikes or noise and anything odd in the data.
2. If the brand appears under several spellings in the CSVs, ask which is
   canonical before building. Otherwise do not ask questions, just build.
