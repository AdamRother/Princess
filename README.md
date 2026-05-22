# Sales YouTube Research & Script Generator

Research what's working for top creators in your niche and generate long-form video scripts in your voice — all from Claude Code.

Built for sales coaching channels. Adaptable to any niche.

---

## What it does

**Stage 1 — Topic Research (`/topic-research`)**
Discovers competitor channels, scrapes their top videos, scores outliers, enriches with SEO data, and writes the top 100 candidates to a Google Sheet — split across two tabs:
- **Trending Now** — videos from the last 90 days performing well right now
- **Proven Evergreen** — older content with lasting high performance

Each topic comes with 10 collapsed angle variants so you can see different ways to model the same idea.

**Stage 2 — Script Generation (`/script-writer`)**
Takes a row number from the sheet and writes a full 30-minute script to a Google Doc — in your voice, using your real stories, with SEO metadata included.

---

## Stack (free or near-free)

| Tool | Cost | Purpose |
|------|------|---------|
| YouTube Data API v3 | Free (10k units/day) | Channel and video data |
| yt-dlp | Free | Transcript fetching |
| pytrends | Free | Google Trends data |
| YouTube suggest endpoint | Free, no auth | Autocomplete keywords |
| gspread + Google API | Free (your account) | Sheet and Doc output |
| sentence-transformers | Free, local | Semantic similarity |

No paid API subscriptions. No vidIQ. No TubeBuddy.

---

## Setup

### 1. Clone and create environment

```bash
git clone <repo-url>
cd <repo-name>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.template .env
```

Fill in `.env`:
- `YOUTUBE_API_KEY` — see `references/setup/01-youtube-api-key.md`
- Google OAuth — see `references/setup/02-google-auth.md`
- `CLIENT_CHANNEL_URL` — your YouTube channel URL
- `CLIENT_NICHE_DESCRIPTION` — one-line description of your channel

`TARGET_SHEET_ID` and `TARGET_DOCS_FOLDER_ID` can be left blank — they'll be auto-created on first run.

### 3. Fill in your voice

The `context/` folder contains five files that define how scripts sound. These ship with example content for a sales coaching channel — replace everything with your own information:

| File | What to put in it |
|------|-------------------|
| `context/voice-and-tone.md` | Your speaking style, phrases you actually say, energy |
| `context/stories-bank.md` | Real stories from your life and career |
| `context/audience-persona.md` | Who you're talking to, what they believe wrong |
| `context/do-and-dont.md` | Hard rules for every script |
| `context/opening-styles.md` | 3–5 opening styles you actually use with examples |

The more specific these are, the more the scripts sound like you. Vague context = generic scripts.

### 4. Open in Claude Code

```bash
claude
```

Then run:

```
/topic-research
```

Claude will walk you through any missing credentials, then run the full pipeline and drop the sheet link in chat.

---

## Usage

### Run topic research

```
/topic-research
```

Runs all 7 phases: channel discovery → scraping → scoring → SEO enrichment → ranking → sheet write. Ends with a link to the sheet and a prompt to pick a row.

### Generate a script

Reply with a tab and row number after research completes:

```
Trending row 3
```

or

```
/script-writer Evergreen row 7
```

Claude pulls the row data, fetches reference transcripts, loads your context files, and writes the full script to a new Google Doc. Returns the Doc URL.

### Resume a partial run

```
/topic-research --from phase3      # re-score from cached data
/topic-research --from phase6      # re-run ranking + sheet write only
/topic-research --rediscover       # force re-run channel discovery
```

---

## Project structure

```
├── .env.template              # copy to .env and fill in
├── CLAUDE.md                  # project instructions for Claude Code
├── requirements.txt           # Python dependencies
│
├── .claude/skills/
│   ├── topic-research.md      # /topic-research skill definition
│   └── script-writer.md       # /script-writer skill definition
│
├── config/
│   ├── channels.yaml          # discovered competitor channels (auto-populated)
│   └── settings.yaml          # tier thresholds, scoring weights, scrape depth
│
├── context/                   # YOUR voice — fill these in
│   ├── voice-and-tone.md
│   ├── stories-bank.md
│   ├── audience-persona.md
│   ├── do-and-dont.md
│   └── opening-styles.md
│
├── references/
│   ├── setup/                 # credential guides (01–04)
│   └── methodology/           # pipeline and script methodology docs
│
├── scripts/                   # pipeline phase modules
│   ├── phase1_discover.py
│   ├── phase2_scrape.py
│   ├── phase3_4_score_cluster.py
│   ├── phase5_seo.py
│   └── phase6_7_rank_sheet.py
│
├── utils/                     # shared helpers
│   ├── google_workspace.py    # Sheets + Docs API client
│   ├── youtube_api.py         # YouTube Data API client
│   ├── config.py              # env + settings loader
│   ├── cache.py               # file-based caching
│   ├── embeddings.py          # sentence-transformers wrapper
│   └── seo.py                 # pytrends + autocomplete
│
└── output/
    └── raw/                   # cached API data (gitignored)
```

---

## Quota usage

A full run (75 channels, 100 videos each) uses approximately 2,000–4,000 YouTube API units. The 10k/day free tier comfortably supports one full run per day. Subsequent runs use cached video data and only refresh stats on new videos.

---

## Adapting to your niche

1. Update `CLIENT_NICHE_DESCRIPTION` in `.env`
2. Update `config/settings.yaml` — seed queries, niche keywords, tier thresholds
3. Replace all five `context/` files with your channel's voice and stories
4. Run `/topic-research` — Phase 1 will discover channels relevant to your niche automatically

The pipeline is niche-agnostic. The voice is yours.
