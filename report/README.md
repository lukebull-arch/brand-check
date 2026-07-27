# Brand check report runner

Brand name in, finished report out:

```bash
python3 run.py --brand "KFC"
```

Output lands in `out/<brand>/`:
- `GEEIQ_Brand_check_<Brand>_<YYYY-MM>.pdf` — the one-page report
- `email_draft.txt` — delivery email, ready to personalise and send
- `analyst_summary.txt` — classification numbers, excluded rows, oddities
- `data/` — the collected CSVs (kept for the record)

First run creates a `.venv` with reportlab automatically. Use
`--csv-dir DIR` to reuse existing CSVs instead of collecting fresh, and
`--no-llm` to force template copy.

## The pipeline

1. **Collect** — calls `../collector/grab.py` (Roblox items + experiences;
   YouTube too once `YOUTUBE_API_KEY` is set).
2. **Classify and compute** — official / creator-made / noise splits,
   lifetime visits, favourites, creators, all in plain code. Every number in
   the report comes from this step.
3. **Copy** — with `ANTHROPIC_API_KEY` set, Claude picks and words the
   headline, stats, reading and email (model via `BRAND_CHECK_MODEL`, default
   claude-sonnet-5). Guardrails: its stats must match the computed candidate
   values exactly, its prose is linted against the house writing rules (em
   dashes, banned words, "not X it's Y", exclamation marks, one coral stat),
   and one retry with feedback is allowed. Anything that fails twice, or no
   API key at all, falls back to a rule-based template so a report always
   ships. `analyst_summary.txt` records which source wrote the copy.
4. **Render** — `build_report.py` draws the approved layout (assets in
   `assets/`: brand fonts and logos). The standing bottom half and its
   verified SBVW figures live in `build_report.py`; update them there when
   SBVW 2027 lands.

## Review before sending

The runner builds a draft. Look at the PDF and the analyst summary before
the email goes anywhere: name-matching can misclassify, and the summary
lists exactly what was counted and excluded so the check takes a minute.

The fuller judgment spec (classification nuance, lookalikes, story angles)
is `claude-project-instructions.md` in this folder. It doubles as the manual
fallback: paste it into a Claude project and upload CSVs by hand.
