# Brand check collector

Replaces the browser extension step of the brand check pipeline. Pulls the
source data straight from platform APIs and writes the CSVs the Claude
project expects. Stdlib Python only, nothing to install.

```bash
python3 grab.py --brand "KFC"
# -> out/kfc/roblox_catalog_items.csv
# -> out/kfc/roblox_games.csv
# -> out/kfc/youtube_{roblox,fortnite,minecraft}.csv  (needs YOUTUBE_API_KEY)
```

## What it collects

- **Marketplace items** (catalog search API): name, id, URL, creator, creator
  type, price, **favourites**, item type, created date. Favourites and dates
  are new; the extension's DOM scrape never had them.
- **Experiences** (omni-search + games API enrichment): name, ids, URL,
  like %, live players, plus **lifetime visits**, favourites, creator name and
  verified flag from a second API pass. Visits is the reach figure the
  reports were missing (KFC test: 68.7m combined visits).
- **YouTube** (official Data API, one CSV per platform searched): title, URL,
  video id, channel, **numeric view counts**, publish date.

## Auth

- **Roblox**: currently answers unauthenticated server-side calls. If both
  Roblox CSVs ever come back empty, put your `.ROBLOSECURITY` cookie value in
  `~/.config/geeiq/roblosecurity` (`chmod 600`) or the `ROBLOSECURITY` env
  var. Fetch it from your own browser DevTools; treat it like a password and
  never commit or share it.
- **YouTube**: set `YOUTUBE_API_KEY` (YouTube Data API v3 key from Google
  Cloud console; the free quota covers ~30 brand checks a day). Without it
  the YouTube CSVs are skipped with a note.

## Known trade versus the extension

The search API returns roughly the top 100 relevance-ranked experiences,
where the browser page's infinite scroll can accumulate hundreds more
long-tail results (mostly dead roleplay worlds with no players). So counts
from the collector are "top results" counts and the instructions word them
that way. The engagement figures (visits, favourites, votes) cover the
experiences that matter and are far richer than the DOM scrape.

Pacing is deliberately polite (1.2s between requests, one brand at a time).
Keep it that way.
