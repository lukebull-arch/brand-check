---
name: brand-opportunity-report
description: Generate a GEEIQ brand opportunity report for account-based marketing. Pulls a brand's Roblox marketplace and experience data plus YouTube gaming content with the bundled collector, classifies it, and builds a client-ready report in the approved GEEIQ layout showing the brand's footprint and the opportunity in gaming and virtual worlds. Use whenever someone asks for an opportunity report, ABM report, brand check, brand visibility check, or prospect report for a brand, or asks what a brand looks like on Roblox or YouTube. Trigger even for casual phrasings like "what does Nike look like on Roblox", "run a brand check on Casio", or "build me a report for the LVMH pitch".
---

# Brand opportunity report

Turn a brand name into a one-page opportunity report for a sales
conversation. Four steps, always in this order: collect, classify, verify
against the GEEIQ platform, then build. The reader is a marketer at the
target brand, so every number must survive them checking it, and every
claim must survive them knowing their own deals better than you do.

## Step 1: Collect

```bash
python3 scripts/grab.py --brand "BRAND NAME"
```

Outputs land in `out/<brand>/` (override with `--out DIR`; `--pages N`
raises the Roblox page count, default 5):

| File | Contents |
|---|---|
| `roblox_catalog_items.csv` | Marketplace items: Name, ID, URL, Creator, Creator Type, Price (Robux), Favorites, Item Type, Created, Brand Match |
| `roblox_games.csv` | Experiences: Name, ID, Universe ID, URL, Like %, Active Players, Creator, Up/Down Votes, Sponsored, Visits (lifetime), Favorites, Creator Type, Verified Creator, Description, Brand Match |
| `youtube_<platform>.csv` | One per platform (roblox, fortnite, minecraft): Title, URL, Video ID, Creator, Creator URL, Views (numeric), Posted, Platform |

Environment: `YOUTUBE_API_KEY` for the YouTube CSVs (ask Luke); without it
they are skipped with a note. Roblox needs no auth. One brand at a time,
the script paces itself deliberately.

## Step 2: Classify before you count

The `Brand Match` column makes the first cut mechanical:

- **Rows with an empty `Brand Match` are noise. They never enter any
  figure.** Roblox search pads weak queries with popular unrelated games;
  a Greggs pull once returned 109 experiences, none of them Greggs.
- **Eyeball the matched names before quoting anything.** Substring matching
  has burned us twice: "Narutomaki Tower" (a fish-cake game, 97m visits)
  matched Naruto, and "Target" matches every shooting game on the
  platform. If a matched name is a longer word containing the brand, or
  the brand word is generic, throw the row out and say so.

Then classify every matched row:

- **Official** requires one of, in order of strength:
  1. Creator name equals the brand exactly (case and spacing may differ,
     punctuation may NOT: "Gregg's™", "Greggs®" and "KTM Oficial" are
     imitators, not the brand; an invisible trailing character has been
     used to fake this).
  2. A punctuation variant of the name PLUS Roblox's verified badge, the
     one signal an imitator cannot self-award.
  3. The experience DESCRIPTION declares a brand partnership in narrow
     terms ("official <brand>", "<brand>-sponsored", "sponsored by
     <brand>", "in partnership with <brand>", "officially licensed"),
     because partners run brand activations under their own accounts
     (Formula E's official experience is run by "Formula E - Electric
     Lap"). Any disclaimer in the description ("unofficial", "fan
     group/made", "not affiliated") voids the claim outright.
- **Creator-made**: brand named, creator is someone else. Fan-made,
  unofficial. A creator named after the brand plus extra words ("KTM
  RACING TEAM GROUP", "{UK} Greggs") is a fan group, never official.
- **Lookalike**: product-line names without the brand word. Flag in chat,
  never count.

## Step 3: Verify against the GEEIQ platform (do not skip)

You have platform access; use it. Search the brand on
`https://app.geeiq.com/search?q=<brand>` and open the brand page's
**Partnerships** and **Experiences** tabs before writing a word.

- The platform tracks partnerships the public data cannot see. A KTM
  report nearly went out saying "no official presence" while the platform
  tracked KTM's live Driving Empire integration. The recipient signed
  those deals; the report must know about them.
- Open "View table" on partnerships for the dates: a past two-week event
  and a live integration look identical on the overview card.
- If the platform and your collected data disagree, the platform wins for
  partnerships and the collected data wins for marketplace counts.

**The scope rule, absolute:** presence claims name what was searched.
Write "no official presence on Roblox's marketplace", never "no official
presence anywhere". Brands live in licensed console games and partner
integrations this data cannot see, and the reader usually knows it.

## Step 4: YouTube, handle with suspicion

Two mandatory checks before any YouTube figure is used:

1. **Dedupe by Video ID across the three platform CSVs.** The same video
   surfaces in several searches; per-platform sums double-count it.
2. **Gaming-content share.** Compute the share of deduped view volume
   whose titles carry a gaming term (roblox, fortnite, minecraft, gaming,
   gameplay, game, obby, tycoon, simulator, ugc, mod, server, speedrun).
   **Below 30%, drop YouTube from the report entirely** and say why in
   chat. Physical-product brands fail this constantly: a KTM pull was 98m
   views of real motorbike Shorts, a Casio pull 94% watch reviews. A big
   number that is mostly not gaming is not a gaming number.

When the figure survives, word it as "views on videos naming <brand>
surfaced by gaming searches", never "views on gaming videos".

## Step 5: Build the report

Use the bundled **`report-template.html`** — it is the approved GEEIQ
layout (praised by the sales team for its restraint) with brand-correct
typography. Fill the placeholders, delete the sections the data does not
earn, save as HTML, then print to PDF:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --no-pdf-header-footer --print-to-pdf="GEEIQ_Opportunity_BRAND_YYYY-MM.pdf" \
  "file://$PWD/report.html"
```

Structure the template enforces: kicker + title + one-sentence headline ·
ONE hero figure in coral (the single strongest number) · up to three stat
cards · an "Official activity" panel ONLY when official presence exists
(with dates, from the platform) · "What this means", 90 words maximum ·
a highlights panel of named items or experiences · the "What we searched"
method strip, which must state exactly what was scanned, what matched,
and whether YouTube was excluded · standing page 2, do not edit its
figures.

Keep it sparse. The design's power is what it leaves out: if a section is
not earned by the data, delete it rather than pad it.

## Data integrity rules, non-negotiable

- Every figure traces to a CSV row, a platform screen, or arithmetic on
  them. No estimates, no rounding up past the data.
- "We found N in the top results", never "there are N". Date the snapshot.
- Creator-made content is "fan-made" or "creator-made", never implied as
  brand-affiliated or endorsed.
- Both stories are real and the data picks: official presence plus a fan
  tail is a commitment story; zero official with creator demand is a
  whitespace story; partnerships plus an uncaptured fan tail (the KTM
  case) is the strongest of all: proof of intent and proof of demand.

## Writing rules (hard rules, every sentence)

- UK English. No em dashes: full stops, commas or colons. No exclamation
  marks. Sentence case.
- Never use: ecosystem, intelligence platform, seamless, leverage, unlock,
  branded activations, benchmark performance, drive ROI, metaverse.
- No "not X, it's Y" or "not X, but Y" constructions.
- Say "gaming and virtual worlds". Numbers carry the argument.

## Deliver

In chat after the report: a three-bullet summary including every row
excluded as lookalike or noise, the YouTube gaming-share and whether the
figure was dropped, and anything the platform showed that the public data
missed. If the brand appears under several spellings, ask which is
canonical before building.
