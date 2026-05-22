# Competitor curation — methodology

Source of truth for Phase 1.5 of the research pipeline. Runs after channel discovery (Phase 1) and before video scraping (Phase 2). Produces a ranked **top 10 primary competitors** list.

---

## Why this phase exists

Discovery returns 15–25 candidate channels. Scraping all of them deeply costs quota and dilutes focus. We want a smaller set of channels we treat as **primary competitors** — channels we model against most heavily — and a longer tail of secondary channels we still monitor but don't obsess over.

The top 10 list:
- Determines which channels get deep-scraped (last 100 videos) vs light-scraped (last 30 videos)
- Gets a weight boost in topic ranking — a breakout on a primary competitor scores higher than the same breakout on a secondary channel
- Gets its own dashboard tab in the Google Sheet so the user can see at a glance who they're modeling
- Can be manually edited by the user in `config/channels.yaml`

---

## When this phase runs

- After Phase 1 (Discovery) if `top_competitors` is empty in `channels.yaml`
- When the user explicitly says "re-curate competitors"
- Automatically every 60 days (so the top 10 evolves as the niche shifts)

Does NOT re-run on every `/research` invocation — the top 10 is stable, only refreshed periodically.

---

## Scoring dimensions

For each discovered channel, compute six sub-scores in the 0–1 range, then combine.

### 1. Niche similarity (weight: 0.25)

How focused on high-ticket sales is this channel?

**Method:**
- Take the channel's last 30 video titles
- Embed each using sentence-transformers (`all-MiniLM-L6-v2`)
- Build a "niche reference vector": embed the contents of `references/methodology/high-ticket-sales-niche-notes.md` (specifically the "Topic territories" and "Lexicon" sections) and the seed queries from `settings.yaml`
- Compute mean cosine similarity between each title and the niche vector
- Channel score = mean of all title scores, normalized to 0–1

**Rationale:** A channel that talks about "high ticket closing" 80% of the time and "career advice" 20% is more useful to model than one that splits 30/70.

### 2. Format match (weight: 0.20)

Does their content match your long-form format?

**Method:**
- For each of the channel's last 30 videos: get duration
- Compute % that are ≥10 minutes
- Score = that percentage, capped at 1.0

**Rationale:** A channel mostly making Shorts is solving a different problem. We need competitors whose long-form performance data is translatable.

### 3. Activity (weight: 0.15)

Are they actively uploading?

**Method:**
- Count uploads in past 90 days
- Score:
  - 0 uploads: 0.0
  - 1–2 uploads: 0.4
  - 3–6 uploads: 0.7
  - 7–15 uploads: 1.0
  - 16+ uploads: 0.85 (over-publishing often correlates with lower per-video quality)

**Rationale:** Dormant channels' data is stale. We want competitors who are still in the game.

### 4. Performance trajectory (weight: 0.15)

Is the channel hitting now, or coasting on old hits?

**Method:**
- Compute median views across all of the channel's videos in the past 24 months = `overall_median`
- Compute median views across the channel's last 10 uploads = `recent_median`
- Ratio = `recent_median / overall_median`
- Score:
  - Ratio < 0.5: 0.2 (declining)
  - 0.5–0.8: 0.5
  - 0.8–1.2: 0.7 (stable)
  - 1.2–2.0: 0.9 (growing)
  - 2.0+: 1.0 (breakout phase)

**Rationale:** Channels with rising recent performance are signaling that their current topic choices and formats are working. We want their playbook.

### 5. Tier fit (weight: 0.15)

How appropriate is their size for modeling at the user's stage?

**Method:**
- peer-lower (1k–10k subs): 1.0
- peer-upper (10k–100k): 0.85
- emerging (<1k): 0.6
- aspirational (>100k): 0.4

**Rationale:** Peer-lower channels are most algorithmically similar to the user's 600-sub channel. Aspirational channels' strategies often don't transfer down.

### 6. Engagement quality (weight: 0.10)

Are people actually engaging, or just lurking?

**Method:**
- Compute median engagement rate (likes + comments / views) across last 30 videos
- Normalize against niche baseline (2% is typical for sales YouTube)
- Score = min(channel_median / 0.04, 1.0) — a 4% engagement rate hits the cap

**Rationale:** High engagement signals genuine audience connection, which usually means better topic-market fit.

---

## Composite scoring

```python
composite = (
    0.25 * niche_similarity
    + 0.20 * format_match
    + 0.15 * activity
    + 0.15 * performance_trajectory
    + 0.15 * tier_fit
    + 0.10 * engagement_quality
)
```

Sort all discovered channels by composite descending. Take top N (default 10, configurable via `settings.yaml` → `competitors.top_n`).

---

## Output

### Write to `config/channels.yaml`

```yaml
top_competitors:
  - rank: 1
    id: UCxxxxxxxxxxxxxxxxxxxxxx
    name: "Channel Name"
    subs: 24300
    tier: peer-upper
    composite_score: 0.87
    sub_scores:
      niche_similarity: 0.92
      format_match: 0.88
      activity: 1.0
      performance_trajectory: 0.9
      tier_fit: 0.85
      engagement_quality: 0.7
    curated_at: 2026-05-20
    notes: ""    # user can add manual notes
  - rank: 2
    ...
  # up to 10
```

Secondary channels remain in the regular `channels:` list, untouched.

### Show user in chat

After curation, surface a table:

```
Top 10 primary competitors:
 1. Cole Gordon              | 87k subs  | peer-upper | score 0.87
 2. Closer Cartel            | 32k subs  | peer-upper | score 0.84
 3. [...]
 ...
10. Setter Academy           | 4.2k subs | peer-lower | score 0.61

Reply "looks good" to proceed, or "swap X for Y" to manually adjust.
```

Wait for user confirmation before proceeding to Phase 2 (Video scraping) on first curation. Subsequent re-curations can proceed automatically unless ranks shifted significantly (>3 positions of churn).

---

## Manual override

User can edit `config/channels.yaml` directly:

```yaml
top_competitors:
  - rank: 1
    id: UCxxxxxxxxxxxxxxxxxxxxxx
    name: "Channel I want pinned at #1"
    pinned: true        # respected on re-curation
  - rank: 2
    ...
```

Channels with `pinned: true` keep their rank position even on re-curation. Useful when the user knows a channel is especially relevant for reasons the scoring doesn't capture (e.g., "this person actually shares my exact methodology, I want to study them closely").

User can also add a channel to `excluded:` to keep it out of the top 10 entirely:

```yaml
excluded:
  - id: UCxxx
    name: "Channel I don't want to model"
    reason: "different niche / I don't respect their approach"
```

---

## Downstream effects

The rest of the pipeline reads `top_competitors` and adjusts behavior:

### Phase 2 — Video scraping
- Top 10 channels: deep scrape, last 100 videos or 24 months (whichever larger)
- Secondary channels: light scrape, last 30 videos or 12 months
- This roughly halves quota cost vs scraping everything deeply

### Phase 6 — Candidate ranking
- Apply a `primary_competitor_multiplier` of 1.25 to `composite_score` for any topic whose source video came from a top-10 channel
- This pushes primary-competitor breakouts up the candidate list

### Phase 7 — Sheet output
- Add column to topics tab: `Primary competitor` (✓ if source is top 10)
- Add a separate sheet tab: `Top 10 Competitors` with the dashboard view:
  - Rank, Channel, Subs, Tier, Composite score
  - Uploads/month (cadence)
  - Median views, recent median views, trajectory direction (↑ → ↓)
  - Engagement rate
  - 3 most recent breakouts (title + outlier score)
  - Last refreshed date
- User can sort/filter this tab freely; it gets overwritten on each curation refresh
