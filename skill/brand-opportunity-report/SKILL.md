---
name: brand-opportunity-report
description: Build a GEEIQ brand check for a sales conversation. Runs the same collector, classifier and renderer as the internal brand check pipeline (Roblox marketplace, Roblox experiences, YouTube gaming content), then applies the platform check, the web check and the house writing rules to produce a client-ready two-page PDF. Use whenever someone asks for a brand check, opportunity report, ABM report, prospect report, or what a brand looks like on Roblox, Fortnite or YouTube. Trigger on casual phrasings too: "what does Nike look like on Roblox", "run a brand check on Casio", "build me something for the LVMH pitch".
---

# Brand opportunity report (v7, 2 November 2026)

This skill ships the live GEEIQ pipeline, not a copy of it. `scripts/run.py`
collects, classifies and renders exactly as the automated brand checker does,
with every fix made since August. Your job is what the code cannot do: the two
checks before any presence claim, the copy, and the judgement about which
story the data supports.

Four steps, in this order: **run, read the flags, check outside the data,
write.** Skipping step three has produced three reports that told a brand it
was absent from a platform it had launched on. Do not be the fourth.

## Setup, once

- Python 3 (on every Mac) and Google Chrome (the renderer prints through it).
- Optional but worth it: `pip3 install pillow segno` gives the QR code and
  cleaner logos. Without them the report still renders; it just has no QR.
- `YOUTUBE_API_KEY` in your shell for the YouTube pull (ask Luke). Without it
  the YouTube step is skipped and the report says nothing about YouTube.
- `ANTHROPIC_API_KEY` is optional. With it, `run.py` drafts the copy itself.
  Without it, pass `--no-llm` and the copy comes from the rule-based template,
  which you then rewrite. Either way you edit before anything ships.
- First run creates `scripts/.venv` with reportlab, the fallback renderer.
  Let it.

## Step 1: Run

```bash
python3 scripts/run.py --brand "BRAND NAME" --out-dir out/brand --no-llm
```

One command does the whole pipeline: collect (marketplace across the brand
name and its variants, four sort orders each, to exhaustion; experiences;
YouTube on three platform searches), classify, fetch the logo, write the copy,
render. Outputs in `out/brand/`:

| File | What it is |
|---|---|
| `GEEIQ_Brand_check_<Brand>_<YYYY-MM>.pdf` | the two-page report |
| `report.html` | the page you edit, then re-render |
| `analyst_summary.txt` | every figure, every flag, every sample row. Read it first |
| `email_draft.txt` | a starting point, never sent as is |
| `data/` | the CSVs every number traces to, plus `collection_notes.json` |

**Time.** Twenty to sixty minutes for a real brand. The collector paces
itself and backs off on rate limits, and a run that takes an hour is the
collector doing its job. Never run two collections at once: they starve each
other and one silently overwrites the other's files. If a run looks dead,
check the log before assuming; a 429 backoff sits quiet for minutes.

**Brand name.** Type it the way fans title their items: "Chelsea" not
"Chelsea Football Club Ltd". The code strips brackets and org suffixes and
searches both forms, but a name nobody uses in a listing finds nothing.

To rerun the analysis on data you already collected (after editing the
context screen, say), pass `--csv-dir out/brand/data` and it skips collection.

## Step 2: Read the flags before you read the PDF

`analyst_summary.txt` is the review. The PDF is the draft. Every line below
has cost a real report.

| Field or flag | What it means | What you do |
|---|---|---|
| `items_official`, `items_fan`, `items_noise` | official, creator-made, and rows that matched nothing | noise never enters a figure |
| `COUNTS ARE A FLOOR` | a query hit Roblox's 1,000-row cap per query and sort order | the report says "at least N" and the method strip says why. Already worded that way by the renderer; keep it |
| `SHORT-NAME MATCHES` | rows that name only the trading name ("Chelsea", "Southampton") | skim them: the short name is also a person or a place. If a share is plainly something else, say so in the method strip |
| `SHORTENED-NAME MATCHES` | rows led by the first word plus kit or season wording ("Brighton Home Kit 22-23") | fine for clubs; still skim |
| `KEYWORD-SOUP SPAM` | listings chaining trending words around the brand ("xorowhair lidl tatsumaki") | excluded from top items already. If the WARNING says spam holds most favourite volume, quote no favourites figure at all |
| `CHECK THESE` (near-official accounts) | accounts named like the brand but not classified official: "Gregg's", "Greggs RBLX", "{UK} Greggs" | imitators mostly, but a partner running a sponsored activation looks identical. Confirm in step 3 before the report says no official presence |
| `Counted as official on the strength of the experience description` | partner-run experiences whose description declares the brand ("official Formula E", "sponsored by KFC") | open each one. The rule now requires the brand name next to "officially licensed", because "officially licensed by Voldex" once made a dungeon game Kinder's own. Trust but open it |
| `youtube_suspect: true` | under 30% of named YouTube view volume carries a gaming term | YouTube is dropped from the page. Do not put it back. Physical brands fail this constantly (KTM was 98m views of real motorbikes) |
| `youtube_thin: true` | most scanned videos never named the brand | the figure is demoted; it never leads |
| `Logo matched entity ... <- check this is the right company` | the logo came from Wikidata or the brand's site | look at it. "John Lewis" resolved to a US congressman once, Aldi to Aldi Nord's mark, DP World Tour to a logo retired in 2022. A wrong logo on a report to the brand's own marketer ends the conversation |
| `games_matching: 0` | no experience name matched | this is common and true for most brands. It is not a bug |

**Ordinary-word brands.** Kinder, Domino's, Snickers, Target: the brand word
appears on listings that are not the product. `run.py` has a context screen
(`CONTEXT_SCREENS`, near line 477) that counts a row only when the listing also
names the product. If your brand is a common word and the samples look wrong,
add an entry in the same shape as the existing ones, the lower-case brand as
the key and a tuple of the product label and its word list as the value, then
rerun with `--csv-dir`.
Without it, "Push Dominos" (a tile game, 2.9m visits) led a Domino's report.

**Zero rows for a real brand.** Roblox returns nothing for some marks in
every phrase that contains them: Nike, Aston Martin, Rolls Royce and BMW so
far. The run exits saying no usable figures. That is not absence. Go to the
protected-mark section below.

## Step 3: Check outside the data (never skip)

The collector sees marketplace listings and experience names. It cannot see
licensed cars inside a driving game, a wearable drop that sold out, an event
that ended, or a partnership announced on a studio's website. Three reports
have nearly gone out saying "no official presence" to brands that had one:
KTM (live Driving Empire integration), Aston Martin (ten licensed cars in a
3bn-visit game) and True and the Rainbow Kingdom (a limited UGC capsule that
no longer appears in search). The third one was addressed to the President of
the studio that commissioned it.

**What the pipeline now does for you (v7).** `run.py` asks the platform
itself before writing a word: it resolves the brand, pulls its partnership
records, and looks up every Roblox-verified account that issues brand-named
items. A verified issuer the platform (or the licensee list in `run.py`) places
for the brand becomes "official via partner" and the copy credits it by name:
Mr Bean's eight items by Cartoon Network Games are Mr Bean's official presence,
not fan-made. A verified issuer nobody can place stays creator-made but blocks
every absence claim, so the draft names the account and stops there. Set
`GEEIQ_API_TOKEN` (your platform session token, from the MCP setup page) or
the check is skipped and `analyst_summary.txt` says `PLATFORM CHECK: NOT DONE`.
Read the `PLATFORM CHECK`, `OFFICIAL VIA PARTNER` and `VERIFIED, NOT PLACED`
lines in the summary; then still do 3a and 3b by hand, because the platform
only knows the partnerships it has logged.

**3a. The GEEIQ platform.** Search the brand on
`https://app.geeiq.com/search?q=<brand>` and open the brand page's
Partnerships and Experiences tabs. Open "View table" for dates: a two-week
event and a live integration look identical on the card. If you have the
GEEIQ MCP server configured in Claude Code, `search_entities` and
`get_entity_snapshot` do the same from the chat. Platform beats collected data
on partnerships; collected data beats the platform on marketplace counts.

**3b. The web.** A real search, every time:
`<brand> Roblox`, `<brand> Fortnite`, `<brand> game partnership`, then the
partner studio's newsroom once you know who builds for them (Voldex, Gamefam,
Dubit, Super League, Twin Atlas, Atopos). Announcements sit on the studio's
site more often than the brand's. A studio or brand announcement with a date is
quotable. A fan wiki, a Reddit thread or an AI summary is a lead, never a
citation.

**3c. Limited drops leave no trace.** Roblox catalog search does not return
items that are off sale, so a sold-out limited collection vanishes from every
count and the brand looks absent. If the web says a drop happened, the report
credits it and says the items are no longer listed. Never write "no presence"
over a launch the recipient announced.

**The scope rule, absolute.** Presence claims name what was searched: "no
official presence on Roblox's marketplace", never "no official presence
anywhere". Brands live in licensed console games and partner integrations
this data cannot see, and the recipient usually signed those deals.

## Protected marks: when search returns nothing

If `grab.py` reports `items=0 games=0` for a brand that obviously has fans,
test one query by hand: `https://catalog.roblox.com/v1/search/items/details?Keyword=<brand>&Limit=10`.
If `data` is empty or null while a slang term ("bimmer") returns rows, the
mark is unsearchable. Use the workaround:

```bash
python3 scripts/grab_hidden.py --brand BMW --alias bimmer --alias beamer \
    --query "e30 m3" --query "m3 gtr" --out out/bmw-hidden
```

It sweeps the slang and model names fans use, the stores of the creators it
finds (where items literally named for the brand sit, unsearchable), and the
groups carrying the name with their public experiences. Everything it returns
is a floor. Word it as "reachable through slang and model codes"; say the
brand name itself returns nothing from search; do not claim to know why. The
cause has not been established and "Roblox suppresses your trademark" is not
a sentence to put in front of a brand's lawyers.

## Step 4: Decide the story, then write

Three stories exist and the data picks:

- **Committed brand.** Official presence plus a fan tail. Lead with the
  official figures; the fan tail is what players built around it.
- **Whitespace with demand.** Zero official, real creator-made footprint.
  Lead with the footprint as demand the brand does not own or measure.
- **Whitespace without demand.** Zero official, a handful of items. The
  brand's own zero goes in the first card, the hero is the brand's own thing
  (a past activation, a sister brand, the category it sells into), and the
  proof comes from verified peers in ONE supporting panel headed "Already in
  your category". Never lead with a competitor's number: a draft that opened
  John Lewis with Tommy Hilfiger's 63.8m visits was called an absolute mess.

For peers, verify every figure yourself:

```bash
python3 scripts/peers.py --game "Spurs Adventure Arena" --place 9616411936 --group-name "Bloxton Hotels"
```

Lifetime visits belong to the experience, so attribute them to a brand only
when the brand owns it. Group memberships are community sizes, not players.
Figures a brand reported about itself (a Shorty entry, a LinkedIn post) are
quotable only as "the club reports".

**Framing, binding on every sentence.** The angle is proven demand the brand
is not capturing or measuring. It is a missed opportunity, never "someone is
using your IP". Hayley's words: the second framing gets us forwarded to legal,
and legal do not buy analytics platforms. So:

- A fan footprint is demand, not a showcase. Do not celebrate it.
- Accounts using the name are "accounts using the name", counted plainly.
  Never "unofficial", "imitators", "fakes" or "lookalikes" on the page.
- Strike anything like "style themselves to look official", "could be
  mistaken for official activity", "worth a trademark check", "taking steps
  not to be found". The Claude copy produces these; you remove them.
- Credit what the brand has done before you show the gap. A brand's own
  gaming team knows its Fortnite work better than you do.

**Writing rules.** UK English. No em dashes: full stops, commas or colons.
No exclamation marks. Sentence case. Never: ecosystem, intelligence platform,
seamless, leverage, unlock, branded activations, benchmark performance, drive
ROI, metaverse. No "not X, it's Y" or "not X, but Y" constructions. Say
"gaming and virtual worlds". "What this means" is four sentences, about 75
words. Numbers carry the argument; write fewer sentences, not more.

**Editing and re-rendering.** Edit `report.html` in the output folder, then:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --no-pdf-header-footer --print-to-pdf="GEEIQ_Brand_check_BRAND_YYYY-MM.pdf" \
  "file://$PWD/report.html"
```

Page 2 is the standing primer; change only the brand name in its closing
panel. For a one-page version (a sales call, a slide), delete the second
`<div class="page">` block and change the footer to "Page 1 of 1".

Names and creators on the page are printed by a whitelist of what the embedded
fonts can draw: emoji and non-Latin scripts are stripped, tm and (r) are kept
on purpose so an imitator called "Tesco(tm)" is never shown as "Tesco". Do not
paste raw listing names back in.

## Before it leaves you

- Every figure traces to a CSV row, a platform screen, `peers.json`, or
  arithmetic on them. Snapshot date on the page.
- Floors are labelled "at least". Nothing capped is read as a total.
- Page 1 content clears the footer. Open the PDF and look; the method strip
  is the first thing to fall off the page when copy runs long.
- The logo is the right company and the current mark.
- Every presence claim is scoped to a platform.
- The web check and the platform check happened, and anything they found is
  on the page.
- No YouTube figure appears if the summary flagged it suspect.

## Deliver

In chat, after the PDF: three to five bullets covering what the data
supports, every flag you acted on, the gaming share and whether YouTube was
dropped, anything the platform or the web showed that the collector could not,
and whether the headline count is a floor. Attach the PDF and point at
`analyst_summary.txt`.

If you send it yourself, BCC `5878363@bcc.hubspot.com` so the email lands on
the contact's HubSpot record. Do not send a decline or a report to a contact
someone else owns without telling them.

## Known limits, say them when they bite

- Roblox search caps at about 1,000 rows per query and sort order and pads
  weak queries with popular unrelated games. Counts are floors, and rows with
  no brand match are noise.
- Experience search returns the top hundred or so per query, never the tail.
- YouTube search is relevance-ranked, never a census, and the view volume on
  physical-product brands is mostly real-world footage.
- Nothing here sees inside an experience: licensed cars, wearables, events
  and sponsorship placements are invisible to every figure.
- Group memberships overlap and are not players.

## Sending a brand check by hand

The automated checker copies in the SDR who covers the brand's sector on
every delivery email (since 22 Oct 2026). A report sent by hand, such as a
bespoke build or a corrected CI draft, follows the same rule, so the lead
gets the same route to a full walkthrough whichever way the report arrives.

Pick the SDR by the brand's sector:

| SDR | Sectors |
|---|---|
| Rachel Ozsanlav-Harris, rachel@geeiq.com | Fashion & Apparel, Retail, Personal Care & Cosmetics, Sports, Financial Services, Public Services / Internet apps |
| Cody Gray, cody@geeiq.com | Food & Drink, Automotive, Toys & Collectables, Consumer Electronics, Media & Entertainment, Leisure, Travel & Tourism |

When the sector is unclear, run the same classifier the automation uses:
`python3 automation/sdr_route.py in the brand-check repo "BRAND" --email lead@domain`
(needs `ANTHROPIC_API_KEY`). A brand that fits no sector (pharma, telecoms,
energy, tools) gets the closest one. Tell Luke it was a closest fit when you
hand him the draft.

Every hand-sent `email_draft.txt` then carries:

- A header block: `To:` the lead, `CC:` the SDR, `BCC: 5878363@bcc.hubspot.com`
  (logs the email in HubSpot), `Attach:` the PDF.
- This paragraph, on its own, directly above the sign-off, with the SDR's
  first name. Keep the wording identical to the automated email:

  > For even more detail, I've copied in my colleague Rachel, who can take
  > you through the entire brands and gaming landscape and what others in
  > your category are doing.

  If the email already offers a consultation booked by the SDR (the IOC
  email did), that offer replaces this paragraph. Never introduce the SDR
  twice.

If someone else owns the contact or the company in HubSpot (an AE such as
Sam, Harry or Charles), still copy in the sector SDR. Name the owner in the
note to Luke so he can decide whether they should be copied in as well.

Drafting is not sending. Send only when Luke says so in the current
conversation, and report the To, CC and BCC lines as sent.

## Example

**User**: what does KFC look like on roblox?

**Do**: run `python3 scripts/grab.py --brand "KFC"`, classify, then report
along these lines: "No official KFC presence. Players built it instead:
150 creator-made KFC items from 86 creators, and the top KFC experiences
have 69m lifetime visits between them, led by Escape KFC Obby at 44m.
Excluded 60 unrelated search rows. YouTube skipped, no API key set."
