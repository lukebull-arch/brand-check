---
name: brand-data-pull
description: Pull a brand's presence data from Roblox and YouTube into CSVs and summarise what it shows, using GEEIQ's collector script. Use this whenever someone asks about a brand's presence, footprint, items, experiences or activity on Roblox, wants brand gaming content counted on YouTube, asks for "brand check" data or CSVs for a brand, or mentions running the GEEIQ scraper or collector. Trigger even for casual phrasings like "what does Nike look like on Roblox" or "can you grab the data for Casio", and even when the user does not mention CSVs or the collector by name.
---

# Brand data pull

Collect a brand's Roblox and YouTube presence with the bundled collector,
then read the results properly. The script does the fetching; your job is
the collection command plus an honest summary.

## Collect

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
- `YOUTUBE_API_KEY` — needed for the YouTube CSVs; without it they are
  skipped with a note. Say so in your summary rather than silently omitting
  YouTube.
- Roblox currently needs no auth. If both Roblox CSVs come back empty, the
  script prints cookie instructions; relay them to the user.

The script paces itself deliberately (one request per ~1.2s). Run one brand
at a time and do not loop it over brand lists without the user
understanding it will take a while.

## Classify before you count

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
  echo it in your summary.

Then put every brand-matched row in one bucket before computing anything:

- **Official**: `Creator` equals the brand name, case-insensitive. Brands
  run verified creator accounts under their own name (adidas does; most
  brands do not).
- **Creator-made**: brand name appears in the item/experience `Name` but
  the creator is someone else. This is fan-made, unofficial content.
- **Lookalike**: carries the brand's product-line names without the brand
  word ("Samba Sneakers", "NK Dunk Low"). Usually knockoffs dodging the
  trademark. Flag them separately; never count them in headline figures.
- **Noise**: no brand term in name or creator (`Brand Match` empty).
  Exclude from all figures, and say how many rows you excluded.

## Summarise honestly

Strongest figures, in rough priority: combined lifetime visits across
matching experiences, official item count and the official/creator-made
split, the most visited experience (named), distinct creators, most
favourited item, YouTube video count and combined views.

Rules that keep the summary defensible:

- Every number must trace to CSV rows. No estimates, no extrapolation.
- Only rows with a non-empty `Brand Match` may enter a figure. Zero
  matched experiences means "no matching experiences found", whatever
  else the CSV contains.
- The Roblox results are the top ~100 by relevance, not a census. Say
  "we found N" or "the top results include N", never "there are N".
- Date the snapshot (visits are lifetime, player counts are that moment).
- Creator-made content is player-made and unofficial. Never imply the
  brand made it, endorsed it, or is affiliated with it.
- Two stories are possible and the data picks: a big official catalogue is
  a commitment story; zero official rows with creator-made content and
  visits is a "players got there first" story.

## Example

**User**: what does KFC look like on roblox?

**Do**: run `python3 scripts/grab.py --brand "KFC"`, classify, then report
along these lines: "No official KFC presence. Players built it instead:
150 creator-made KFC items from 86 creators, and the top KFC experiences
have 69m lifetime visits between them, led by Escape KFC Obby at 44m.
Excluded 60 unrelated search rows. YouTube skipped, no API key set."
