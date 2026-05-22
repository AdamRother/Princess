# Sales YouTube Research & Script Generation

## Mission

This project helps grow a YouTube channel in the **sales coaching** niche by:
1. Researching what's working for top creators in this space (data-driven, not guessing)
2. Generating SEO-optimized topic ideas backed by performance + search data
3. Writing long-form video scripts in **her voice** using her stories and tone

**Channel owner**: Female sales coach. Content covers the full sales spectrum — sales calls, closing, high-ticket, appointment setting, cold outreach, objection handling, sales mindset, scripts, and coaching methodology.

**Target audience for the channel**: anyone who wants to get better at sales — high-ticket closers, appointment setters, sales reps working for coaches/consultants/agencies, SDRs/BDRs doing outbound, founders selling their own offers on calls, and general salespeople at any level or gender.

**My channel today**: ~600 subscribers, a few thousand views per video. Use this to calibrate which competitor channels are "modelable" (peer-tier) vs aspirational reference.

---

## Skills (active — use these)

Both skills are live in `.claude/skills/`. Invoke them by name:

- **`/topic-research`** — runs the full research pipeline and populates the Google Sheet. See `.claude/skills/topic-research.md` for the exact steps.
- **`/script-writer`** — takes a tab name + row number from the sheet and writes a full script to Google Doc. See `.claude/skills/script-writer.md` for the exact steps.

When the user types either command, read the matching skill file and follow it exactly.

---

## The pipeline (target end state)

### Stage 1 — `/research` (will become the `topic-research` skill)

When I say "let's run the research" or `/research`:

1. **Check credentials.** Read `.env`. For any missing value, walk me through getting it using the matching `references/setup/` guide.
2. **Check competitor channels.** Read `config/channels.yaml`. If `channels:` is empty or older than 30 days, run channel discovery (see `references/methodology/topic-research-pipeline.md`, Phase 1).
3. **Curate top 10 primary competitors.** If `top_competitors:` is empty or older than 60 days, run competitor curation (see `references/methodology/competitor-curation.md`). Show me the ranked top 10 in chat; wait for confirmation before proceeding on first curation.
4. **Scrape videos** for each competitor channel (Phase 2). Deep-scrape the top 10, light-scrape the rest. Cache to `output/raw/videos/`.
5. **Score performance** — views/day, outlier score, engagement (Phase 3).
6. **Cluster topics** by semantic similarity using sentence-transformers locally (Phase 4).
7. **SEO enrichment** — YouTube autocomplete, Google Trends, related queries (Phase 5).
8. **Rank candidates** weighted by tier match AND primary competitor status — peer-tier outliers from top-10 competitors score highest because they're most modelable at my channel size (Phase 6).
9. **Write top 20 to the Google Sheet** across three tabs (Phase 7): Tab 1 "Topics" — 7-column decision view with 10 collapsed angle variants per topic; Tab 2 "Top 10 Competitors" — dashboard; Tab 3 "Details" — hidden, all analyst metadata (used by script-writer). Always replaces; no append mode.
10. **End with:** "Top 10 candidates are in the sheet: [link]. Reply with the row number to script."

### Stage 2 — Auto-triggered script generation (will become the `script-writer` skill)

When I reply with a row number after `/research` completes:

1. Pull that row's data from the Google Sheet (topic, source video URL, suggested title, etc.)
2. Pull the top 3–5 reference video transcripts on that topic via `yt-dlp` (see `references/methodology/script-writing-pipeline.md`)
3. Load my voice/stories/tone from `context/`
4. Generate full long-form script (target 10–60 min, default 30 min ≈ 4,500 words)
5. Generate YouTube metadata (5 title variants, SEO description with chapter timestamps, tags, thumbnail brief)
6. Write to a new Google Doc in the configured Drive folder
7. Return the Doc URL to me

---

## Constraints (non-negotiable)

- **Cost: free or as close to free as possible.** Stack: YouTube Data API v3 free tier (10k units/day), `yt-dlp` (open source), `pytrends` (free), YouTube suggest endpoint (free, no auth), `gspread` + `google-api-python-client` with my own Google account. No paid APIs, no vidIQ/TubeBuddy subscriptions.
- **Output format:**
  - Topics → **Google Sheet** — Tab 1 "Topics" (7-col decision view + 10 angle variants per topic, collapsed), Tab 2 "Top 10 Competitors", Tab 3 "Details" (hidden metadata for script-writer)
  - Scripts → **Google Doc** (one per video, named `[YYYY-MM-DD] {short title}`)
- **Long-form only.** Scripts target 10–60 minutes. Default 30 min unless I specify.
- **Freshness:** research runs fresh every time, but caches video data and only refreshes stats (1 quota unit each) on cached videos — keeps full runs well under the 10k/day cap.
- **Niche stays high-ticket sales.** Don't drift into "general sales" or "B2B SaaS sales" topics unless I explicitly broaden the niche in `config/settings.yaml`.

---

## Reference docs (read on demand)

**Setup guides** — read and walk me through when a credential is missing:
- `references/setup/01-youtube-api-key.md`
- `references/setup/02-google-auth.md`
- `references/setup/03-find-channel-id.md`
- `references/setup/04-create-sheet-and-doc.md`

**Methodology** — read when running the pipeline:
- `references/methodology/topic-research-pipeline.md` — full research flow
- `references/methodology/competitor-curation.md` — how to pick + rank the top 10 primary competitors
- `references/methodology/script-writing-pipeline.md` — full script flow
- `references/methodology/high-ticket-sales-niche-notes.md` — niche-specific context, lexicon, what works

**My voice/personality** — read EVERY time you generate a script:
- `context/voice-and-tone.md`
- `context/stories-bank.md`
- `context/audience-persona.md`
- `context/do-and-dont.md`
- `context/opening-styles.md`

---

## File map

```
sales-yt-research/
├── CLAUDE.md                          # this file
├── README.md                          # human quickstart
├── .env                               # API keys + client config (gitignored — I fill this)
├── .gitignore                         # excludes secrets, raw cache
├── config/
│   ├── channels.yaml                  # competitor channels (auto-populated)
│   └── settings.yaml                  # tier thresholds, seed queries, scoring weights
├── context/                           # MY voice — I fill these in
│   ├── voice-and-tone.md
│   ├── stories-bank.md
│   ├── audience-persona.md
│   ├── do-and-dont.md
│   └── opening-styles.md
├── references/                        # YOU read these on demand
│   ├── setup/                         # 4 guides for getting credentials
│   │   ├── 01-youtube-api-key.md
│   │   ├── 02-google-auth.md
│   │   ├── 03-find-channel-id.md
│   │   └── 04-create-sheet-and-doc.md
│   └── methodology/                   # docs for how each pipeline phase works
├── .claude/
│   └── skills/
│       ├── topic-research.md          # /topic-research skill — full research pipeline
│       └── script-writer.md          # /script-writer skill — script from sheet row
├── scripts/                           # Pipeline phase modules
└── output/
    └── raw/                           # cached API data (gitignored)
```

---

## First-session checklist (when I open this project the first time)

Run through these in order, one at a time. Don't skip ahead.

- [ ] Confirm Python 3.10+ is available; create a venv at `.venv/`
- [ ] Install: `gspread google-auth google-auth-oauthlib google-api-python-client yt-dlp pytrends pandas sentence-transformers scikit-learn pyyaml`
- [ ] Walk me through getting YouTube API key (`references/setup/01-youtube-api-key.md`)
- [ ] Walk me through Google OAuth setup (`references/setup/02-google-auth.md`)
- [ ] Confirm Sheet/Doc folder strategy — let you auto-create, or me provide IDs (`references/setup/04-create-sheet-and-doc.md`)
- [ ] Prompt me to fill in `context/` files (give me a minimum viable version to start with if I don't have time to fill all five)
- [ ] Then we run the first `/research` — step by step, you narrating, me confirming, until we have a populated Google Sheet
- [ ] Then I pick a topic, you generate the first script to Google Doc
- [ ] If everything works → convert to skills (`/topic-research` and auto-chained `/script-writer`)

---

## Skill conversion criteria (when "this is solid")

We convert to skills when ALL of these are true:
1. Full `/research` → Sheet flow runs without manual intervention
2. Script generation from a picked row produces output I'd actually record
3. Credentials persist across sessions (no re-auth every run)
4. Caching works — a second run uses <50% the quota of the first
5. I've validated at least 2 generated scripts feel like me

Don't propose skill conversion before all five are met.
