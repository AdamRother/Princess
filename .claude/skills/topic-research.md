# Skill: /topic-research

Runs the full competitor research pipeline and populates the Google Sheet with ranked topic candidates.

## When to invoke

User says `/topic-research`, "run the research", "find topics", or "update the sheet".

## What this skill does

Discovers what's working for top sales creators on YouTube, scores every video, and writes two ranked tabs to the Google Sheet:
- **Trending Now** — videos published in the last 90 days that are already pulling strong views
- **Proven Evergreen** — videos 90 days–24 months old with proven sustained demand

Each topic row has 10 collapsed angle variants the user can expand and model.

## Steps — run in order, narrate each one

### 1. Check credentials
Read `.env`. Verify these keys are present and non-empty:
- `YOUTUBE_API_KEY`
- `CLIENT_SECRETS_PATH`
- `TARGET_SHEET_ID`

If any are missing, open the matching guide in `references/setup/` and walk the user through it before continuing.

### 2. Check competitor channels
Read `config/channels.yaml`. If `channels:` is empty or has fewer than 10 entries, run Phase 1:
```
python -m scripts.phase1_discover
```
Show the user how many channels were found. If `top_competitors:` is empty or older than 60 days, run Phase 1.5:
```
python -m scripts.phase1_5_curate
```

### 3. Scrape videos (Phase 2)
```
python -m scripts.phase2_scrape
```
Deep-scrapes top competitors (100 videos, 12 months), light-scrapes the rest (30 videos, 6 months). Caches to `output/raw/videos/`. Note the run ID printed at the end.

### 4. Score and filter (Phase 3+4)
```
python -m scripts.phase3_4_score_cluster
```
Scores every video, tags each as `trending` (≤90 days) or `evergreen` (>90 days). No clustering — every video is its own topic candidate. Note the new run ID.

### 5. SEO enrichment (Phase 5)
```
python -m scripts.phase5_seo --run-id <run_id_from_step_4>
```
Adds YouTube autocomplete keywords and Google Trends signal to each candidate.

### 6. Rank and write sheet (Phase 6+7)
```
python -m scripts.phase6_7_rank_sheet --run-id <run_id_from_step_4>
```
Ranks by composite score, splits 50 trending + 50 evergreen, writes to the Google Sheet.

### 7. End message
Print the sheet URL and say:
> "Sheet is updated — Trending Now and Proven Evergreen tabs are ready. Reply with the tab name and row number to write a script (e.g. 'Trending row 3' or 'Evergreen row 12')."

## Key settings (config/settings.yaml)
- `video_filters.trending_max_days: 90` — what counts as trending
- `video_filters.min_candidate_views: 1000` — minimum views to qualify
- `sheet.top_n_candidates: 100` — 50 per tab
- Format exclusions: no interviews, podcasts, vlogs, or reaction videos

## Notes
- All phases cache their output to `output/runs/`. If Phase 2 already ran today, skip it and reuse the cache.
- The Sheets API rate-limits at 60 writes/min — the script handles retries automatically.
- YouTube Data API quota is 10k units/day. A full run (Phase 1+2) costs ~2k–4k units. Phase 3–7 costs 0 quota.
