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

**Let it run to the end and never pass `--pages`.** The collector now
paginates the marketplace until Roblox stops returning a cursor, which on a
big brand means several minutes and dozens of pages. `--pages N` exists only
as a deliberate sample and it will print a truncation warning; a report built
on a truncated pull is wrong, not approximate. A Chelsea FC check went out
with 54 fan-made items when the catalogue held 1,047: the collector had
stopped at page 5 with a live cursor and said nothing.

**Brand name: type it the way fans type it.** Give the plain trading name
("Chelsea", "KTM", "Greggs"). The script also strips brackets and org
suffixes itself, so "Chelsea (FC)" is queried as both "Chelsea (FC)" and
"Chelsea", but a name nobody uses in an item title finds nothing.

Outputs land in `out/<brand>/` (override with `--out DIR`):

| File | Contents |
|---|---|
| `roblox_catalog_items.csv` | Marketplace items: Name, ID, URL, Creator, Creator Type, Price (Robux), Favorites, Item Type, Created, Brand Match |
| `roblox_games.csv` | Experiences: Name, ID, Universe ID, URL, Like %, Active Players, Creator, Up/Down Votes, Sponsored, Visits (lifetime), Favorites, Creator Type, Verified Creator, Description, Brand Match |
| `youtube_<platform>.csv` | One per platform (roblox, fortnite, minecraft): Title, URL, Video ID, Creator, Creator URL, Views (numeric), Posted, Platform |

Environment: `YOUTUBE_API_KEY` for the YouTube CSVs (ask Luke); without it
they are skipped with a note. Roblox needs no auth. One brand at a time,
the script paces itself deliberately.

### What the collector cannot see, and what you must write instead

Read the run's final line and every WARNING or NOTE above it. Three ceilings
exist and each one changes the wording of the report:

| Ceiling | What the run prints | How you must word it |
|---|---|---|
| Roblox caps a single catalogue query at about 1,000 rows | `NOTE: "X" returned N rows, which is Roblox's ~1,000-row ceiling` | "at least N items", plus a method-strip line saying the platform's search limit was reached |
| `--pages` or the 40-page safety ceiling stopped a live cursor | `WARNING: stopped at ... more results still available` | Do not publish. Rerun without the limit |
| YouTube search is relevance-ranked, never exhaustive | `youtube <platform>: N rows (top sample, not a census)` | "at least N views across the top results", never a total |

If the summary line says `items=N (AT LEAST ...)`, the phrase "at least"
belongs in the report itself, in the hero figure's caption and the method
strip. A floor honestly labelled is a stronger sales number than a total that
the recipient can disprove by scrolling their own catalogue.

## Step 2: Classify before you count

The `Brand Match` column makes the first cut mechanical:

- **Rows with an empty `Brand Match` are noise. They never enter any
  figure.** Roblox search pads weak queries with popular unrelated games;
  a Greggs pull once returned 109 experiences, none of them Greggs.
- **A tiny matched count on a famous brand is a bug until proven otherwise.**
  Before quoting a low number, check the run log: did a query stop early, and
  is the brand's own name in `Brand Match` at all? Fifty-four items for a
  Premier League club was the tell that pagination had truncated, and it read
  as a finished report. Sanity-check the scale against what the brand's fans
  plainly produce.
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

If the run prints `NOTE: N of M matches name only "X"`, those rows matched on
the short trading name alone. Keep them, because that is how fans title their
work, but read a sample first: "Chelsea" is also a person and a London
borough. If a meaningful share is clearly something else, say so in chat and
in the method strip rather than quietly inflating the count.

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

## Step 3b: Search the web before you claim absence (do not skip)

Run a real web search. Partnerships are announced, and the announcement
almost always sits on the partner studio's site rather than the brand's:

- `<brand> Roblox partnership`, `<brand> Fortnite`, `<brand> game partnership`
- the studio's newsroom once you know who built it (voldex.com/news, for one)
- the experience's own social account, which posts the update

An Aston Martin check reported nothing at all while Voldex had announced ten
licensed Aston Martin cars in Driving Empire, live since 6 September 2025, in
an experience with 3.2bn lifetime visits. The experience was called "[ASTON
MARTIN] Driving Empire" at the time. One search would have found it, and the
same was true of KTM. The platform APIs cannot see inside an experience, so
licensed vehicles, wearables and events are invisible to every figure the
collector produces.

Anything you find this way is quotable when it comes from the studio or the
brand direct, with the date and the source named. A fan wiki or an AI summary
is a lead to chase, never a citation.

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
- Where a collection ceiling was hit, the report says so in the method strip
  and the figure is written as a floor ("at least N"). Never let a capped
  count be read as a census.
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
missed. State plainly whether any collection ceiling was hit and therefore
whether the headline count is a total or a floor. If the brand appears under
several spellings, ask which is canonical before building.
