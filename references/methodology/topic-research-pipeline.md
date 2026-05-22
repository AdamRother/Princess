# Topic research pipeline — methodology

This is the source of truth for Stage 1 of the project. Claude Code reads this during the walkthrough and will reference it when the `topic-research` skill is eventually created.

---

## Goal

Surface 10–20 video topic ideas for the user's high-ticket sales channel, ranked by likelihood of performing well at the user's current channel size (~600 subs), with all supporting data visible in a Google Sheet.

## Inputs

- Niche: **high-ticket sales** (audience: high-ticket closers, setters, sales reps for coaches/consultants/agencies, founders selling high-ticket offers)
- User's `your_channel_id` (for tier calibration)
- Competitor channels in `config/channels.yaml` (or run discovery if empty / >30 days old)
- Seed queries from `config/settings.yaml` (`research.seed_queries`)
- Tier thresholds and scoring weights from `config/settings.yaml`

## Outputs

- Rows in the configured Google Sheet, one per topic candidate
- Updated `config/channels.yaml` with newly discovered channels
- Cached video data in `output/raw/videos/{channel_id}.json`
- Cached channel metadata in `output/raw/channels/{channel_id}.json`

---

## Phase 1 — Channel discovery

**Run when:** `channels.yaml` is empty, OR `last_scraped` on all channels is >30 days old, OR user explicitly requests rediscovery.

### Steps

For each seed query in `settings.yaml`:
1. `youtube.search.list` with `q=<query>`, `type=channel`, `maxResults=25`, `order=relevance`
2. Extract channel IDs from results
3. Dedupe globally across all seed queries

For each unique channel ID:
1. `youtube.channels.list` to get: `subscriberCount`, `videoCount`, `viewCount`, `country`, `title`, `customUrl`
2. `youtube.playlistItems.list` on the channel's uploads playlist → last 30 video IDs
3. `youtube.videos.list` (batch of 30) → get `viewCount` for each, compute median
4. Filter: keep channel if **either**:
   - It has uploaded ≥5 videos in the past 6 months (active)
   - It has ≥10k subscribers OR ≥100k total views

For each kept channel, assign tier based on `subscriberCount` against thresholds in `settings.yaml`:
- `>= aspirational_min` (default 100k) → `aspirational`
- `>= peer_upper_min` (default 10k) → `peer-upper`
- `>= peer_lower_min` (default 1k) → `peer-lower`
- else → `emerging`

Write to `config/channels.yaml`.

**Quota cost:** ~15 seed queries × 100 units + (kept channels × 2) ≈ 1,600–1,800 units for first run.

---

## Phase 1.5 — Competitor curation

**Run when:** `top_competitors` in `channels.yaml` is empty, OR older than 60 days, OR user requests "re-curate competitors."

This phase reduces ~25 discovered channels down to the **top 10 primary competitors** we'll focus on. Full methodology in **`references/methodology/competitor-curation.md`**.

### Quick summary
- Score each discovered channel on 6 dimensions: niche similarity, format match (long-form), activity, performance trajectory, tier fit, engagement quality
- Composite score determines top 10
- Show ranked list to user in chat; wait for confirmation on first curation
- Write to `channels.yaml` under `top_competitors:`

### Effect on downstream phases
- **Phase 2** (Scraping): top 10 get deep scrape (100 videos / 24 months); secondary channels get light scrape (30 videos / 12 months) — roughly halves quota
- **Phase 6** (Ranking): topics sourced from top 10 get a 1.25x boost on composite_score
- **Phase 7** (Output): adds `Primary competitor` column to topics tab + a dedicated `Top 10 Competitors` dashboard tab

**Quota cost:** mostly free (uses cached video data from Phase 1). Maybe ~50 units if some sub-scores need fresh fetches.

---

## Phase 2 — Video scraping

For each channel in `channels.yaml`:

### Determine scrape depth based on competitor tier
- **Top 10 primary competitors** (`top_competitors` list): deep scrape — last 100 videos or 24 months, whichever yields more
- **Secondary channels** (`channels:` list, not in top 10): light scrape — last 30 videos or 12 months
- **Pinned channels** (`pinned:` list): deep scrape regardless of competitor status

### First run (no cache)
1. `youtube.playlistItems.list` on uploads playlist, paginate to get all video IDs (or stop at `videos_per_channel_max` from settings)
2. Filter to videos published in the past `max_age_months` (default 24)
3. `youtube.videos.list` in batches of 50 to fetch full metadata:
   - `id`, `snippet.title`, `snippet.description`, `snippet.tags`, `snippet.publishedAt`, `snippet.thumbnails`
   - `contentDetails.duration` (parse ISO 8601)
   - `statistics.viewCount`, `statistics.likeCount`, `statistics.commentCount`
4. Filter out:
   - Shorts (duration < `video_filters.min_duration_seconds`, default 60s)
   - Live streams (`liveBroadcastContent` != "none")
5. Write to `output/raw/videos/{channel_id}.json`

### Subsequent runs (incremental)
1. Read cached `{channel_id}.json`
2. `youtube.playlistItems.list` on uploads playlist, walk until you hit a video already cached → stop
3. New video IDs: full fetch (as above)
4. Already-cached video IDs: batched `youtube.videos.list` for just `statistics` — refresh view/like/comment counts only (1 unit each)
5. Merge and rewrite cache

**Quota cost:** ~100 units per new video, ~1 unit per refresh. Incremental runs are typically 200–500 units total.

---

## Phase 3 — Performance scoring

For each video in the cache, compute these fields and store in memory:

- `days_since_publish` = (today - publishedAt).days
- `views_per_day` = `viewCount` / max(`days_since_publish`, 1)
- `channel_median_views` = median of all that channel's videos' viewCount
- `outlier_score` = `viewCount` / max(`channel_median_views`, 1)
- `engagement_rate` = (`likeCount` + `commentCount`) / max(`viewCount`, 1)
- `age_weighted_score` = `views_per_day` × log(`days_since_publish` + 7)

Flag a video as **breakout** if:
- `outlier_score >= scoring.outlier_threshold` (default 3.0) AND
- `views_per_day >= channel_median_views_per_day × 2`

Keep all breakouts as candidates for clustering.

---

## Phase 4 — Topic clustering

Goal: group breakouts that are about the same underlying topic, so we surface unique ideas not 15 versions of the same thing.

### Steps
1. Load `sentence-transformers` model from `clustering.embedding_model` (default `all-MiniLM-L6-v2`). Free, runs locally, ~80MB download first time.
2. Embed each breakout video's title (just title; description adds too much noise).
3. Run DBSCAN with `eps=0.4`, `min_samples=2` (from settings). DBSCAN groups similar items and leaves outliers as singletons — both are useful.
4. For each cluster (and each singleton), pick the **anchor**: highest `composite_score` (computed in Phase 6) video.
5. Note all variations within the cluster — useful for the user to see "this idea hit on 4 different channels with these title variations."

---

## Phase 5 — SEO enrichment

For each cluster anchor:

### YouTube autocomplete
- Hit: `https://suggestqueries.google.com/complete/search?client=youtube&ds=yt&q={anchor_title_seed}`
- No auth, free, returns JSON
- Use the most distinctive 2–4 words from the anchor title as the seed
- Parse `[1]` of the response array — list of suggestions
- Store as `autocomplete_suggestions`; count = `keyword_richness`

### Google Trends (via pytrends)
- Initialize `TrendReq(hl='en-US', tz=360)`
- `pytrends.build_payload([anchor_keyword], cat=0, timeframe='today 12-m', geo=settings.seo.trends_region)`
- Get `interest_over_time()` → mean of last 12 months = `search_volume_proxy` (0–100)
- Compare last 3 months mean vs prior 3 months mean → `trend_direction`:
  - `rising` if last3 > prior3 × 1.15
  - `declining` if last3 < prior3 × 0.85
  - `stable` otherwise
- `pytrends.related_queries()` → `top` and `rising` → store top 5 of each as `related_searches`

### Rate limiting
pytrends gets rate-limited if hit too fast. Sleep 1–2 seconds between calls. If 429, sleep 60s and retry once.

---

## Phase 6 — Candidate ranking with tier match

For each cluster anchor:

```
tier_match = tier_match_weights[anchor.channel.tier]   # 1.0 for peer-lower, 0.3 for aspirational

primary_competitor_boost = 1.25 if anchor.channel.id in top_competitors else 1.0

trend_modifier = {
  "rising": 0.3,
  "stable": 0.0,
  "declining": -0.2
}[trend_direction]

composite_score = (
    outlier_score
    * tier_match
    * primary_competitor_boost
    * (1 + trend_modifier)
    * (1 + log(keyword_richness + 1) * 0.1)
    * (1 + min(search_volume_proxy / 100, 1.0) * 0.3)
)
```

Sort all candidates by `composite_score` descending. Take top `sheet.top_n_candidates` (default 100), split evenly: top 50 trending (≤90 days) and top 50 evergreen (>90 days).

### Generate per-candidate fields
- **`suggested_title`** — single LLM call (Claude API) that takes:
  - The anchor's title (pattern reference)
  - Top 3 autocomplete suggestions (keyword stuffing)
  - User's `voice-and-tone.md` (so the title sounds like them)
  - Asks for one title <60 chars, keyword-rich, in the user's voice
- **`why_this_fits`** — generated in the same prompt, one sentence: e.g. *"Peer-tier breakout (5.2x median), search trending up, low keyword competition"*
- **`difficulty`** — heuristic 1–5:
  - 1 = talking head, no edits beyond basic cuts
  - 2 = talking head + light B-roll
  - 3 = talking head + screen recordings or examples
  - 4 = needs guest, demo, or complex visuals
  - 5 = production-heavy (location shoot, multiple cameras, etc.)
  - Default to 1–2 unless the source video clearly required more.

---

## Phase 7 — Sheet output

Write to the Google Sheet specified by `target_sheet_id`. The Sheet has **three tabs**:
- **Tab 1: "Trending Now"** — top 50 topics from videos ≤90 days old
- **Tab 2: "Proven Evergreen"** — top 50 topics from videos >90 days old (min 3k views)
- **Tab 3: "Top 10 Competitors"** — competitor dashboard (unchanged each run unless recuration runs)

Each topic tab has the same 7-column structure. Always replaces — no append mode.

### Tab 1 & 2: "Trending Now" / "Proven Evergreen" — decision view

7 columns, 50 rows per tab (sorted by Score descending):

| Column | Content |
|---|---|
| ⭐ | Set on the top 3 picks only |
| Idea | Working title in the user's voice (cluster anchor) |
| Proof | HYPERLINK cell: `🔥 5.2x outlier · 142k views · 31 days  →  Channel / Source title` — clicking opens the source video |
| Search demand | `📈 Rising · 72/100` / `→ Steady · 45/100` / `📉 Declining · 18/100` |
| Why it works + fits you | 2–3 diagnostic sentences: what drove the source video's performance + how it maps to this channel's size and tier |
| Score | 0–100 (min-max normalized composite score); red→yellow→green color scale; sorted descending |
| Status | Dropdown: _(empty)_ / Selected / Scripted / Published |

Each topic row has **10 variant rows** directly beneath it, collapsed via Google Sheets row grouping (+ toggle on the left). The variants are only visible when the user expands a topic. Variant columns:

| Variant title | Angle | What's modified | Why this angle might work for me |

The 10 angles are fixed and identical for every topic:

| # | Angle |
|---|---|
| 1 | Story-led |
| 2 | Confessional |
| 3 | Framework |
| 4 | Contrarian |
| 5 | Numbers |
| 6 | Question |
| 7 | Beginner-angle |
| 8 | Advanced-angle |
| 9 | Reframe |
| 10 | Behind-the-scenes |

Each variant has a template-derived title, a description of what's modified from the main angle, and a rationale tied to the source video's tier + engagement data.

### Tab 2: "Top 10 Competitors" — dashboard view

Overwritten on each curation refresh. Schema:

| Column | Content |
|---|---|
| Rank | 1–10 |
| Channel | Name |
| Subs | Subscriber count |
| Tier | peer-lower / peer-upper / etc. |
| Composite score | Their curation score |
| Uploads / month | Recent cadence |
| Median views | Lifetime median |
| Recent median | Last 10 videos median |
| Trajectory | ↑ Growing / → Stable / ↓ Declining |
| Engagement % | Median engagement rate |
| Top breakout 1–3 | Title + outlier score (e.g. "How I Closed $50k in 30 Days — 5.2x") |
| Last refreshed | Date |
| Notes | Free text — user annotations |

### Tab 3: "Top 10 Competitors" — competitor dashboard

Same schema as described in the Competitor Curation doc. Overwritten on each curation refresh (every 60 days). Not touched during normal research runs unless `--recurate` is passed.

### Write behavior

**Always replace.** Every run clears all rows in both topic tabs (Trending Now + Proven Evergreen) and writes fresh. No append mode. The `output/raw/` cache preserves historical video data locally.

### After writing

- Print the Sheet URL in chat
- Print the top 5 Idea + Score rows from each tab as a quick text summary
- End with: **"Top 50 trending + 50 evergreen candidates are in the sheet: [link]. Reply with the tab and row number to script."**

That message is the handoff to Stage 2.

---

## Quota budget for a typical full run

| Phase | Approximate cost |
|---|---|
| 1 — Discovery (first time only) | 1,500–2,000 units |
| 1 — Discovery (cached, no rerun) | 0 |
| 1.5 — Competitor curation | ~50 units (mostly uses cached Phase 1 data) |
| 2 — Video scraping (first run, top 10 deep + 15 secondary light) | ~1,200–1,500 units |
| 2 — Video scraping (incremental, all channels) | 200–400 units |
| 3, 4 — Scoring + clustering | 0 (all local) |
| 5 — SEO enrichment (20 anchors) | 0 quota; pytrends rate-limited |
| 6 — Title generation (20 LLM calls) | 0 YouTube quota; Claude API tokens (~10k input + 1k output per run) |
| 7 — Sheet writes (both tabs) | 0 (Sheets API not quota-billed) |

**Total YouTube quota:**
- First-ever run (full discovery + curation + deep scrape): ~2,800–3,500 units
- Subsequent runs (incremental scrape, no recuration): ~200–500 units
- Curation refresh (every 60 days): ~50 units

All comfortably under the 10,000/day free cap.
